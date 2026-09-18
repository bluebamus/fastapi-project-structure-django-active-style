"""쓰기 핸들러는 응답 DTO 를 검증한 **뒤에** commit 한다 (docs-learnability ADR-007).

commit 뒤에 DTO 를 검증하면, 검증(또는 그 안의 적재되지 않은 속성 접근)이 실패했을 때
클라이언트는 500 을 받는데 데이터는 이미 저장돼 있다. catalog 가 먼저 이 순서를
지켰고 개발 가이드도 그 순서를 가르치므로, CRUD 앱 전부가 같은 순서인지 여기서 고정한다.

방법: 핸들러 모듈이 참조하는 응답 DTO 이름을 "검증하면 터지는" 클래스로 바꿔 끼우고,
생성·수정 요청이 500 으로 끝날 때 commit 이 한 번도 호출되지 않았고 DB 상태도 요청 전과
같은지 본다. `response_model` 은 데코레이터 시점에 잡혀 있어 교체의 영향을 받지 않는다.
"""

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import (
    Base,
    get_read_only_db_session,
    get_writer_db_session,
)
from main import app


@dataclass(frozen=True)
class _Case:
    router_module: str
    dto_name: str
    model: str  # "모듈:클래스"
    collection: str
    create: dict[str, Any]
    update: dict[str, Any]


_CASES = {
    "blog": _Case(
        "app.features.blog.api.routers.v1.blog",
        "PostResponse",
        "app.features.blog.models.models:Post",
        "/api/v1/blog/posts",
        {"title": "원래 제목", "content": "본문"},
        {"title": "바뀐 제목"},
    ),
    "reply": _Case(
        "app.features.reply.api.routers.v1.reply",
        "ReplyResponse",
        "app.features.reply.models.models:Reply",
        "/api/v1/reply/replies",
        {"content": "원래 댓글"},
        {"content": "바뀐 댓글"},
    ),
    "sns": _Case(
        "app.features.sns.api.routers.v1.sns",
        "SnsPostResponse",
        "app.features.sns.models.models:SnsPost",
        "/api/v1/sns/posts",
        {"content": "원래 글"},
        {"content": "바뀐 글"},
    ),
    "user": _Case(
        "app.features.user.api.routers.v1.user",
        "UserResponse",
        "app.features.user.models.models:User",
        "/api/v1/user/users",
        {"username": "hong", "email": "hong@example.com"},
        {"email": "changed@example.com"},
    ),
    # 기준 순서를 이미 지키는 예제 — 검사가 올바른 것을 통과시키는지의 대조군.
    "catalog": _Case(
        "app.features.catalog.api.routers.v1.products",
        "ProductResponse",
        "app.features.catalog.models.models:Product",
        "/api/v1/catalog/products",
        {"name": "Keyboard", "price": "10.00"},
        {"name": "Mouse"},
    ),
}


class _ExplodingDTO:
    """`model_validate` 를 부르면 터진다 — 직렬화 실패를 흉내 낸다."""

    @classmethod
    def model_validate(cls, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("injected DTO validation failure")


def _model(case: _Case) -> Any:
    module, name = case.model.split(":")
    return getattr(import_module(module), name)


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    calls = {"commit": 0}

    async def _session():
        async with maker() as session:
            original_commit = session.commit

            async def _counting_commit(*args: Any, **kwargs: Any) -> None:
                calls["commit"] += 1
                await original_commit(*args, **kwargs)

            session.commit = _counting_commit  # type: ignore[method-assign]
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    for dependency in (get_writer_db_session, get_read_only_db_session):
        app.dependency_overrides[dependency] = _session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, maker, calls
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.parametrize("name", sorted(_CASES))
async def test_create_does_not_commit_when_dto_validation_fails(env, name, monkeypatch):
    client, maker, calls = env
    case = _CASES[name]
    monkeypatch.setattr(import_module(case.router_module), case.dto_name, _ExplodingDTO)

    response = await client.post(case.collection, json=case.create)

    assert response.status_code == 500
    assert calls["commit"] == 0, f"{name}: DTO 검증 전에 commit 했다"
    async with maker() as session:
        count = await session.scalar(select(func.count()).select_from(_model(case)))
    assert count == 0, f"{name}: 500 을 돌려줬는데 행이 저장돼 있다"


@pytest.mark.parametrize("name", sorted(_CASES))
async def test_update_does_not_commit_when_dto_validation_fails(env, name, monkeypatch):
    client, maker, calls = env
    case = _CASES[name]
    created = await client.post(case.collection, json=case.create)
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    commits_before = calls["commit"]
    monkeypatch.setattr(import_module(case.router_module), case.dto_name, _ExplodingDTO)

    response = await client.patch(f"{case.collection}/{item_id}", json=case.update)

    assert response.status_code == 500
    assert calls["commit"] == commits_before, f"{name}: DTO 검증 전에 commit 했다"
    field, _ = next(iter(case.update.items()))
    async with maker() as session:
        row = await session.get(_model(case), item_id)
    assert getattr(row, field) == case.create[field], f"{name}: 500 인데 수정이 저장돼 있다"
