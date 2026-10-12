"""접속 로그 미들웨어의 기록 내용 (F-008·F-009·F-010, ADR-005).

- 처리되지 않은 예외도 500 으로 기록된다(장애 요청이 기록에서 빠지지 않는다).
- query string 의 민감 키 값은 `***` 로 가려 저장된다.
- session_id 는 설정 `SESSION_COOKIE_NAME` 이름의 쿠키에서 읽는다.
- user_id 는 인증 의존성이 핸들러 실행 중에 남긴 값이다 — 응답 뒤에 읽어야 보인다(F-008, 단계 F2).
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
