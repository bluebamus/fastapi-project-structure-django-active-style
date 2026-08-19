"""Catalog CRUD 엔드포인트 테스트 (Phase 7).

이 기능은 Phase 3~6 에서 만든 Base 를 **신규 기능에 처음 적용한** 자리다. 그래서
여기서 보는 것은 CRUD 동작만이 아니라, 그 Base 계약이 실전에서 그대로 성립하는가다:

- `main.py` 를 고치지 않고 자동 발견·마운트되는가 (C-1)
- 조회는 read-only Dependency 를 쓰는가 — 쓰기용 재사용이면 이 테스트가 못 잡으므로
  read-only 세션이 실제로 쓰기를 거부하는지 별도로 확인한다 (INV-4)
- update 가 제공된 필드만 반영하고 빈 PATCH 를 no-op 으로 처리하는가 (Phase 4 계약)

view→dependency→service→repository→DB 전 경로를 in-memory sqlite 로 검증한다.
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.catalog.models.models import Product  # noqa: F401  (register table)
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

    # 조회는 read-only, 변경은 writer Dependency 를 쓴다 — 둘 다 오버라이드하지 않으면
    # 한쪽 경로가 실제 MySQL 로 새어나간다.
    app.dependency_overrides[get_writer_db_session] = _override
    app.dependency_overrides[get_read_only_db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _create(client, **overrides) -> dict:
    payload = {"name": "Mechanical Keyboard", "price": "129.00"} | overrides
    response = await client.post("/api/v1/catalog/products", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------ 자동배선


def test_catalog_is_auto_registered():
    """디렉터리 컨벤션만으로 catalog 라우터가 발견·마운트된다 (C-1)."""
    paths = set(app.openapi()["paths"])

    assert "/api/v1/catalog/products" in paths
    assert "/api/v1/catalog/products/{product_id}" in paths


def test_main_has_no_catalog_reference():
    """중앙 파일을 고치지 않았다 — 이 기능은 디렉터리 존재로만 등록된다."""
    from pathlib import Path

    main_source = (
        Path(__file__).resolve().parents[4].joinpath("main.py").read_text(encoding="utf-8")
    )

    assert "catalog" not in main_source


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
    """빈 PATCH 는 오류가 아니라 현재 상태를 그대로 돌려준다 (Phase 4 계약)."""
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


def test_read_endpoints_use_read_only_dependency():
    """조회 핸들러가 쓰기용 Dependency 를 재사용하지 않는다."""
    import inspect

    from app.features.catalog.api.routers.v1 import products

    for handler in (products.list_products, products.get_product):
        source = inspect.getsource(handler)
        assert (
            "get_catalog_service_readonly" in source
        ), f"{handler.__name__} 이 쓰기 의존성을 씁니다."

    for handler in (products.create_product, products.update_product, products.delete_product):
        source = inspect.getsource(handler)
        assert "Depends(get_catalog_service)" in source


def test_write_handlers_validate_response_before_commit():
    """commit 뒤에 DTO 를 만들면 만료된 속성 재조회로 lazy I/O 가 난다."""
    import inspect

    from app.features.catalog.api.routers.v1 import products

    for handler in (products.create_product, products.update_product):
        source = inspect.getsource(handler)
        validate_at = source.index("model_validate")
        commit_at = source.index("service.commit()")
        assert validate_at < commit_at, f"{handler.__name__} 이 commit 뒤에 검증합니다."
