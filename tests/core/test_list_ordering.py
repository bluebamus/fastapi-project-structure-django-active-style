"""목록 쿼리의 결정적 순서 (service-hardening F-005).

정렬 없는 offset 페이지네이션은 DB 가 고른 임의 순서라 페이지 사이에서 행이 중복·누락된다.
`created_at` 하나로 정렬해도 같은 시각의 행끼리는 순서가 정해지지 않는다 — 초 단위 시각
(MySQL `DATETIME(0)`)에서는 동률이 흔하다. 그래서 일부러 **모든 행의 created_at 을 같게**
만들고, PK 가 마지막 동률을 끊는지 본다.
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest_asyncio
from sqlalchemy import Integer, insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.repositories.repository_base import BaseRepository
from app.features.blog.models.models import Post
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.home.models.models import UserAccessLog
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository

SAME_INSTANT = datetime(2026, 10, 12, 9, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
IDS = [f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 8)]


class PostRepo(BaseRepository[Post, str]):
    model = Post


@pytest_asyncio.fixture
async def session():
    from app.core.db.session import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _pages(fetch, size: int, total: int) -> list[list[str]]:
    return [[row.id for row in await fetch(skip, size)] for skip in range(0, total, size)]


def _assert_partition(pages: list[list[str]], expected: list[str]) -> None:
    """페이지를 이어 붙이면 기대 순서와 정확히 같다 — 중복도 누락도 없다."""
    flat = [row_id for page in pages for row_id in page]
    assert flat == expected
    assert len(set(flat)) == len(flat)


# ------------------------------------------------------------------ BaseRepository.get_all


async def test_get_all_breaks_created_at_ties_by_primary_key(session):
    # 삽입 순서를 일부러 섞는다 — 삽입 순서에 기대면 이 테스트가 잡는다.
    for row_id in (IDS[3], IDS[0], IDS[6], IDS[2], IDS[5], IDS[1], IDS[4]):
        session.add(Post(id=row_id, title="t", content="c", created_at=SAME_INSTANT))
    await session.flush()
    repo = PostRepo(session)

    pages = await _pages(lambda skip, size: repo.get_all(skip=skip, limit=size), 3, len(IDS))

    _assert_partition(pages, sorted(IDS, reverse=True))


async def test_get_all_puts_newer_rows_first(session):
    older = SAME_INSTANT.replace(hour=8)
    session.add(Post(id=IDS[6], title="old", content="c", created_at=older))
    session.add(Post(id=IDS[0], title="new", content="c", created_at=SAME_INSTANT))
    await session.flush()

    rows = await PostRepo(session).get_all()

    assert [row.title for row in rows] == ["new", "old"]


class _NoTimestampBase(DeclarativeBase):
    """created_at 이 없는 모델 — 테스트 전용 metadata."""


class Counter(_NoTimestampBase):
    __tablename__ = "ordering_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class CounterRepo(BaseRepository[Counter, int]):
    model = Counter


async def test_get_all_falls_back_to_primary_key_without_created_at():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_NoTimestampBase.metadata.create_all)
        await conn.execute(insert(Counter), [{"id": n} for n in (3, 1, 5, 2, 4)])
    async with async_sessionmaker(engine)() as session:
        repo = CounterRepo(session)
        pages = [[row.id for row in await repo.get_all(skip=skip, limit=2)] for skip in (0, 2, 4)]
    await engine.dispose()

    assert pages == [[5, 4], [3, 2], [1]]


# ------------------------------------------------------------------ 기능 Repository 보조 키


async def test_product_list_active_is_deterministic_on_equal_created_at(session):
    for row_id in (IDS[2], IDS[5], IDS[0], IDS[4], IDS[1], IDS[6], IDS[3]):
        session.add(
            Product(
                id=row_id,
                name="p",
                price=Decimal("1.00"),
                is_active=True,
                created_at=SAME_INSTANT,
            )
        )
    await session.flush()
    repo = ProductRepository(session)

    pages = await _pages(lambda skip, size: repo.list_active(skip=skip, limit=size), 3, len(IDS))

    _assert_partition(pages, sorted(IDS, reverse=True))


def _log(row_id: str) -> UserAccessLog:
    return UserAccessLog(
        id=row_id,
        ip_address="10.0.0.1",
        user_id="u1",
        request_path="/",
        request_method="GET",
        created_at=SAME_INSTANT,
    )


async def test_access_log_queries_are_deterministic_on_equal_created_at(session):
    for row_id in (IDS[4], IDS[1], IDS[6], IDS[0], IDS[3], IDS[5], IDS[2]):
        session.add(_log(row_id))
    await session.flush()
    repo = UserAccessLogRepository(session)
    expected = sorted(IDS, reverse=True)

    _assert_partition(
        await _pages(lambda s, n: repo.get_by_ip("10.0.0.1", skip=s, limit=n), 3, 7), expected
    )
    _assert_partition(
        await _pages(lambda s, n: repo.get_by_user_id("u1", skip=s, limit=n), 3, 7), expected
    )
    _assert_partition(
        await _pages(
            lambda s, n: repo.get_by_date_range(SAME_INSTANT, SAME_INSTANT, skip=s, limit=n),
            3,
            7,
        ),
        expected,
    )
    assert [row.id for row in await repo.get_recent_logs(limit=3)] == expected[:3]
