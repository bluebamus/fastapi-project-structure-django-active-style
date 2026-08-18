"""lifespan 자원 회수 (Phase 1).

startup 이 실패하면 `yield` 에 도달하지 못한다. 정리 코드가 `yield` 뒤에만 있으면
그 경로에서 엔진이 회수되지 않고, 기동 실패를 재시도하는 컨테이너에서 커넥션이
계속 쌓인다. 성공/실패 어느 쪽이든 회수는 한 번 일어나야 한다.
"""

import pytest

import main


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

    monkeypatch.setattr(main, "dispose_engine", fake_dispose)
    monkeypatch.setattr(main, "access_log_tasks", _FakeTasks(calls))
    return calls


async def test_normal_shutdown_drains_then_disposes(recorded, monkeypatch):
    async def noop_create():
        recorded.append("create")

    monkeypatch.setattr(main, "create_db_tables", noop_create)

    async with main.lifespan(main.app):
        assert "dispose" not in recorded, "yield 중에 이미 정리됐습니다."

    assert recorded[-2:] == ["drain", "dispose"]


async def test_startup_failure_still_releases_resources(recorded, monkeypatch):
    """테이블 생성이 실패해도 drain/dispose 는 반드시 수행된다."""

    async def boom():
        raise RuntimeError("테이블 생성 실패")

    monkeypatch.setattr(main, "create_db_tables", boom)
    monkeypatch.setattr(main.app_settings, "DEBUG", True)

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

    monkeypatch.setattr(main, "create_db_tables", noop_create)

    async with main.lifespan(main.app):
        pass

    assert recorded.count("dispose") == 1
    assert recorded.count("drain") == 1
