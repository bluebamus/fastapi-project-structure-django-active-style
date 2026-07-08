"""BaseRepository 재사용 표면 전수 검증.

감사 결론: 템플릿이 "재사용 스캐폴딩"으로 제공하는 BaseRepository 메서드는
실제로 범용 동작해야 재사용 가치가 있다(미검증 = 잠재 함정). L-2(중첩
eager-loading)가 그 증거였다. 이 모듈은 앱이 사용하지 않아 미검증이던
메서드들을 격리 모델로 하나씩 호출해 실제 동작을 고정한다.

- 격리 declarative Base 사용 → 앱 Base.metadata 오염 없음.
- 관계/컬럼/텍스트 컬럼을 갖춘 모델로 filter/update/delete/eager/join/partial/
  batch/upsert 경로를 모두 실행한다.
"""

import pytest
import pytest_asyncio
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.repositories.repository_base import BaseRepository


class _Base(DeclarativeBase):
    """앱 Base.metadata 오염 방지용 격리 base."""


class Item(_Base):
    __tablename__ = "surf_item"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(50))
    qty: Mapped[int] = mapped_column(Integer, default=0)
    bio: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list["Tag"]] = relationship(back_populates="item")


class Tag(_Base):
    __tablename__ = "surf_tag"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("surf_item.id"))
    label: Mapped[str] = mapped_column(String(50))
    item: Mapped[Item] = relationship(back_populates="tags")


class ItemRepo(BaseRepository[Item]):  # type: ignore[type-var]
    model = Item


class TagRepo(BaseRepository[Tag]):  # type: ignore[type-var]
    model = Tag


@pytest_asyncio.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield ItemRepo(s)
    await engine.dispose()


async def _seed(repo: ItemRepo, n_tags: int = 0) -> None:
    """category=a 2건, category=b 1건. 필요 시 첫 item 에 태그 부여."""
    await repo.create({"id": "i1", "name": "alpha", "category": "a", "qty": 1, "bio": "x"})
    await repo.create({"id": "i2", "name": "beta", "category": "a", "qty": 2, "bio": "y"})
    await repo.create({"id": "i3", "name": "gamma", "category": "b", "qty": 3, "bio": "z"})
    if n_tags:
        tag_repo = TagRepo(repo.session)
        for k in range(n_tags):
            await tag_repo.create({"id": f"t{k}", "item_id": "i1", "label": f"L{k}"})
    await repo.session.commit()


# --------------------------------------------------------------------------
# CREATE
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_create(repo: ItemRepo):
    created = await repo.bulk_create(
        [{"name": "a", "category": "c", "qty": 1}, {"name": "b", "category": "c", "qty": 2}]
    )
    await repo.session.commit()
    assert len(created) == 2
    assert all(c.id for c in created)  # id 자동 할당
    assert await repo.count() == 2


# --------------------------------------------------------------------------
# READ - basic
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_many_with_filter(repo: ItemRepo):
    await _seed(repo)
    items = await repo.get_many(category="a")
    assert {i.id for i in items} == {"i1", "i2"}


@pytest.mark.asyncio
async def test_exists_and_exists_by(repo: ItemRepo):
    await _seed(repo)
    assert await repo.exists("i1") is True
    assert await repo.exists("nope") is False
    assert await repo.exists_by(name="gamma") is True
    assert await repo.exists_by(name="none") is False


# --------------------------------------------------------------------------
# READ - eager loading
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_by_id_with(repo: ItemRepo):
    await _seed(repo, n_tags=2)
    item = await repo.get_by_id_with("i1", relations=["tags"])
    repo.session.expunge_all()
    assert item is not None
    assert len(item.tags) == 2


@pytest.mark.asyncio
async def test_get_one_with(repo: ItemRepo):
    await _seed(repo, n_tags=1)
    item = await repo.get_one_with(relations=["tags"], name="alpha")
    repo.session.expunge_all()
    assert item is not None and len(item.tags) == 1


@pytest.mark.asyncio
async def test_get_many_with(repo: ItemRepo):
    await _seed(repo, n_tags=2)
    items = await repo.get_many_with(relations=["tags"], category="a")
    repo.session.expunge_all()
    assert {i.id for i in items} == {"i1", "i2"}
    assert len(next(i for i in items if i.id == "i1").tags) == 2


@pytest.mark.asyncio
async def test_get_by_ids_with(repo: ItemRepo):
    await _seed(repo, n_tags=1)
    items = await repo.get_by_ids_with(["i1", "i3"], relations=["tags"])
    repo.session.expunge_all()
    assert {i.id for i in items} == {"i1", "i3"}
    # 빈 목록 조기 반환
    assert await repo.get_by_ids_with([]) == []


# --------------------------------------------------------------------------
# READ - partial / batch / join / aggregation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_partial(repo: ItemRepo):
    await _seed(repo)
    items = await repo.get_partial(columns=["id", "name"], category="a")
    assert {i.id for i in items} == {"i1", "i2"}
    assert items[0].name  # 로드된 컬럼 접근 가능


@pytest.mark.asyncio
async def test_get_by_id_partial(repo: ItemRepo):
    await _seed(repo)
    item = await repo.get_by_id_partial("i1", columns=["id", "name"])
    assert item is not None and item.name == "alpha"


@pytest.mark.asyncio
async def test_get_in_batches(repo: ItemRepo):
    await _seed(repo)
    seen: list[str] = []
    async for batch in repo.get_in_batches(batch_size=2):
        seen.extend(i.id for i in batch)
    assert set(seen) == {"i1", "i2", "i3"}


@pytest.mark.asyncio
async def test_get_with_join(repo: ItemRepo):
    await _seed(repo, n_tags=2)
    items = await repo.get_with_join(
        join_model=Tag,
        join_condition=Item.id == Tag.item_id,
        relations=["tags"],
    )
    repo.session.expunge_all()
    # i1 만 태그가 있어 조인 결과에 포함
    assert {i.id for i in items} == {"i1"}
    assert len(items[0].tags) == 2


@pytest.mark.asyncio
async def test_count_with_relation(repo: ItemRepo):
    await _seed(repo, n_tags=3)
    results = await repo.count_with_relation("tags")
    counts = {item.id: cnt for item, cnt in results}
    assert counts["i1"] == 3
    assert counts["i2"] == 0


# --------------------------------------------------------------------------
# UPDATE
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_update(repo: ItemRepo):
    await _seed(repo)
    n = await repo.bulk_update(["i1", "i2"], {"qty": 99})
    await repo.session.commit()
    assert n == 2
    assert (await repo.get_by_id("i1")).qty == 99


@pytest.mark.asyncio
async def test_update_by(repo: ItemRepo):
    await _seed(repo)
    n = await repo.update_by({"qty": 7}, category="a")
    await repo.session.commit()
    assert n == 2
    assert (await repo.get_by_id("i2")).qty == 7


# --------------------------------------------------------------------------
# DELETE
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bulk_delete(repo: ItemRepo):
    await _seed(repo)
    n = await repo.bulk_delete(["i1", "i2"])
    await repo.session.commit()
    assert n == 2
    assert await repo.count() == 1


@pytest.mark.asyncio
async def test_delete_by(repo: ItemRepo):
    await _seed(repo)
    n = await repo.delete_by(category="a")
    await repo.session.commit()
    assert n == 2
    assert await repo.count() == 1


# --------------------------------------------------------------------------
# UPSERT
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_or_create(repo: ItemRepo):
    await _seed(repo)
    existing, created = await repo.get_or_create(name="alpha", defaults={"category": "a"})
    assert created is False and existing.id == "i1"

    new, created2 = await repo.get_or_create(name="delta", defaults={"category": "d", "qty": 5})
    await repo.session.commit()
    assert created2 is True and new.name == "delta"


@pytest.mark.asyncio
async def test_update_or_create(repo: ItemRepo):
    await _seed(repo)
    updated, created = await repo.update_or_create(name="alpha", defaults={"qty": 42})
    await repo.session.commit()
    assert created is False and updated.qty == 42

    new, created2 = await repo.update_or_create(name="omega", defaults={"category": "z", "qty": 1})
    await repo.session.commit()
    assert created2 is True and new.name == "omega"
