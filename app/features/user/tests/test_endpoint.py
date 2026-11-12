"""User CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_writer_db_session 오버라이드)로 검증한다.
"""

import pytest_asyncio

from app.features.user.models.models import User  # noqa: F401  (register table)
from tests.auth_headers import superuser_headers


@pytest_asyncio.fixture
async def client(make_feature_client):
    # 비활성화·삭제가 refresh 저장소(Redis)를 쓴다.
    client, _, _ = await make_feature_client(headers=superuser_headers(), redis=True)
    return client


async def test_create_and_get_user(client):
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "alice", "email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert body["is_active"] is True
    user_id = body["id"]

    got = await client.get(f"/api/v1/user/users/{user_id}")
    assert got.status_code == 200
    assert got.json()["email"] == "alice@example.com"


async def test_list_users(client):
    await client.post(
        "/api/v1/user/users", json={"username": "a", "email": "a@x.com", "password": "password123"}
    )
    await client.post(
        "/api/v1/user/users", json={"username": "b", "email": "b@x.com", "password": "password123"}
    )

    resp = await client.get("/api/v1/user/users")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_user_deactivate(client):
    created = await client.post(
        "/api/v1/user/users",
        json={"username": "bob", "email": "bob@x.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    resp = await client.patch(f"/api/v1/user/users/{user_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_delete_user(client):
    created = await client.post(
        "/api/v1/user/users",
        json={"username": "carol", "email": "carol@x.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/user/users/{user_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/user/users/{user_id}")
    assert got.status_code == 404


async def test_duplicate_username_returns_409(client):
    await client.post(
        "/api/v1/user/users",
        json={"username": "dup", "email": "d1@x.com", "password": "password123"},
    )
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "dup", "email": "d2@x.com", "password": "password123"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "USER_USERNAME_DUPLICATE"


async def test_get_missing_user_returns_404(client):
    resp = await client.get("/api/v1/user/users/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "USER_NOT_FOUND"


async def test_create_rejects_invalid_email(client):
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "x", "email": "not-an-email", "password": "password123"},
    )
    assert resp.status_code == 422
