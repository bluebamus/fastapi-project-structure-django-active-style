"""SNS CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_writer_db_session 오버라이드)로 검증한다.
"""

import pytest_asyncio

from app.features.sns.models.models import SnsPost  # noqa: F401  (register table)
from tests.auth_headers import USER_ID, user_headers


@pytest_asyncio.fixture
async def client(make_feature_client):
    client, _, _ = await make_feature_client(headers=user_headers())
    return client


async def test_create_and_get_post(client):
    resp = await client.post(
        "/api/v1/sns/posts",
        json={"content": "오늘 날씨 좋다", "author": "park"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "오늘 날씨 좋다"
    assert body["like_count"] == 0
    post_id = body["id"]

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 200
    # 본문의 author("park")는 무시되고 서버가 로그인 주체로 채운다.
    assert got.json()["author"] == "alice"
    assert got.json()["author_id"] == USER_ID


async def test_list_posts(client):
    await client.post("/api/v1/sns/posts", json={"content": "a"})
    await client.post("/api/v1/sns/posts", json={"content": "b"})

    resp = await client.get("/api/v1/sns/posts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "old"})
    post_id = created.json()["id"]

    resp = await client.patch(f"/api/v1/sns/posts/{post_id}", json={"content": "new"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


async def test_delete_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "c"})
    post_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/sns/posts/{post_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 404


async def test_get_missing_post_returns_404(client):
    resp = await client.get("/api/v1/sns/posts/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "SNS_POST_NOT_FOUND"


async def test_create_rejects_empty_content(client):
    resp = await client.post("/api/v1/sns/posts", json={"content": ""})
    assert resp.status_code == 422
