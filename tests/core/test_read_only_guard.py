"""read-only 세션의 쓰기 차단은 `DB_ROUTER_ENABLED` 와 무관하다 (ledger F-003).

지금까지 차단은 `RoutingSession.get_bind()` 안에만 있었다. 그래서 라우터가 꺼진
구성(단일 서버 기본값)과 background 세션 팩토리에서는 `mark_read_only()` 를 불러도
쓰기가 그냥 통과했다. read-only 는 replica 라우팅 옵션이 아니라 **Dependency 계약**이다.

판별은 default-deny 다. SELECT 로 확실히 읽기라고 판단되는 것만 통과시키고, `WITH`·
잠금 획득·multi-statement·판별 불가 문장은 read-only 에서 거부한다.

테스트 모델은 별도 `DeclarativeBase` 를 쓴다 — 공유 metadata 와 migration 을 오염시키지
않기 위해서다(workflow-guide §14).
"""

import pytest
import pytest_asyncio
from sqlalchemy import Integer, String, delete, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    assert_writable,
    create_routing_sessionmaker,
    is_read_only,
    mark_read_only,
)


class _TestBase(DeclarativeBase):
    """테스트 전용 metadata — 앱 Base 와 분리한다."""


class Widget(_TestBase):
    __tablename__ = "guard_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest_asyncio.fixture(params=["router_off", "router_on"])
async def maker(request):
    """라우터 on/off 두 구성을 같은 계약으로 검증한다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    if request.param == "router_on":
        router = DatabaseRouter(writer=engine, readers=[], sticky_after_write=True)
        factory = create_routing_sessionmaker(router)
    else:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with factory() as seed:
        await seed.execute(insert(Widget).values(id=1, name="seed"))
        await seed.commit()

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def read_only(maker):
    async with maker() as session:
        mark_read_only(session)
        yield session


@pytest_asyncio.fixture
async def writable(maker):
    async with maker() as session:
        yield session


async def _rows(factory) -> int:
    async with factory() as session:
        return len((await session.execute(select(Widget))).scalars().all())


# ---------------------------------------------------------------- 중앙 API


async def test_is_read_only_reports_marking(maker):
    async with maker() as session:
        assert is_read_only(session) is False
        mark_read_only(session)
        assert is_read_only(session) is True


async def test_assert_writable_raises_only_when_marked(maker):
    async with maker() as session:
        assert_writable(session)  # 표시 전에는 통과
        mark_read_only(session)
        with pytest.raises(ReadOnlyRoutingError):
            assert_writable(session)


# ---------------------------------------------------------------- 쓰기 차단


async def test_orm_flush_is_blocked(read_only, maker):
    read_only.add(Widget(name="orm"))

    with pytest.raises(ReadOnlyRoutingError):
        await read_only.flush()

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize(
    "statement_name",
    ["insert", "update", "delete"],
)
async def test_core_dml_is_blocked(read_only, maker, statement_name):
    statement = {
        "insert": insert(Widget).values(name="core"),
        "update": update(Widget).values(name="changed"),
        "delete": delete(Widget),
    }[statement_name]

    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(statement)

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO guard_widgets (name) VALUES ('raw')",
        "UPDATE guard_widgets SET name = 'raw'",
        "DELETE FROM guard_widgets",
        "  insert into guard_widgets (name) values ('lower')",
        "/* comment */ UPDATE guard_widgets SET name = 'x'",
        "DROP TABLE guard_widgets",
        "CREATE TABLE t2 (id INT)",
    ],
)
async def test_raw_dml_and_ddl_are_blocked(read_only, maker, sql):
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text(sql))

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM guard_widgets FOR UPDATE",
        "SELECT * FROM guard_widgets LOCK IN SHARE MODE",
        "WITH c AS (SELECT 1) SELECT * FROM c",
        "SELECT 1; DELETE FROM guard_widgets",
        "CALL some_procedure()",
        "지원하지 않는 문장",
    ],
)
async def test_unknown_or_locking_statements_are_denied_by_default(read_only, sql):
    """default-deny — 확실히 읽기라고 판단되지 않으면 거부한다."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text(sql))


# ---------------------------------------------------------------- 읽기 허용


async def test_orm_select_is_allowed(read_only):
    rows = (await read_only.execute(select(Widget))).scalars().all()

    assert [row.name for row in rows] == ["seed"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM guard_widgets",
        "  select id from guard_widgets  ",
        "SELECT 1;",
        "/* 주석 */ SELECT name FROM guard_widgets",
    ],
)
async def test_raw_select_is_allowed(read_only, sql):
    await read_only.execute(text(sql))


# ---------------------------------------------------------------- 대조군


async def test_writable_session_can_write(writable, maker):
    await writable.execute(insert(Widget).values(name="ok"))
    await writable.commit()

    assert await _rows(maker) == 2


async def test_writable_session_raw_dml_succeeds(writable, maker):
    await writable.execute(text("INSERT INTO guard_widgets (name) VALUES ('raw-ok')"))
    await writable.commit()

    assert await _rows(maker) == 2
