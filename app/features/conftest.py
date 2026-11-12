"""기능 엔드포인트 테스트의 공용 클라이언트 팩토리.

기능마다 같은 형태(in-memory SQLite + 세션 Dependency override + ASGI 클라이언트)를 복사하던
것을 하나로 모았다. 기능별 차이는 인자로만 받는다.

    @pytest_asyncio.fixture
    async def client(make_feature_client):
        client, _maker, _redis = await make_feature_client(headers=user_headers())
        return client
"""

from contextlib import AsyncExitStack

import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.redis import get_redis
from main import app
from tests.session_overrides import SessionHook, session_overrides


@pytest_asyncio.fixture
async def make_feature_client():
    """``await make(...)`` → ``(client, maker, redis)``. 테스트가 끝나면 override·엔진을 정리한다.

    Args(make):
        headers: 클라이언트 기본 헤더(보통 ``tests.auth_headers`` 의 Bearer).
        writer: False 면 쓰기 세션은 override 하지 않는다 — 몰래 writer 를 잡으면 실패하게.
        on_open: 세션을 연 직후 훅(commit/rollback 집계 등).
        redis: True 면 ``get_redis`` 를 FakeAsyncRedis 로 바꾼다(lifespan 없이 띄우므로).
        raise_app_exceptions: False 면 서버 예외를 실제 500 응답으로 받는다.
    """
    stack = AsyncExitStack()
    engines = []

    async def make(
        *,
        headers: dict[str, str] | None = None,
        writer: bool = True,
        on_open: SessionHook | None = None,
        redis: bool = False,
        raise_app_exceptions: bool = True,
    ) -> tuple[AsyncClient, async_sessionmaker, FakeAsyncRedis | None]:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        engines.append(engine)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        maker = async_sessionmaker(engine, expire_on_commit=False)

        # 조회는 read-only, 변경은 writer Dependency 를 쓴다 — 오버라이드하지 않은 쪽은
        # 실제 MySQL 로 새어나간다.
        app.dependency_overrides.update(session_overrides(maker, on_open=on_open, writer=writer))
        fake_redis: FakeAsyncRedis | None = None
        if redis:
            fake_redis = FakeAsyncRedis()
            app.dependency_overrides[get_redis] = lambda: fake_redis
        transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        client = await stack.enter_async_context(
            AsyncClient(transport=transport, base_url="http://test", headers=headers)
        )
        return client, maker, fake_redis

    yield make

    await stack.aclose()
    app.dependency_overrides.clear()
    for engine in engines:
        await engine.dispose()
