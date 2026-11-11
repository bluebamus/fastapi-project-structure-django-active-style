"""전역 예외 처리 — 응답에 예외 원문을 싣지 않음, 로그 수준과 route template, 처리기 없는 예외,
HTTP 예외 헤더(Allow·WWW-Authenticate), Redis 장애 503, 응답 직렬화.
"""

import inspect
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

import main
from app.core.exception import AppException

SENTINEL = "mysql+aiomysql://root:sup3rs3cret@db:3306/app"


def _client_with_exploding_route():
    @main.app.get("/_boom_{item_id}", include_in_schema=False)
    async def boom(item_id: str):
        raise RuntimeError(SENTINEL)

    return TestClient(main.app, raise_server_exceptions=False)


def test_unhandled_exception_response_hides_raw_detail(monkeypatch):
    monkeypatch.setattr(main.app_settings, "DEBUG", True)
    client = _client_with_exploding_route()

    response = client.get("/_boom_42")

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_SERVER_ERROR"
    assert body["detail"] is None, "raw 예외 본문이 응답에 실렸습니다."
    assert SENTINEL not in response.text
    assert "sup3rs3cret" not in response.text


def test_handler_logs_route_template_not_raw_path():
    """로그에는 /_boom_{item_id} 같은 template 을 남긴다."""
    source = inspect.getsource(main._register_exception_handlers)

    assert "route" in source, "예외 핸들러가 route template 을 쓰지 않습니다."


def test_debug_flag_no_longer_switches_detail_exposure():
    """DEBUG 여부로 노출을 가르던 분기가 사라졌는지 확인(회귀 방지)."""
    source = inspect.getsource(main._register_exception_handlers)

    assert "str(exc) if app_settings.DEBUG" not in source


def _client_raising(exc_factory):
    """`exc_factory()` 를 던지는 라우트를 붙인다. 경로마다 이름이 달라 서로 덮지 않는다."""
    path = f"/_app_exc_{len(main.app.routes)}" + "/{item_id}"

    @main.app.get(path, include_in_schema=False)
    async def raising(item_id: str):
        raise exc_factory()

    return TestClient(main.app, raise_server_exceptions=False), path


def _handler_records(caplog):
    return [r for r in caplog.records if r.getMessage().startswith("[AppException]")]


def test_client_error_app_exception_logs_warning_without_detail(caplog):
    """4xx 는 WARNING 이고, 클라이언트가 보낸 값이 담긴 detail 은 로그에 싣지 않는다."""
    import logging

    from app.core.exception import NotFoundException

    client, template = _client_raising(lambda: NotFoundException(detail={"email": SENTINEL}))
    with caplog.at_level(logging.DEBUG, logger=main.logger.name):
        response = client.get(template.replace("{item_id}", "42"))

    assert response.status_code == 404
    records = _handler_records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    record = records[0]
    assert not hasattr(record, "detail")
    assert SENTINEL not in logging.Formatter().format(record)
    assert record.path == template, "raw path 대신 route template 을 남긴다"
    assert record.status_code == 404
    assert record.error_code == "NOT_FOUND"


def test_server_error_app_exception_logs_error_with_detail(caplog):
    import logging

    from app.core.exception import DatabaseException

    client, template = _client_raising(lambda: DatabaseException(detail={"model": "Post"}))
    with caplog.at_level(logging.DEBUG, logger=main.logger.name):
        response = client.get(template.replace("{item_id}", "1"))

    assert response.status_code == 500
    records = _handler_records(caplog)
    assert [r.levelno for r in records] == [logging.ERROR]
    assert records[0].detail == {"model": "Post"}


# ------------------------------------------------------------------ 처리기 없는 예외
# 처리기가 없는 예외는 ServerErrorMiddleware 바로 안쪽(가장 바깥 사용자 미들웨어)에서 받아 기존 Exception
# 처리기로 응답을 끝낸다 — 로그 1번, 연결 유지, 응답 불변. 다시 올라가면 uvicorn 이 traceback 을 한 번 더
# 남기고 keep-alive 연결을 닫는다. raise_server_exceptions=True(기본)인 TestClient 는 앱 밖으로 나온 예외를 던진다.

_BODY_500 = {
    "error_code": "INTERNAL_SERVER_ERROR",
    "message": "내부 서버 오류가 발생했습니다.",
    "detail": None,
}


def _bug_route() -> str:
    path = f"/_bug_{len(main.app.routes)}" + "/{item_id}"

    @main.app.get(path, include_in_schema=False)
    async def bug(item_id: str):
        raise RuntimeError(SENTINEL)

    return path


def _tracebacks(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.exc_info]


def test_unhandled_exception_is_answered_once_and_not_reraised(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(main.app_settings, "DEBUG", False)  # pytest env 는 DEBUG=true
    path = _bug_route()
    with caplog.at_level(logging.DEBUG):
        response = TestClient(main.app).get(path.replace("{item_id}", "7"))

    assert response.status_code == 500
    assert response.json() == _BODY_500
    assert _tracebacks(caplog) == ["[UnhandledException] RuntimeError"]
    record = next(r for r in caplog.records if r.exc_info)
    assert record.path == path  # route template — 기존 처리기의 로그 형식 그대로


def test_exception_inside_another_middleware_is_caught(monkeypatch, caplog):
    """사용자 미들웨어(UserInfo) 안에서 난 예외도 받는다 — 그래서 가장 바깥에 둔다."""
    import logging

    from app.core.middlewares.user_info_middleware import UserInfoMiddleware

    async def explode(self, request, call_next):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(main.app_settings, "DEBUG", False)
    monkeypatch.setattr(UserInfoMiddleware, "dispatch", explode)
    monkeypatch.setattr(main.app, "middleware_stack", None)  # 새 dispatch 로 다시 조립
    with caplog.at_level(logging.DEBUG):
        response = TestClient(main.app).get("/health")

    assert response.status_code == 500
    assert response.json() == _BODY_500
    assert _tracebacks(caplog) == ["[UnhandledException] RuntimeError"]


def test_debug_mode_reraises(monkeypatch):
    """DEBUG=true 는 지금처럼 다시 던진다(개발 중 오류 화면·테스트 클라이언트의 예외)."""
    import pytest

    monkeypatch.setattr(main.app_settings, "DEBUG", True)
    path = _bug_route()

    with pytest.raises(RuntimeError):
        TestClient(main.app).get(path.replace("{item_id}", "7"))


def test_unhandled_exception_middleware_is_the_outermost_user_middleware():
    """등록 순서 고정 — 가장 나중에 등록한 것이 가장 바깥(user_middleware[0])이다."""
    first = main.app.user_middleware[0]
    assert first.kwargs.get("dispatch") is main.answer_unhandled_exception


BODY_KEYS = {"error_code", "message", "detail"}


def test_405_carries_allow_with_the_route_methods():
    client = TestClient(main.app)

    response = client.delete("/health")

    assert response.status_code == 405
    route = next(r for r in main.app.routes if isinstance(r, APIRoute) and r.path == "/health")
    allowed = {m.strip() for m in response.headers["allow"].split(",")}
    assert allowed == route.methods
    body = response.json()
    assert set(body) == BODY_KEYS
    assert body["error_code"] == "HTTP_405"
    assert body["detail"] is None


def _app_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    main._register_exception_handlers(app)

    @app.get("/probe")
    async def probe():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_fastapi_http_exception_headers_reach_the_response():
    client = _app_raising(
        HTTPException(
            status_code=401, detail="no", headers={"WWW-Authenticate": "Bearer", "X-Probe": "1"}
        )
    )

    response = client.get("/probe")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["x-probe"] == "1"
    assert response.json() == {"error_code": "HTTP_401", "message": "no", "detail": None}


def test_starlette_http_exception_headers_reach_the_response():
    client = _app_raising(StarletteHTTPException(status_code=429, headers={"Retry-After": "7"}))

    response = client.get("/probe")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert set(response.json()) == BODY_KEYS


def test_http_exception_without_headers_still_works():
    client = _app_raising(HTTPException(status_code=418, detail="teapot"))

    response = client.get("/probe")

    assert response.status_code == 418
    assert response.json() == {"error_code": "HTTP_418", "message": "teapot", "detail": None}


def test_api_401_carries_www_authenticate_bearer():
    """앱 고유 401(UnauthorizedException 계열)도 RFC 9110 §15.5.2 의 `WWW-Authenticate` 를 싣는다.

    토큰이 없거나 위조면 `get_current_principal` 이 UnauthorizedException 을 올린다(auto_error=False).
    그 예외가 헤더 없이 나가 401 이 계약을 어기고 있었다.
    """
    client = TestClient(main.app)
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert set(response.json()) == BODY_KEYS


@pytest.mark.parametrize(
    "exc",
    [RedisConnectionError("Error 111 connecting to cache:6379. refused"), RedisTimeoutError("t")],
)
def test_redis_connection_errors_become_503_once(exc, caplog):
    app = FastAPI()
    main._register_exception_handlers(app)

    @app.post("/probe")
    async def probe():
        raise exc

    # raise_server_exceptions=True(기본) — 예외가 핸들러 밖으로 다시 올라오면 여기서 터진다.
    with caplog.at_level(logging.ERROR):
        response = TestClient(app).post("/probe")
    assert response.status_code == 503
    assert response.json() == {
        "error_code": "SERVICE_UNAVAILABLE",
        "message": "서비스가 일시적으로 사용 불가능합니다.",
        "detail": None,
    }
    assert "cache:6379" not in response.text
    assert sum(1 for r in caplog.records if r.exc_info) == 1


class _Payload(BaseModel):
    id: UUID
    aware_at: datetime
    naive_at: datetime
    amount: Decimal
    ratio: float
    note: str | None
    tags: list[str]


_SAMPLE = _Payload(
    id=UUID("12345678-1234-5678-1234-567812345678"),
    aware_at=datetime(2026, 8, 10, 12, 34, 56, 789012, tzinfo=UTC),
    naive_at=datetime(2026, 8, 10, 12, 34, 56, 789012),
    amount=Decimal("10.50"),
    ratio=0.5,
    note=None,
    tags=["가", "b"],
)


# ORJSONResponse 를 쓰던 시점에 실측한 바이트. 전환 후에도 동일해야 한다.
_EXPECTED = (
    b'{"id":"12345678-1234-5678-1234-567812345678",'
    b'"aware_at":"2026-08-10T12:34:56.789012Z",'
    b'"naive_at":"2026-08-10T12:34:56.789012",'
    b'"amount":"10.50",'
    b'"ratio":0.5,'
    b'"note":null,'
    b'"tags":["\xea\xb0\x80","b"]}'
)


def test_response_bytes_are_unchanged():
    """response_model 이 있는 응답의 raw 바이트가 이전 직렬화와 동일하다."""
    app = FastAPI()

    @app.get("/x", response_model=_Payload)
    async def x() -> _Payload:
        return _SAMPLE

    resp = TestClient(app).get("/x")

    assert resp.headers["content-type"] == "application/json"
    assert resp.content == _EXPECTED


@pytest.mark.parametrize(
    "detail",
    [
        pytest.param({"id": "abc"}, id="primitive"),
        pytest.param({"when": datetime(2026, 8, 10, tzinfo=UTC)}, id="datetime"),
        pytest.param({"id": UUID(int=1)}, id="uuid"),
    ],
)
def test_error_handler_survives_non_primitive_detail(detail: Any):
    """에러 응답의 detail 은 Any 라 원시 타입이 아닐 수 있다.

    예전에는 ORJSONResponse 가 datetime/UUID 를 알아서 처리해줬다. 기본
    JSONResponse 는 그렇지 않아 `model_dump(mode="json")` 로 Pydantic 이 먼저
    JSON 안전 값으로 바꿔야 한다. 그 단계를 빠뜨리면 핸들러가 TypeError 로 터진다.

    **실제 등록된 예외 핸들러를 태운다.** 모델만 따로 검사하면 핸들러가 mode="json"
    을 빠뜨려도 통과해버린다(전환 중 실제로 그랬다).
    """
    from main import _register_exception_handlers

    app = FastAPI()
    _register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppException(detail=detail)

    resp = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert resp.status_code == 500, "핸들러가 응답을 만들지 못했다(직렬화 실패 가능)"
    body = resp.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    for value in body["detail"].values():
        assert isinstance(value, str), "JSON 안전 값으로 변환되지 않았다"
