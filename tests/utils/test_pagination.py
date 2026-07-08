"""app/utils/pagination 유틸 검증.

이동·데이터클래스화된 PaginatedResponse(stdlib @dataclass)와 get_paginated
헬퍼가 실제로 동작함을 격리 모델(sqlite)로 고정한다.
"""

from dataclasses import is_dataclass
from datetime import datetime

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.pagination import PaginatedResponse, get_paginated


class _Base(DeclarativeBase):
    pass


class PgItem(_Base):
    __tablename__ = "pg_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PgItemOut(BaseModel):
    id: str
    name: str
    category: str


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add_all(
            [
                PgItem(id="a", name="alpha", category="x", created_at=datetime(2024, 1, 1)),
                PgItem(id="b", name="beta", category="x", created_at=datetime(2024, 1, 2)),
                PgItem(id="c", name="gamma", category="y", created_at=datetime(2024, 1, 3)),
            ]
        )
        await s.commit()
        yield s
    await engine.dispose()


def test_is_stdlib_dataclass():
    assert is_dataclass(PaginatedResponse)


def test_default_values():
    resp: PaginatedResponse = PaginatedResponse()
    assert resp.items == []
    assert resp.total == 0
    assert resp.page == 1
    assert resp.page_size == 20
    assert resp.total_pages == 1
    assert resp.has_next is False
    assert resp.has_prev is False


def test_create_computes_metadata():
    resp = PaginatedResponse.create(items=[1, 2], total=25, page=2, page_size=10)
    assert resp.total_pages == 3  # ceil(25/10)
    assert resp.has_next is True  # 2 < 3
    assert resp.has_prev is True  # 2 > 1
    assert resp.items == [1, 2]


def test_create_empty_has_one_page():
    resp = PaginatedResponse.create(items=[], total=0, page=1, page_size=10)
    assert resp.total_pages == 1
    assert resp.has_next is False
    assert resp.has_prev is False


@pytest.mark.asyncio
async def test_get_paginated_orders_and_paginates(session):
    resp = await get_paginated(
        session=session,
        model=PgItem,
        item_schema=PgItemOut,
        page=1,
        page_size=2,
    )
    assert resp.total == 3
    assert resp.total_pages == 2
    assert resp.has_next is True
    assert resp.has_prev is False
    # created_at desc 기본 정렬 → 최신순 c, b
    assert [i.id for i in resp.items] == ["c", "b"]
    assert all(isinstance(i, PgItemOut) for i in resp.items)


@pytest.mark.asyncio
async def test_get_paginated_filters(session):
    resp = await get_paginated(
        session=session,
        model=PgItem,
        item_schema=PgItemOut,
        filters={"category": "x"},
    )
    assert resp.total == 2
    assert {i.id for i in resp.items} == {"a", "b"}


@pytest.mark.asyncio
async def test_get_paginated_transform_fn(session):
    resp = await get_paginated(
        session=session,
        model=PgItem,
        item_schema=PgItemOut,
        transform_fn=lambda r: PgItemOut(id=r.id, name=r.name.upper(), category=r.category),
    )
    assert all(i.name.isupper() for i in resp.items)
