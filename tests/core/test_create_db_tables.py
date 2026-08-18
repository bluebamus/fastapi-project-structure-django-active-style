"""`create_db_tables()` 의 발견 재사용 계약 (INV-5, ledger F-001).

DEBUG 기동 경로가 모델을 **다시 발견**하면 런타임과 Alembic 이 서로 다른 앱 목록을
볼 수 있다. main.py 가 이미 `AppRegistry.discover()` + `import_models()` 로 채워둔
`Base.metadata` 를 그대로 써야 하며, 여기서 두 번째 스캔을 돌리면 안 된다.
"""

import pytest

from app.core.db import session as session_module
from app.core.models.models_base import Base
from app.core.registry import AppRegistry


class _FakeConnection:
    def __init__(self, calls: list[object]) -> None:
        self._calls = calls

    async def run_sync(self, fn, *args, **kwargs):
        self._calls.append(fn)


class _FakeEngine:
    """`engine.begin()` 만 흉내내는 최소 대역 — 실제 DB 없이 경로를 태운다."""

    def __init__(self) -> None:
        self.run_sync_calls: list[object] = []

    def begin(self):
        connection = _FakeConnection(self.run_sync_calls)

        class _Ctx:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


@pytest.fixture
def fake_engine(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(session_module, "engine", engine)
    return engine


@pytest.fixture
def prepared_metadata():
    """main.py 와 동일하게 registry 로 metadata 를 미리 채운다(선행 조건)."""
    registry = AppRegistry()
    registry.discover()
    registry.import_models()
    assert Base.metadata.tables, "registry 가 metadata 를 채우지 못했습니다."
    return registry


@pytest.fixture
def discover_spy(monkeypatch, prepared_metadata):
    """`AppRegistry.discover()` 호출 횟수를 센다(선행 적재 이후부터)."""
    calls: list[str] = []
    original = AppRegistry.discover

    def counted(self, package=None):
        calls.append(package or "app.features")
        return original(self) if package is None else original(self, package)

    monkeypatch.setattr(AppRegistry, "discover", counted)
    return calls


async def test_create_db_tables_does_not_rediscover(fake_engine, discover_spy):
    """테이블 생성은 새 발견을 유발하지 않는다 (F-001)."""
    await session_module.create_db_tables()

    assert discover_spy == [], (
        "create_db_tables() 가 AppRegistry.discover() 를 다시 호출했습니다. "
        "main.py 가 만든 동일 registry 의 metadata 를 재사용해야 합니다."
    )
    assert fake_engine.run_sync_calls, "create_all 이 실행되지 않았습니다."


async def test_create_db_tables_uses_prepared_metadata(fake_engine, discover_spy):
    """이미 채워진 Base.metadata 를 그대로 쓴다 — 테이블 목록이 보존된다."""
    before = set(Base.metadata.tables)

    await session_module.create_db_tables()

    assert set(Base.metadata.tables) == before


async def test_create_db_tables_rejects_empty_metadata(fake_engine, monkeypatch):
    """metadata 가 비어 있으면 0개 테이블을 조용히 만들지 않고 실패한다."""
    empty = type(Base.metadata)()
    monkeypatch.setattr(session_module, "Base", type("B", (), {"metadata": empty}))

    with pytest.raises(RuntimeError, match="metadata"):
        await session_module.create_db_tables()

    assert not fake_engine.run_sync_calls, "실패 경로에서 create_all 이 실행됐습니다."
