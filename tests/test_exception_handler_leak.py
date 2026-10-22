"""전역 예외 핸들러는 raw 예외 본문을 응답에 담지 않는다 (계획서 §8, C-5).

DEBUG 에서만 노출한다 해도 개발 환경의 예외 메시지에는 DSN·쿼리·입력값이 그대로
실려 온다. 응답에는 안정적인 error code 만 남기고, 로그에는 raw path 대신 route
template 을 남긴다(경로에 박힌 식별자가 로그로 새지 않도록).
"""

import inspect

from fastapi.testclient import TestClient

import main

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
    """4xx 는 WARNING 이고, 클라이언트가 보낸 값이 담긴 detail 은 로그에 싣지 않는다 (F-013)."""
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


# ------------------------------------------------------------------ integration-e2e ADR-013 (P-003)
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
