"""BaseRepository 최소 공개 API 의 동작 계약 (계획서 §4, Phase 4).

공개 표면을 8개로 줄이면서 각 메서드의 계약도 함께 못박는다.

- 입력 mapping 을 복사한다 — 호출자의 dict 를 Repository 가 바꾸면 안 된다.
- Base 가 임의로 id 를 주입하지 않는다 — PK 생성은 모델(mixin default)이 소유한다.
- update/delete 는 bulk DML 이 아니라 단일 엔티티를 먼저 조회한다.
- update 는 unknown 필드와 PK 변경을 거부하고, 빈 PATCH 는 존재 확인 후 no-op 이다.
- 예외 detail 에 드라이버 오류 원문을 담지 않는다 (C-5).
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.exception import AppException
from app.core.repositories.repository_base import BaseRepository
from app.features.blog.models.models import Post
from app.features.user.models.models import User


class PostRepo(BaseRepository[Post, str]):
    model = Post


@pytest_asyncio.fixture
async def repo():
    from app.core.db.session import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield PostRepo(session)
    await engine.dispose()


# ------------------------------------------------------------------ create


async def test_create_does_not_mutate_caller_mapping(repo):
    """호출자가 넘긴 dict 는 그대로 남아야 한다."""
    data = {"title": "제목", "content": "본문"}
    snapshot = dict(data)

    await repo.create(data)

    assert data == snapshot, f"호출자 dict 가 변경됐습니다: {data}"


async def test_create_does_not_inject_primary_key(repo):
    """PK 생성은 모델(mixin default)이 소유한다 — Base 가 끼어들지 않는다."""
    data = {"title": "제목", "content": "본문"}

    created = await repo.create(data)

    assert "id" not in data, "Base 가 호출자 dict 에 id 를 주입했습니다."
    assert created.id, "모델 default 로 PK 가 채워지지 않았습니다."


async def test_create_respects_explicit_primary_key(repo):
    explicit = "11111111-2222-3333-4444-555555555555"

    created = await repo.create({"id": explicit, "title": "t", "content": "c"})

    assert created.id == explicit


# ------------------------------------------------------------------ update


@pytest_asyncio.fixture
async def existing(repo):
    return await repo.create({"title": "원본", "content": "원본 본문"})


async def test_update_applies_only_provided_fields(repo, existing):
    updated = await repo.update(existing.id, {"title": "바뀐 제목"})

    assert updated is not None
    assert updated.title == "바뀐 제목"
    assert updated.content == "원본 본문", "제공하지 않은 필드가 변경됐습니다."


async def test_update_rejects_unknown_field(repo, existing):
    with pytest.raises(AppException):
        await repo.update(existing.id, {"nonexistent_column": "x"})


async def test_update_rejects_primary_key_change(repo, existing):
    with pytest.raises(AppException):
        await repo.update(existing.id, {"id": "99999999-9999-9999-9999-999999999999"})


async def test_empty_patch_is_noop_when_entity_exists(repo, existing):
    result = await repo.update(existing.id, {})

    assert result is not None
    assert result.id == existing.id


async def test_empty_patch_returns_none_when_missing(repo):
    assert await repo.update("no-such-id", {}) is None


async def test_update_returns_none_for_missing_entity(repo):
    assert await repo.update("no-such-id", {"title": "x"}) is None


async def test_update_does_not_mutate_caller_mapping(repo, existing):
    data = {"title": "새 제목"}
    snapshot = dict(data)

    await repo.update(existing.id, data)

    assert data == snapshot


# ------------------------------------------------------------------ delete / exists


async def test_delete_removes_the_entity(repo, existing):
    assert await repo.delete(existing.id) is True
    assert await repo.get_by_id(existing.id) is None


async def test_delete_returns_false_for_missing_entity(repo):
    assert await repo.delete("no-such-id") is False


async def test_exists_reflects_reality(repo, existing):
    assert await repo.exists(existing.id) is True
    assert await repo.exists("no-such-id") is False


def test_exists_uses_an_exists_query():
    """COUNT(*) 대신 EXISTS 를 쓴다 — 첫 행에서 멈춘다."""
    import inspect

    source = inspect.getsource(BaseRepository.exists)

    assert "exists" in source.lower()
    assert "func.count" not in source, "exists 가 아직 COUNT 로 구현돼 있습니다."


# ------------------------------------------------------------------ 표면 고정


def test_public_surface_is_the_agreed_eight():
    expected = {
        "count",
        "create",
        "delete",
        "exists",
        "get_all",
        "get_by_id",
        "get_by_id_or_raise",
        "update",
    }
    actual = {n for n in vars(BaseRepository) if not n.startswith("_")}

    assert actual == expected, f"공개 표면이 합의된 8개와 다릅니다: {sorted(actual)}"


# ------------------------------------------------------------------ 오류 비노출


async def test_exception_detail_hides_driver_error(repo):
    """무결성 오류 응답에 드라이버 원문을 담지 않는다 (C-5).

    users.username 의 unique 제약을 쓴다 — PK 중복은 identity map 충돌 경로를 타서
    실제 드라이버 오류 경로와 다르다.
    """

    class UserRepo(BaseRepository[User, str]):
        model = User

    users = UserRepo(repo.session)
    await users.create({"username": "dup", "email": "a@example.com"})

    with pytest.raises(AppException) as excinfo:
        await users.create({"username": "dup", "email": "b@example.com"})

    rendered = str(excinfo.value.to_response().model_dump())
    for leaked in ("UNIQUE constraint", "sqlite3", "SQL", "INSERT INTO"):
        assert leaked not in rendered, f"응답에 드라이버 원문('{leaked}')이 실렸습니다."


def test_crud_base_exposes_only_the_agreed_primitives():
    """CRUDBase 는 get/add/delete/flush/refresh primitive 만 제공한다 (계획서 §4)."""
    from app.core.repositories.crud_base import CRUDBase

    expected = {"_get", "_add", "_delete", "_flush", "_refresh", "_pk"}
    actual = {name for name in vars(CRUDBase) if name.startswith("_") and not name.startswith("__")}

    assert actual == expected, f"CRUDBase primitive 가 합의된 집합과 다릅니다: {sorted(actual)}"
