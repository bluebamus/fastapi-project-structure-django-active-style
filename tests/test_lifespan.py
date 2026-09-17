"""lifespan 자원 회수 (Phase 1).

startup 이 실패하면 `yield` 에 도달하지 못한다. 정리 코드가 `yield` 뒤에만 있으면
그 경로에서 엔진이 회수되지 않고, 기동 실패를 재시도하는 컨테이너에서 커넥션이
계속 쌓인다. 성공/실패 어느 쪽이든 회수는 한 번 일어나야 한다.
"""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

import main
from app.core import resources


class _FakeRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class _FakeRedisFactory:
    @staticmethod
    def from_url(*args, **kwargs) -> _FakeRedis:
        return _FakeRedis()


class _FakeTasks:
    def __init__(self, calls):
        self._calls = calls

    async def drain(self):
        self._calls.append("drain")


@pytest.fixture
def recorded(monkeypatch):
    calls: list[str] = []

    async def fake_dispose():
        calls.append("dispose")

    async def fake_stop_logging():
        return None

    monkeypatch.setattr(resources, "dispose_engine", fake_dispose)
    monkeypatch.setattr(resources, "access_log_tasks", _FakeTasks(calls))
    monkeypatch.setattr(resources, "stop_queue_listener", fake_stop_logging)
    monkeypatch.setattr(resources, "Redis", _FakeRedisFactory)
    return calls


async def test_normal_shutdown_drains_then_disposes(recorded, monkeypatch):
    async def noop_create():
        recorded.append("create")

    monkeypatch.setattr(resources, "create_db_tables", noop_create)

    async with main.lifespan(main.app):
        assert "dispose" not in recorded, "yield 중에 이미 정리됐습니다."

    assert recorded[-2:] == ["drain", "dispose"]


async def test_startup_failure_still_releases_resources(recorded, monkeypatch):
    """테이블 생성이 실패해도 drain/dispose 는 반드시 수행된다."""

    async def boom():
        raise RuntimeError("테이블 생성 실패")

    monkeypatch.setattr(resources, "create_db_tables", boom)
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    with pytest.raises(RuntimeError, match="테이블 생성 실패"):
        async with main.lifespan(main.app):
            pytest.fail("startup 이 실패했는데 본문이 실행됐습니다.")

    assert recorded == [
        "drain",
        "dispose",
    ], f"startup 실패 경로에서 자원이 회수되지 않았습니다: {recorded}"


async def test_resources_are_released_exactly_once(recorded, monkeypatch):
    """정상 경로에서 정리가 두 번 돌지 않는다."""

    async def noop_create():
        pass

    monkeypatch.setattr(resources, "create_db_tables", noop_create)

    async with main.lifespan(main.app):
        pass

    assert recorded.count("dispose") == 1
    assert recorded.count("drain") == 1


async def test_redis_connection_failure_stops_startup(recorded, monkeypatch):
    """필수 Redis의 PING 실패는 startup을 중단하고 앞선 자원을 정리한다."""

    class _UnavailableRedis(_FakeRedis):
        async def ping(self) -> bool:
            raise RedisConnectionError("Redis unavailable")

        async def aclose(self) -> None:
            recorded.append("redis_close")

    class _UnavailableRedisFactory:
        @staticmethod
        def from_url(*args, **kwargs) -> _UnavailableRedis:
            return _UnavailableRedis()

    monkeypatch.setattr(resources, "Redis", _UnavailableRedisFactory)

    with pytest.raises(RedisConnectionError):
        async with main.lifespan(main.app):
            pytest.fail("Redis 연결이 실패했는데 애플리케이션이 시작됐다")

    assert recorded == ["redis_close", "dispose"]
    assert main.app.state.redis is None
    assert main.app.state.resources is None
