"""Raw primitive 를 실제 MySQL 에 대고 검증한다 (계획서 §5·§10 Phase 6).

SQLite 단위 테스트는 결과 의미(0행/복수행/NULL)를 빠르게 못박지만, **드라이버 계약은
검증하지 못한다**. rowcount 가 실제로 무엇을 돌려주는지, `IN` 확장 바인딩이 방언에서
어떻게 펼쳐지는지, multi-statement 를 드라이버가 어떻게 다루는지는 여기서만 알 수 있다.

Phase 2 의 read-only 계약이 Raw 경로에도 그대로 걸리는지도 함께 본다 — 두 Phase 가
따로 통과하고 합쳐서 새는 경우를 막는다.
"""

import pytest
import pytest_asyncio
from sqlalchemy import bindparam, text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db.router import ReadOnlyRoutingError, mark_read_only
from app.core.repositories.raw_crud_base import RawCRUDBase, RawSQLContractError

from .conftest import ASYNC_URL

pytestmark = pytest.mark.mysql

_CREATE = text(
    """
    CREATE TABLE IF NOT EXISTS raw_widgets (
        id INT PRIMARY KEY,
        name VARCHAR(50),
        score INT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
)
_SEED = text(
    "INSERT INTO raw_widgets (id, name, score) VALUES "
    "(1, 'alpha', 10), (2, 'beta', 20), (3, 'gamma', NULL)"
)


@pytest_asyncio.fixture
async def raw_session_factory():
    """Raw 전용 소형 스키마를 매번 새로 만든다(앱 모델과 섞지 않는다)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = create_async_engine(ASYNC_URL, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            await session.execute(text("DROP TABLE IF EXISTS raw_widgets"))
            await session.execute(_CREATE)
            await session.execute(_SEED)
            await session.commit()
        yield maker
        async with maker() as session:
            await session.execute(text("DROP TABLE IF EXISTS raw_widgets"))
            await session.commit()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def raw(raw_session_factory):
    async with raw_session_factory() as session:
        yield RawCRUDBase(session)


# ------------------------------------------------------------------ 결과 의미


async def test_fetch_one_on_mysql(raw):
    row = await raw.fetch_one(text("SELECT name, score FROM raw_widgets WHERE id = :id"), {"id": 1})

    assert dict(row) == {"name": "alpha", "score": 10}


async def test_fetch_one_rejects_multiple_rows_on_mysql(raw):
    with pytest.raises(MultipleResultsFound):
        await raw.fetch_one(text("SELECT id FROM raw_widgets"))


async def test_fetch_all_returns_empty_on_mysql(raw):
    assert await raw.fetch_all(text("SELECT id FROM raw_widgets WHERE id > 100")) == []


async def test_fetch_scalar_null_and_missing_are_both_none_on_mysql(raw):
    """MySQL 에서도 0행과 SQL NULL 은 똑같이 None 이다(의도된 계약)."""
    null_value = await raw.fetch_scalar(
        text("SELECT score FROM raw_widgets WHERE id = :id"), {"id": 3}
    )
    no_row = await raw.fetch_scalar(
        text("SELECT score FROM raw_widgets WHERE id = :id"), {"id": 999}
    )

    assert null_value is None
    assert no_row is None


# ------------------------------------------------------------------ rowcount


async def test_execute_rowcount_is_real_on_mysql(raw):
    """드라이버가 돌려주는 실제 rowcount 를 그대로 쓴다."""
    affected = await raw.execute(
        text("UPDATE raw_widgets SET score = :score WHERE id <= :id"), {"score": 99, "id": 2}
    )

    assert affected == 2


async def test_execute_rowcount_zero_on_mysql(raw):
    assert await raw.execute(text("DELETE FROM raw_widgets WHERE id = :id"), {"id": 999}) == 0


async def test_execute_does_not_commit_on_mysql(raw, raw_session_factory):
    """commit 은 쓰기 View 소유다 — Repository 가 하지 않는다 (ADR-004)."""
    await raw.execute(text("DELETE FROM raw_widgets WHERE id = :id"), {"id": 1})
    await raw.session.rollback()

    async with raw_session_factory() as other:
        remaining = await RawCRUDBase(other).fetch_scalar(text("SELECT COUNT(*) FROM raw_widgets"))

    assert remaining == 3


# ------------------------------------------------------------------ 바인딩


async def test_expanding_in_binding_on_mysql(raw):
    """`IN` 은 문자열 조립이 아니라 expanding bindparam 으로 넘긴다."""
    statement = text("SELECT name FROM raw_widgets WHERE id IN :ids ORDER BY id").bindparams(
        bindparam("ids", expanding=True)
    )

    rows = await raw.fetch_all(statement, {"ids": [1, 3]})

    assert [row["name"] for row in rows] == ["alpha", "gamma"]


async def test_bound_value_is_not_interpreted_as_sql_on_mysql(raw):
    """주입 시도는 그냥 '값' 으로 처리된다."""
    injected = "alpha' OR '1'='1"

    rows = await raw.fetch_all(
        text("SELECT id FROM raw_widgets WHERE name = :name"), {"name": injected}
    )

    assert rows == []


async def test_multi_statement_is_rejected_before_reaching_mysql(raw):
    with pytest.raises(RawSQLContractError):
        await raw.fetch_all(text("SELECT 1; DROP TABLE raw_widgets"))


# ------------------------------------------------------------------ read-only × Raw


async def test_read_only_session_blocks_raw_dml_on_mysql(raw_session_factory):
    """Phase 2 의 read-only 계약이 Raw 경로에도 걸린다."""
    async with raw_session_factory() as session:
        mark_read_only(session)
        primitive = RawCRUDBase(session)

        with pytest.raises(ReadOnlyRoutingError):
            await primitive.execute(text("DELETE FROM raw_widgets WHERE id = :id"), {"id": 1})

        await session.rollback()

    async with raw_session_factory() as other:
        remaining = await RawCRUDBase(other).fetch_scalar(text("SELECT COUNT(*) FROM raw_widgets"))

    assert remaining == 3, "read-only 세션에서 Raw DML 이 실제로 반영됐습니다."


async def test_read_only_session_allows_raw_select_on_mysql(raw_session_factory):
    async with raw_session_factory() as session:
        mark_read_only(session)

        rows = await RawCRUDBase(session).fetch_all(text("SELECT id FROM raw_widgets ORDER BY id"))

    assert [row["id"] for row in rows] == [1, 2, 3]
