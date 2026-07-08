"""Home 접속 로그 조회/통계 엔드포인트 테스트.

접속 로그는 미들웨어가 생성하므로(생성 API 없음), DB 에 직접 시드한 뒤 5개
읽기 엔드포인트를 검증한다. StaticPool 로 시드 세션과 요청 세션이 동일
in-memory DB 를 공유한다. (view→dependency→service→repository→DB 전체 경로)
"""

from datetime import datetime

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.bootstrap import create_app
from app.core.db.session import Base, get_session
from app.domains.home.models.models import UserAccessLog


@pytest_asyncio.fixture
async def ctx():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_session():
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    await engine.dispose()


async def _seed(maker):
    async with maker() as s:
        s.add_all(
            [
                UserAccessLog(
                    id="l1",
                    ip_address="10.0.0.1",
                    request_path="/a",
                    request_method="GET",
                    user_id="u1",
                    device_type="desktop",
                    os_name="Windows",
                    browser_name="Chrome",
                    is_bot=False,
                    created_at=datetime(2024, 1, 1),
                ),
                UserAccessLog(
                    id="l2",
                    ip_address="10.0.0.1",
                    request_path="/b",
                    request_method="GET",
                    user_id="u2",
                    device_type="mobile",
                    os_name="iOS",
                    browser_name="Safari",
                    is_bot=False,
                    created_at=datetime(2024, 1, 2),
                ),
                UserAccessLog(
                    id="l3",
                    ip_address="10.0.0.2",
                    request_path="/c",
                    request_method="POST",
                    user_id="u1",
                    device_type="desktop",
                    os_name="Linux",
                    browser_name="Firefox",
                    is_bot=False,
                    created_at=datetime(2024, 1, 3),
                ),
            ]
        )
        await s.commit()


def test_home_auto_registered():
    """디렉터리 컨벤션만으로 home 라우터가 자동 발견·마운트된다."""
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/home/access-logs" in paths
    assert "/api/v1/home/access-logs/stats" in paths


async def test_list_access_logs(ctx):
    client, maker = ctx
    await _seed(maker)
    resp = await client.get("/api/v1/home/access-logs?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


async def test_recent_access_logs(ctx):
    client, maker = ctx
    await _seed(maker)
    resp = await client.get("/api/v1/home/access-logs/recent?limit=2")
    assert resp.status_code == 200
    items = resp.json()
    assert [i["id"] for i in items] == ["l3", "l2"]  # created_at 역순


async def test_access_logs_by_ip(ctx):
    client, maker = ctx
    await _seed(maker)
    resp = await client.get("/api/v1/home/access-logs/by-ip/10.0.0.1")
    assert resp.status_code == 200
    assert {i["id"] for i in resp.json()} == {"l1", "l2"}


async def test_access_logs_by_user(ctx):
    client, maker = ctx
    await _seed(maker)
    resp = await client.get("/api/v1/home/access-logs/by-user/u1")
    assert resp.status_code == 200
    assert {i["id"] for i in resp.json()} == {"l1", "l3"}


async def test_access_log_stats(ctx):
    client, maker = ctx
    await _seed(maker)
    resp = await client.get("/api/v1/home/access-logs/stats")
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_count"] == 3
    devices = {d["device_type"]: d["count"] for d in stats["device_types"]}
    assert devices["desktop"] == 2
    assert devices["mobile"] == 1


async def test_list_access_logs_empty(ctx):
    client, _ = ctx
    resp = await client.get("/api/v1/home/access-logs")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
