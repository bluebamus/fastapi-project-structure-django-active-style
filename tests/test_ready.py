"""`/ready` readiness 엔드포인트 (Phase 1, service-hardening 단계 E).

`/health` 는 프로세스가 살아있는지만 답한다(liveness). `/ready` 는 의존 자원인
DB 와 Redis 까지 확인해 트래픽을 받아도 되는지 답한다(readiness). DB 가 죽었을 때 200 을
돌려주면 로드밸런서가 죽은 인스턴스로 트래픽을 계속 보낸다.

DB 왕복 자체는 `app/core/db/session.py` 의 `ping_writer_db()` **하나**가 소유한다.
엔드포인트가 `SELECT 1` 을 직접 들고 있으면 "어느 엔진을 · 몇 초 안에 본다" 는
결정이 두 곳으로 갈라지고, 한쪽만 고치는 사고가 난다.

오류 응답에 DSN·SQL·예외 메시지를 담지 않는다 (C-5).
"""

import asyncio
import functools
import inspect

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import main
from app.core import redis as redis_module
from app.core.db import session as db_session_module
from main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def reachable_db(monkeypatch):
    """DB 점검이 성공하는 상황."""

    async def _ok(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "ping_writer_db", _ok)


class _FakeRedis:
    """`ping()` 만 가진 가짜 클라이언트 — lifespan 없이 `app.state.redis` 에 둔다."""

    def __init__(self, error: Exception | None = None, hang: bool = False):
        self.error = error
        self.hang = hang
        self.pings = 0

    async def ping(self):
        self.pings += 1
        if self.hang:
            await asyncio.sleep(10)
        if self.error is not None:
            raise self.error
        return True


@pytest.fixture(autouse=True)
def reachable_redis(monkeypatch):
    """기본은 Redis 정상. 테스트 클라이언트는 lifespan 을 돌리지 않으므로 직접 둔다."""
    fake = _FakeRedis()
    monkeypatch.setattr(app.state, "redis", fake, raising=False)
    return fake


@pytest.fixture
def unreachable_db(monkeypatch):
    """DB 점검이 실패하는 상황 — 드라이버 예외에 DSN 과 자격증명이 실려 온다."""

    async def _boom(*args, **kwargs):
        raise RuntimeError("mysql+aiomysql://root:sup3rs3cret@db:3306/app 접속 실패")

    monkeypatch.setattr(main, "ping_writer_db", _boom)


async def test_ready_returns_200_when_db_reachable(client, reachable_db):
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    # 사양: 200 응답은 HealthResponse 계약(status + version)을 따른다.
    assert "version" in body


async def test_ready_returns_503_when_db_unreachable(client, unreachable_db):
    response = await client.get("/ready")

    assert response.status_code == 503
    # 사양: 실패는 프로젝트 표준 오류 응답(ErrorResponse)을 쓴다.
    body = response.json()
    assert body["error_code"]
    assert body["detail"] is None


async def test_ready_error_does_not_leak_dsn_or_credentials(client, unreachable_db):
    """503 응답 본문에 DSN·자격증명·예외 메시지가 없어야 한다 (C-5)."""
    body = (await client.get("/ready")).text

    for leaked in ("sup3rs3cret", "aiomysql", "root", "3306"):
        assert leaked not in body, f"응답에 '{leaked}' 가 노출됐습니다."


async def test_health_does_not_touch_the_db(client, monkeypatch):
    """liveness 는 의존 자원을 건드리지 않는다 — DB 가 흔들려도 프로세스는 살아 있다."""

    async def _must_not_be_called(*args, **kwargs):
        raise AssertionError("/health 가 DB 를 건드렸습니다.")

    monkeypatch.setattr(main, "ping_writer_db", _must_not_be_called)

    assert (await client.get("/health")).status_code == 200


def test_ready_is_in_openapi_with_health_tag():
    spec = app.openapi()

    assert "/ready" in spec["paths"], "/ready 가 OpenAPI 에 없습니다."
    operation = spec["paths"]["/ready"]["get"]
    assert operation["tags"] == ["Health"]
    assert operation["operationId"] == "getReadiness"


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_liveness_and_readiness_are_separate(path):
    """둘은 서로 다른 엔드포인트다 — 하나로 합치지 않는다."""
    assert path in app.openapi()["paths"]


def test_ready_declares_503_response():
    operation = app.openapi()["paths"]["/ready"]["get"]

    assert "503" in operation["responses"]


def test_ready_delegates_db_check_to_the_shared_helper():
    """`/ready` 는 `SELECT 1` 을 직접 들고 있지 않다 — writer 점검은 한 곳에 있다."""
    source = inspect.getsource(main)

    assert "ping_writer_db()" in source, "/ready 가 공용 헬퍼를 쓰지 않습니다."
    # 설명용 docstring 언급은 괜찮다. 막으려는 건 **실행되는** 두 번째 점검이다.
    assert 'text("SELECT 1")' not in source, "writer 점검이 main.py 에 중복돼 있습니다."


def test_readiness_timeout_is_bounded():
    """DB 가 응답하지 않을 때 readiness 가 무한정 매달리면 안 된다."""
    assert 0 < db_session_module.READINESS_TIMEOUT_SECONDS <= 5


class _FakeConnection:
    def __init__(self, executed):
        self._executed = executed

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def execute(self, statement):
        self._executed.append(str(statement))


class _FakeEngine:
    def __init__(self):
        self.executed: list[str] = []

    def connect(self):
        return _FakeConnection(self.executed)


async def test_ping_writer_db_runs_select_one_on_the_writer(monkeypatch):
    """replica 가 아니라 writer 를 본다 — 쓰기를 못 받는 인스턴스는 준비된 게 아니다."""
    fake = _FakeEngine()
    monkeypatch.setattr(db_session_module, "engine", fake)

    await db_session_module.ping_writer_db()

    assert fake.executed == ["SELECT 1"]


async def test_ping_writer_db_times_out(monkeypatch):
    """DB 가 응답하지 않으면 timeout 으로 끊는다."""

    class _HangingConnection:
        async def __aenter__(self):
            await asyncio.sleep(10)

        async def __aexit__(self, *exc_info):
            return False

    class _HangingEngine:
        def connect(self):
            return _HangingConnection()

    monkeypatch.setattr(db_session_module, "engine", _HangingEngine())

    with pytest.raises(TimeoutError):
        await db_session_module.ping_writer_db(timeout=0.05)


# --------------------------------------------------------------------------- Redis (단계 E)


async def test_ready_pings_both_db_and_redis(client, reachable_db, reachable_redis):
    """Redis 는 필수다(ADR-008) — 200 은 Redis 왕복까지 성공했다는 뜻이어야 한다."""
    response = await client.get("/ready")

    assert response.status_code == 200
    assert reachable_redis.pings == 1


async def test_ready_returns_503_when_redis_ping_fails(client, reachable_db, monkeypatch):
    fake = _FakeRedis(error=ConnectionError("redis://:r3d1s-s3cret@cache:6379/0 접속 실패"))
    monkeypatch.setattr(app.state, "redis", fake, raising=False)

    response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "NOT_READY"
    assert body["detail"] is None
    for leaked in ("r3d1s-s3cret", "6379", "cache"):
        assert leaked not in response.text, f"응답에 '{leaked}' 가 노출됐습니다."


async def test_ready_returns_503_when_redis_times_out(client, reachable_db, monkeypatch):
    """Redis 가 응답하지 않으면 상한에서 끊고 503 — 무한정 매달리지 않는다."""
    monkeypatch.setattr(app.state, "redis", _FakeRedis(hang=True), raising=False)
    monkeypatch.setattr(
        main, "ping_redis", functools.partial(redis_module.ping_redis, timeout=0.05)
    )

    response = await asyncio.wait_for(client.get("/ready"), timeout=5)

    assert response.status_code == 503


async def test_ready_returns_503_when_redis_client_is_missing(client, reachable_db, monkeypatch):
    """lifespan 밖(클라이언트 없음)을 준비 완료로 착각하지 않는다."""
    monkeypatch.setattr(app.state, "redis", None, raising=False)

    assert (await client.get("/ready")).status_code == 503


async def test_ready_logs_only_the_failure_type(client, reachable_db, monkeypatch, caplog):
    fake = _FakeRedis(error=ConnectionError("r3d1s-s3cret"))
    monkeypatch.setattr(app.state, "redis", fake, raising=False)

    with caplog.at_level("WARNING", logger=main.logger.name):
        await client.get("/ready")

    assert "r3d1s-s3cret" not in caplog.text
    assert "ConnectionError" in caplog.text


async def test_ping_redis_times_out():
    request = _request_with(_FakeRedis(hang=True))

    with pytest.raises(TimeoutError):
        await redis_module.ping_redis(request, timeout=0.05)


def test_redis_readiness_uses_the_same_bound_as_the_db():
    """DB 와 Redis 의 상한이 두 숫자로 갈라지지 않는다."""
    default = inspect.signature(redis_module.ping_redis).parameters["timeout"].default
    assert default == db_session_module.READINESS_TIMEOUT_SECONDS


def _request_with(redis):
    from types import SimpleNamespace

    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
