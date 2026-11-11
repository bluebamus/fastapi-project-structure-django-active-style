"""Catalog CRUD 엔드포인트 테스트.

ORM 예제 기능이다. 생성·조회·목록·부분 수정(빈 PATCH 는 no-op)·삭제, 입력 검증, NOT NULL 컬럼의
명시적 null 거부를 본다.

view→dependency→service→repository→DB 전 경로를 in-memory sqlite 로 검증한다.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.features.catalog.models.models import Product  # noqa: F401  (register table)
from main import app
from tests.auth_headers import superuser_headers
from tests.session_overrides import session_overrides


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

    # 조회는 read-only, 변경은 writer Dependency 를 쓴다 — 둘 다 오버라이드하지 않으면
    # 한쪽 경로가 실제 MySQL 로 새어나간다.
    app.dependency_overrides.update(session_overrides(maker))
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=superuser_headers()
    ) as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _create(client, **overrides) -> dict:
    payload = {"name": "Mechanical Keyboard", "price": "129.00"} | overrides
    response = await client.post("/api/v1/catalog/products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ 자동배선


# ------------------------------------------------------------------ CRUD


async def test_create_returns_201_with_body(client):
    body = await _create(client)

    assert body["name"] == "Mechanical Keyboard"
    assert Decimal(str(body["price"])) == Decimal("129.00")
    assert body["is_active"] is True
    assert body["id"]


async def test_list_returns_items_and_total(client):
    await _create(client, name="A")
    await _create(client, name="B")

    body = (await client.get("/api/v1/catalog/products")).json()

    assert body["total"] == 2
    assert {item["name"] for item in body["items"]} == {"A", "B"}
    assert body["skip"] == 0
    assert body["limit"] == 50


async def test_get_returns_single_product(client):
    created = await _create(client)

    body = (await client.get(f"/api/v1/catalog/products/{created['id']}")).json()

    assert body["id"] == created["id"]


async def test_get_missing_returns_404(client):
    response = await client.get("/api/v1/catalog/products/no-such-id")

    assert response.status_code == 404


async def test_patch_applies_only_given_fields(client):
    created = await _create(client)

    response = await client.patch(
        f"/api/v1/catalog/products/{created['id']}", json={"price": "99.00"}
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(str(body["price"])) == Decimal("99.00")
    assert body["name"] == created["name"], "보내지 않은 필드가 바뀌었습니다."


async def test_empty_patch_is_noop(client):
    """빈 PATCH 는 오류가 아니라 현재 상태를 그대로 돌려준다."""
    created = await _create(client)

    response = await client.patch(f"/api/v1/catalog/products/{created['id']}", json={})

    assert response.status_code == 200
    assert response.json()["name"] == created["name"]


async def test_patch_missing_returns_404(client):
    response = await client.patch("/api/v1/catalog/products/no-such-id", json={"price": "1.00"})

    assert response.status_code == 404


async def test_delete_returns_204_and_removes(client):
    created = await _create(client)

    response = await client.delete(f"/api/v1/catalog/products/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"/api/v1/catalog/products/{created['id']}")).status_code == 404


async def test_delete_missing_returns_404(client):
    assert (await client.delete("/api/v1/catalog/products/no-such-id")).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "price": "1.00"},
        {"name": "x", "price": "0"},
        {"name": "x", "price": "-1.00"},
        {"price": "1.00"},
    ],
    ids=["empty-name", "zero-price", "negative-price", "missing-name"],
)
async def test_create_rejects_invalid_payload(client, payload):
    assert (await client.post("/api/v1/catalog/products", json=payload)).status_code == 422


# ------------------------------------------------------------------ 계약


@pytest.mark.parametrize("field", ["name", "price", "is_active"])
async def test_patch_null_on_not_null_column_returns_422(client, field):
    """NOT NULL 컬럼의 명시적 null 은 422 다 — 예전에는 무결성 오류가 409 "충돌" 이었다."""
    created = await _create(client)

    response = await client.patch(f"/api/v1/catalog/products/{created['id']}", json={field: None})

    assert response.status_code == 422
