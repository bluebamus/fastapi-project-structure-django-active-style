"""접속 로그 미들웨어 — 수집 대상 판정, 민감 쿼리 마스킹, 세션 쿠키·사용자 id 기록, sink 등록과
sink 실패 로그.
"""

import httpx
import pytest
from fastapi import FastAPI

from app.core.middlewares import user_info_middleware as module
from app.core.middlewares.access_log_sink import get_access_log_sink, set_access_log_sink
from app.core.middlewares.background_tasks import BackgroundTaskRunner
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.dependencies import CurrentPrincipal
from tests.auth_headers import USER_ID, user_headers


@pytest.fixture
def recorded(monkeypatch):
    """미들웨어가 저장하려 한 접속 로그 dict 목록(실제 sink 대신 수집)."""
    saved: list[dict] = []

    class CaptureSink:
        async def save(self, data: dict) -> None:
            saved.append(data)

    runner = BackgroundTaskRunner()
    monkeypatch.setattr(module, "access_log_tasks", runner)
    original = get_access_log_sink()
    set_access_log_sink(CaptureSink())
    yield saved, runner
    set_access_log_sink(original)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(module.UserInfoMiddleware, ip_resolver=ClientIPResolver(0))

    @app.get("/ok")
    async def ok():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    @app.get("/whoami")
    async def whoami(principal: CurrentPrincipal):
        return {"id": principal.id}

    return app


async def _get(path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, **kwargs)


async def test_unhandled_exception_is_recorded_as_500(recorded):
    saved, runner = recorded

    response = await _get("/boom")
    await runner.drain()

    assert response.status_code == 500
    assert [entry["response_status"] for entry in saved] == [500]
    assert saved[0]["request_path"] == "/boom"
    assert saved[0]["response_time_ms"] >= 0


async def test_sensitive_query_values_are_masked(recorded):
    saved, runner = recorded

    await _get(
        "/ok",
        params=[
            ("page", "2"),
            ("token", "t0k3n"),
            ("Password", "hunter2"),
            ("code", "oauth-code"),
            ("q", "a b"),
        ],
    )
    await runner.drain()

    query = saved[0]["query_string"]
    assert query == "page=2&token=***&Password=***&code=***&q=a+b"
    for secret in ("t0k3n", "hunter2", "oauth-code"):
        assert secret not in query


async def test_masking_follows_the_setting(recorded, monkeypatch):
    saved, runner = recorded
    monkeypatch.setattr(
        module.middleware_settings, "ACCESS_LOG_SENSITIVE_QUERY_KEYS", ["custom_secret"]
    )

    await _get("/ok", params={"custom_secret": "x", "token": "kept"})
    await runner.drain()

    assert saved[0]["query_string"] == "custom_secret=***&token=kept"


async def test_query_string_is_none_without_params(recorded):
    saved, runner = recorded

    await _get("/ok")
    await runner.drain()

    assert saved[0]["query_string"] is None


async def test_session_id_is_read_from_the_configured_cookie(recorded, monkeypatch):
    saved, runner = recorded
    monkeypatch.setattr(module.session_settings, "SESSION_COOKIE_NAME", "my_session")

    await _get("/ok", headers={"Cookie": "my_session=abc; session_id=wrong"})
    await runner.drain()

    assert saved[0]["session_id"] == "abc"


async def test_authenticated_request_records_user_id(recorded):
    """인증 의존성(`get_current_principal`)이 정한 주체 id 가 접속 로그에 남는다."""
    saved, runner = recorded

    response = await _get("/whoami", headers=user_headers())
    await runner.drain()

    assert response.status_code == 200
    assert saved[0]["user_id"] == USER_ID


async def test_anonymous_request_records_no_user_id(recorded):
    saved, runner = recorded

    await _get("/ok")
    await _get("/whoami")  # 토큰 없음 — 401, 주체 없음
    await runner.drain()

    assert [entry["user_id"] for entry in saved] == [None, None]


@pytest.mark.parametrize(
    ("enabled", "url", "stored"),
    [
        (False, "/ok", False),  # ACCESS_LOG_ENABLED=false 면 아무것도 저장하지 않는다
        (True, "/skip", False),  # 제외 경로는 정확 일치
        (True, "/skip/child", True),  # 접두사는 제외가 아니다
        (True, "/app.css", False),  # 제외 확장자는 접미사 일치
        (True, "/ok", True),
    ],
)
async def test_only_enabled_and_not_excluded_requests_are_stored(
    recorded, monkeypatch, enabled, url, stored
):
    """문서가 말하는 저장 범위(``_should_skip``) — 로컬 .env 값과 무관하게 고정한다."""
    saved, runner = recorded
    monkeypatch.setattr(module.middleware_settings, "ACCESS_LOG_ENABLED", enabled)
    monkeypatch.setattr(module.middleware_settings, "ACCESS_LOG_EXCLUDE_PATHS", ["/skip"])
    monkeypatch.setattr(module.middleware_settings, "ACCESS_LOG_EXCLUDE_EXTENSIONS", [".css"])

    await _get(url)
    await runner.drain()

    assert [entry["request_path"] for entry in saved] == ([url] if stored else [])


async def test_sink_registration_roundtrip():
    """set_access_log_sink / get_access_log_sink roundtrip works and delegates calls."""
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )

    original = get_access_log_sink()

    calls = []

    class StubSink:
        async def save(self, data: dict) -> None:
            calls.append(data)

    stub = StubSink()
    try:
        set_access_log_sink(stub)
        assert get_access_log_sink() is stub
        await get_access_log_sink().save({"x": 1})
        assert calls == [{"x": 1}]
    finally:
        set_access_log_sink(original)


async def test_sink_failure_log_has_no_sql_or_bindings(caplog):
    """저장 실패 로그가 SQL·바인딩 값을 흘리지 않는다.

    sink 저장은 DB 쓰기다. 실패하면 예외 str() 에 SQL 과 바인딩된 값이 실려 오는데,
    이 로거 이름("user_info_middleware")은 SQLNoiseFilter 를 그대로 통과한다.
    기본 로그에는 예외 타입만 남기고 전문은 DEBUG 레코드로만 내보낸다.
    """
    import logging

    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.core.middlewares.user_info_middleware import UserInfoMiddleware

    sentinel = "victim-binding-sentinel@example.com"

    class Boom(Exception):
        pass

    class FailingSink:
        async def save(self, data: dict) -> None:
            raise Boom(
                "(pymysql.err.OperationalError) (1213, 'Deadlock found') "
                "[SQL: INSERT INTO user_access_log (email) VALUES (%(email)s)] "
                f"[parameters: {{'email': '{sentinel}'}}]"
            )

    original = get_access_log_sink()
    try:
        set_access_log_sink(FailingSink())
        with caplog.at_level(logging.DEBUG, logger="user_info_middleware"):
            middleware = UserInfoMiddleware.__new__(UserInfoMiddleware)
            await middleware._save_access_log({"email": sentinel})
    finally:
        set_access_log_sink(original)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "저장 실패 시 ERROR 레코드가 남아야 한다."
    for record in errors:
        message = record.getMessage()
        assert sentinel not in message, message
        assert "[SQL:" not in message, message
        assert record.exc_info is None, "ERROR 레코드의 트레이스백에도 SQL 이 실린다."
    assert any("Boom" in r.getMessage() for r in errors), "예외 타입은 남아야 진단이 된다."

    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
    assert debugs, "DEBUG 레벨에서는 전문이 남아야 한다."
    assert sentinel in " ".join(logging.Formatter().format(r) for r in debugs)
