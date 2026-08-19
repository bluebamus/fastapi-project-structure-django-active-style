"""Raw SQL primitive 의 결과 의미 계약 (계획서 §5, Phase 6).

Raw 계층에서 사고는 대부분 "결과를 어떻게 줄였는가" 에서 난다. `first()` 로 복수
행을 조용히 묵인하거나, scalar 가 여러 행을 버리거나, rowcount 를 bool 로 축약하면
증상은 한참 뒤에 데이터 불일치로 나타난다. 그래서 네 primitive 의 의미를 못박는다.

| API            | 의미                                                              |
|----------------|-------------------------------------------------------------------|
| `fetch_one`    | 0행 None · 1행 RowMapping · **복수 행이면 오류**                    |
| `fetch_all`    | 0행은 빈 sequence                                                  |
| `fetch_scalar` | 0행 또는 SQL NULL 은 None · **복수 행이면 오류**                    |
| `execute`      | DML 전용, commit 하지 않음, `rowcount: int | None` (미지원 시 None) |

`fetch_scalar` 가 "0행" 과 "NULL 값" 을 구분하지 못하는 것은 **의도된 계약**이다.
구분이 필요하면 `fetch_one` 을 쓴다.

ORM Base 와는 상속 관계가 없다(C-7). 세션·예외·로깅 정책만 공유한다.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.repositories.raw_crud_base import RawCRUDBase, RawSQLContractError


@pytest_asyncio.fixture
async def raw():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await session.execute(
            text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT, score INTEGER)")
        )
        await session.execute(
            text(
                "INSERT INTO widgets (id, name, score) VALUES "
                "(1, 'alpha', 10), (2, 'beta', 20), (3, 'gamma', NULL)"
            )
        )
        await session.commit()
        yield RawCRUDBase(session)
    await engine.dispose()


# ------------------------------------------------------------------ fetch_one


async def test_fetch_one_returns_mapping(raw):
    row = await raw.fetch_one(text("SELECT id, name FROM widgets WHERE id = :id"), {"id": 1})

    assert row is not None
    assert row["name"] == "alpha"
    assert dict(row) == {"id": 1, "name": "alpha"}


async def test_fetch_one_returns_none_for_no_rows(raw):
    assert await raw.fetch_one(text("SELECT id FROM widgets WHERE id = :id"), {"id": 999}) is None


async def test_fetch_one_rejects_multiple_rows(raw):
    """복수 행을 조용히 첫 행으로 줄이지 않는다."""
    with pytest.raises(MultipleResultsFound):
        await raw.fetch_one(text("SELECT id FROM widgets"))


# ------------------------------------------------------------------ fetch_all


async def test_fetch_all_returns_all_rows(raw):
    rows = await raw.fetch_all(text("SELECT id FROM widgets ORDER BY id"))

    assert [row["id"] for row in rows] == [1, 2, 3]


async def test_fetch_all_returns_empty_sequence(raw):
    rows = await raw.fetch_all(text("SELECT id FROM widgets WHERE id > 100"))

    assert rows == []


# ------------------------------------------------------------------ fetch_scalar


async def test_fetch_scalar_returns_value(raw):
    assert await raw.fetch_scalar(text("SELECT score FROM widgets WHERE id = :id"), {"id": 2}) == 20


async def test_fetch_scalar_returns_none_for_no_rows(raw):
    assert (
        await raw.fetch_scalar(text("SELECT score FROM widgets WHERE id = :id"), {"id": 999})
        is None
    )


async def test_fetch_scalar_returns_none_for_sql_null(raw):
    """0행과 SQL NULL 을 구분하지 않는 것은 의도된 계약이다."""
    assert (
        await raw.fetch_scalar(text("SELECT score FROM widgets WHERE id = :id"), {"id": 3}) is None
    )


async def test_fetch_scalar_rejects_multiple_rows(raw):
    """여러 행을 조용히 버리지 않는다."""
    with pytest.raises(MultipleResultsFound):
        await raw.fetch_scalar(text("SELECT score FROM widgets"))


# ------------------------------------------------------------------ execute


async def test_execute_returns_rowcount(raw):
    affected = await raw.execute(
        text("UPDATE widgets SET score = :score WHERE id <= :id"), {"score": 1, "id": 2}
    )

    assert affected == 2


async def test_execute_returns_zero_when_nothing_matched(raw):
    """0 은 실패가 아니라 '해당 행 없음' 이다 — bool 로 축약하지 않는다."""
    affected = await raw.execute(text("DELETE FROM widgets WHERE id = :id"), {"id": 999})

    assert affected == 0
    assert affected is not False


async def test_execute_does_not_commit(raw):
    """트랜잭션 경계는 쓰기 View 가 소유한다 (ADR-004)."""
    await raw.execute(text("DELETE FROM widgets WHERE id = :id"), {"id": 1})
    await raw.session.rollback()

    assert await raw.fetch_scalar(text("SELECT COUNT(*) FROM widgets")) == 3


async def test_unsupported_rowcount_becomes_none(raw, monkeypatch):
    """드라이버가 rowcount 를 모르면 -1 을 성공 건수로 공개하지 않는다."""

    class _Result:
        rowcount = -1

    async def fake_execute(*args, **kwargs):
        return _Result()

    monkeypatch.setattr(raw.session, "execute", fake_execute)

    assert await raw.execute(text("DELETE FROM widgets")) is None


# ------------------------------------------------------------------ 입력 계약


async def test_plain_string_statement_is_rejected(raw):
    """문자열을 그대로 받으면 보간 SQL 이 섞여 들어온다 — TextClause 만 받는다."""
    with pytest.raises(RawSQLContractError):
        await raw.fetch_all("SELECT id FROM widgets")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM widgets; DROP TABLE widgets",
        "DELETE FROM widgets; DELETE FROM widgets",
    ],
)
async def test_multi_statement_is_rejected(raw, sql):
    with pytest.raises(RawSQLContractError):
        await raw.fetch_all(text(sql))


async def test_trailing_semicolon_is_allowed(raw):
    """세미콜론 하나로 끝나는 단일 문장은 정상이다."""
    rows = await raw.fetch_all(text("SELECT id FROM widgets ORDER BY id;"))

    assert len(rows) == 3


# ------------------------------------------------------------------ 식별자 allowlist


def test_identifier_allowlist_accepts_known_value():
    from app.core.repositories.raw_crud_base import ensure_identifier

    assert ensure_identifier("score", frozenset({"score", "name"})) == "score"


def test_identifier_allowlist_rejects_unknown_value():
    """정렬 컬럼 같은 식별자는 bind 로 못 넘긴다 — allowlist 로만 통과시킨다."""
    from app.core.repositories.raw_crud_base import ensure_identifier

    with pytest.raises(RawSQLContractError):
        ensure_identifier("score; DROP TABLE widgets", frozenset({"score", "name"}))


# ------------------------------------------------------------------ 계층 분리


def test_raw_base_does_not_inherit_orm_base():
    """ORM Base 와 Raw Base 는 상속 관계를 갖지 않는다 (C-7)."""
    from app.core.repositories.crud_base import CRUDBase

    assert not issubclass(RawCRUDBase, CRUDBase)
    assert not issubclass(CRUDBase, RawCRUDBase)
