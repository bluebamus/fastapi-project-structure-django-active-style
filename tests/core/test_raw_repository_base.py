"""Raw Repository 의 로깅 계약 (계획서 §5, Phase 6).

Raw 계층은 SQL 을 직접 다루므로 로그가 가장 새기 쉬운 지점이다. 그래서 남기는 것을
**화이트리스트로 고정**한다: 질의 이름, 소요 시간, 성공/실패. SQL 본문과 파라미터는
남기지 않는다 (C-5).

질의 이름은 keyword-only 필수 인자다. 위치 인자로 두면 호출부에서 조용히 빠지거나
파라미터와 섞여, 정작 문제가 생겼을 때 "어느 질의인지" 를 알 수 없게 된다.
"""

import logging

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.repositories.raw_repository_base import RawRepositoryBase

SENTINEL_VALUE = "sup3rs3cret-sentinel"

# 이 계층이 직접 남기는 로그만 본다. 드라이버(aiosqlite)와 SQLAlchemy 는 DEBUG 에서
# SQL 과 파라미터를 스스로 찍는데, 그것을 막는 것은 이 Base 의 책임이 아니라
# 로깅 파이프라인의 SQL noise filter 몫이다(ledger F-018, Phase 1-R2 로 이월).
REPO_LOGGER = "raw_repository"


def _messages(caplog) -> str:
    """이 계층이 남긴 로그만 이어붙인다."""
    return chr(10).join(
        record.getMessage() for record in caplog.records if record.name == REPO_LOGGER
    )


class WidgetRawRepository(RawRepositoryBase):
    """테스트용 구체 Repository — SQL 은 Repository 소유 상수다."""

    _SELECT_BY_NAME = text("SELECT id, name FROM widgets WHERE name = :name")
    _DELETE_BY_NAME = text("DELETE FROM widgets WHERE name = :name")

    async def find_by_name(self, name: str):
        return await self.fetch_one(
            self._SELECT_BY_NAME, {"name": name}, query_name="widget.by_name"
        )

    async def delete_by_name(self, name: str) -> int | None:
        return await self.execute(self._DELETE_BY_NAME, {"name": name}, query_name="widget.delete")


@pytest_asyncio.fixture
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await session.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)"))
        await session.execute(
            text("INSERT INTO widgets (id, name) VALUES (1, :name)"), {"name": SENTINEL_VALUE}
        )
        await session.commit()
        yield WidgetRawRepository(session)
    await engine.dispose()


async def test_query_name_is_logged(repo, caplog):
    with caplog.at_level(logging.DEBUG):
        await repo.find_by_name(SENTINEL_VALUE)

    assert "widget.by_name" in _messages(caplog)


async def test_duration_is_logged(repo, caplog):
    with caplog.at_level(logging.DEBUG):
        await repo.find_by_name(SENTINEL_VALUE)

    assert "ms" in _messages(caplog)


async def test_sql_body_and_params_are_not_logged(repo, caplog):
    """SQL 본문도 파라미터 값도 로그에 남기지 않는다 (C-5)."""
    with caplog.at_level(logging.DEBUG):
        await repo.find_by_name(SENTINEL_VALUE)

    rendered = _messages(caplog)
    assert rendered, "이 계층의 로그가 하나도 남지 않았습니다."
    assert SENTINEL_VALUE not in rendered, "파라미터 값이 로그에 실렸습니다."
    for fragment in ("SELECT", "FROM widgets", ":name"):
        assert fragment not in rendered, f"SQL 본문('{fragment}')이 로그에 실렸습니다."


async def test_failure_is_logged_and_reraised(repo, caplog):
    """실패해도 원인 SQL 을 남기지 않되, 어느 질의가 실패했는지는 남긴다."""
    broken = text("SELECT no_such_column FROM widgets")

    with caplog.at_level(logging.DEBUG), pytest.raises(OperationalError):
        await repo.fetch_one(broken, query_name="widget.broken")

    rendered = _messages(caplog)
    assert "widget.broken" in rendered
    assert "no_such_column" not in rendered, "실패 로그에 SQL 본문이 실렸습니다."


async def test_query_name_is_keyword_only(repo):
    """위치 인자로 넘길 수 없어야 한다 — 호출부에서 조용히 빠지는 것을 막는다."""
    with pytest.raises(TypeError):
        await repo.fetch_one(text("SELECT 1"), None, "widget.positional")  # type: ignore[misc]


async def test_execute_still_returns_rowcount(repo):
    """로깅 래퍼가 primitive 의 반환 의미를 바꾸지 않는다."""
    assert await repo.delete_by_name(SENTINEL_VALUE) == 1
    assert await repo.delete_by_name("nobody") == 0


def test_raw_repository_does_not_inherit_orm_base():
    from app.core.repositories.repository_base import BaseRepository

    assert not issubclass(RawRepositoryBase, BaseRepository)
    assert not issubclass(BaseRepository, RawRepositoryBase)
