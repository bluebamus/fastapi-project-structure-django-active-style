"""BaseRepository eager-loading 의 단일/중첩 관계 로딩 회귀 검증.

배경(감사 F-1): `_apply_eager_loading` 의 중첩 경로가 체인 로더에 문자열을
넘겨(SQLAlchemy 2.0) `relations=["a.b"]` 사용 시 런타임 실패했다. 앱 모델에는
relationship 이 없어 도달 불가였으나, 이 베이스는 재사용 스캐폴딩이므로
관계를 정의한 소비자를 대신해 격리된 모델로 회귀를 고정한다.

핵심 회귀: async 세션에서 eager-load 된 관계를 이후 접근해도 지연로딩
(MissingGreenlet)이 발생하지 않아야 한다. 수정 전에는 중첩 옵션 구성 자체가
예외였다.
"""

import pytest
import pytest_asyncio
from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.repositories.repository_base import BaseRepository


class _Base(DeclarativeBase):
    """앱 Base.metadata 오염을 피하기 위한 격리 declarative base."""


class _Parent(_Base):
    __tablename__ = "eltest_parent"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    children: Mapped[list["_Child"]] = relationship(back_populates="parent")


class _Child(_Base):
    __tablename__ = "eltest_child"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("eltest_parent.id"))
    parent: Mapped[_Parent] = relationship(back_populates="children")
    grandchildren: Mapped[list["_GrandChild"]] = relationship(back_populates="child")


class _GrandChild(_Base):
    __tablename__ = "eltest_grandchild"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    child_id: Mapped[str] = mapped_column(ForeignKey("eltest_child.id"))
    child: Mapped[_Child] = relationship(back_populates="grandchildren")


class _ParentRepo(BaseRepository[_Parent]):  # type: ignore[type-var]
    model = _Parent


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        s.add(_Parent(id="p1"))
        s.add(_Child(id="c1", parent_id="p1"))
        s.add(_GrandChild(id="g1", child_id="c1"))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_eager_load_single_level(session):
    repo = _ParentRepo(session)
    parents = await repo.get_all_with(relations=["children"])
    session.expunge_all()  # 지연로딩이면 이후 접근에서 실패하도록 강제

    assert len(parents) == 1
    # eager-load 되지 않았다면 expunge 후 접근 시 예외가 발생한다.
    assert [c.id for c in parents[0].children] == ["c1"]


@pytest.mark.asyncio
async def test_eager_load_nested_level(session):
    repo = _ParentRepo(session)
    parents = await repo.get_all_with(relations=["children", "children.grandchildren"])
    session.expunge_all()

    assert len(parents) == 1
    child = parents[0].children[0]
    # 중첩 grandchildren 이 eager-load 되어 지연로딩 없이 접근 가능해야 한다.
    assert [g.id for g in child.grandchildren] == ["g1"]
