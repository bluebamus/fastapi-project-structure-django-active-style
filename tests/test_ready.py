"""`/ready` readiness 엔드포인트 (Phase 1).

`/health` 는 프로세스가 살아있는지만 답한다(liveness). `/ready` 는 의존 자원인
DB 까지 확인해 트래픽을 받아도 되는지 답한다(readiness). DB 가 죽었을 때 200 을
돌려주면 로드밸런서가 죽은 인스턴스로 트래픽을 계속 보낸다.

오류 응답에 DSN·SQL·예외 메시지를 담지 않는다 (C-5).
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session
from main import app


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_read_only_db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def broken_client():
    """DB 점검이 실패하는 상황 — execute 가 예외를 던진다."""

    class _BrokenSession:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("mysql+aiomysql://root:sup3rs3cret@db:3306/app 접속 실패")

    async def _override():
        yield _BrokenSession()

    app.dependency_overrides[get_read_only_db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_ready_returns_200_when_db_reachable(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"


async def test_ready_returns_503_when_db_unreachable(broken_client):
    response = await broken_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


async def test_ready_error_does_not_leak_dsn_or_credentials(broken_client):
    """503 응답 본문에 DSN·자격증명·예외 메시지가 없어야 한다 (C-5)."""
    body = (await broken_client.get("/ready")).text

    for leaked in ("sup3rs3cret", "aiomysql", "root", "3306"):
        assert leaked not in body, f"응답에 '{leaked}' 가 노출됐습니다."


def test_ready_is_in_openapi_with_health_tag():
    spec = app.openapi()

    assert "/ready" in spec["paths"], "/ready 가 OpenAPI 에 없습니다."
    operation = spec["paths"]["/ready"]["get"]
    assert operation["tags"] == ["Health"]
    assert operation["operationId"] == "readinessCheck"


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_liveness_and_readiness_are_separate(path):
    """둘은 서로 다른 엔드포인트다 — 하나로 합치지 않는다."""
    assert path in app.openapi()["paths"]
