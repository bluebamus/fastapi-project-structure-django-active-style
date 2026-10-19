"""사용자 리소스 권한과 세션 폐기 (service-hardening 단계 F2 — ADR-016, F-022·F-023).

- 단건 조회·수정은 본인 또는 슈퍼유저, ``is_active``·``is_superuser`` 변경은 슈퍼유저만.
- 생성은 슈퍼유저 전용이고 비밀번호가 필수다(로그인할 수 없는 계정 금지).
- 비활성화·강등·삭제는 그 사용자의 refresh family 를 모두 폐기한다(``revoke_user``).

가입·로그인은 실제 auth 엔드포인트를 지난다 — 토큰의 ``sub``·``su`` 가 DB 의 사용자와 같다.
"""

import jwt
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.redis import get_redis
from app.features.user.models.models import User
from main import app
from tests.auth_headers import superuser_headers
from tests.session_overrides import session_overrides


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
    app.dependency_overrides.update(session_overrides(maker))
    fake_redis = FakeAsyncRedis()
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, maker, fake_redis
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(env):
    return env[0]


async def _signup(client, username: str) -> tuple[str, dict]:
    """가입 + 로그인 → ``(user_id, 토큰 응답)``."""
    created = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@ex.com", "password": "password123"},
    )
    assert created.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": "password123"}
    )
    assert login.status_code == 200
    return created.json()["id"], login.json()


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _refresh(client, tokens: dict):
    return await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )


def _family(tokens: dict) -> str:
    return jwt.decode(tokens["refresh_token"], options={"verify_signature": False})["fam"]


# ------------------------------------------------------------------ 본인 / 타인


async def test_user_reads_and_updates_self(client):
    alice_id, alice = await _signup(client, "alice")

    got = await client.get(f"/api/v1/user/users/{alice_id}", headers=_auth(alice))
    patched = await client.patch(
        f"/api/v1/user/users/{alice_id}", json={"email": "new@ex.com"}, headers=_auth(alice)
    )

    assert got.status_code == 200
    assert got.json()["is_superuser"] is False
    assert patched.status_code == 200
    assert patched.json()["email"] == "new@ex.com"


async def test_user_cannot_read_or_update_others(client):
    bob_id, _ = await _signup(client, "bob")
    _, alice = await _signup(client, "alice")

    got = await client.get(f"/api/v1/user/users/{bob_id}", headers=_auth(alice))
    patched = await client.patch(
        f"/api/v1/user/users/{bob_id}", json={"email": "x@ex.com"}, headers=_auth(alice)
    )
    # 없는 id 도 같은 403 — 존재 여부를 떠볼 수 없다.
    missing = await client.get("/api/v1/user/users/no-such-id", headers=_auth(alice))

    assert (got.status_code, patched.status_code, missing.status_code) == (403, 403, 403)


async def test_user_cannot_change_privileged_fields_of_self(client):
    alice_id, alice = await _signup(client, "alice")
    url = f"/api/v1/user/users/{alice_id}"

    for body in ({"is_active": False}, {"is_superuser": True}, {"is_active": True}):
        resp = await client.patch(url, json=body, headers=_auth(alice))
        assert resp.status_code == 403, body
        assert resp.json()["error_code"] == "USER_PRIVILEGED_FIELD"

    # 슈퍼유저 권한 상승이 일어나지 않았다.
    assert (await client.get(url, headers=_auth(alice))).json()["is_superuser"] is False


async def test_superuser_reads_and_updates_anyone(client):
    alice_id, _ = await _signup(client, "alice")
    url = f"/api/v1/user/users/{alice_id}"

    assert (await client.get(url, headers=superuser_headers())).status_code == 200
    promoted = await client.patch(url, json={"is_superuser": True}, headers=superuser_headers())
    assert promoted.status_code == 200
    assert promoted.json()["is_superuser"] is True


# ------------------------------------------------------------------ 생성


async def test_created_user_can_log_in_and_superuser_flag_reaches_the_token(client):
    created = await client.post(
        "/api/v1/user/users",
        json={
            "username": "ops",
            "email": "ops@ex.com",
            "password": "password123",
            "is_superuser": True,
        },
        headers=superuser_headers(),
    )
    assert created.status_code == 201
    assert created.json()["is_superuser"] is True
    assert "password" not in created.json() and "hashed_password" not in created.json()

    login = await client.post(
        "/api/v1/auth/login", data={"username": "ops", "password": "password123"}
    )
    assert login.status_code == 200
    # 로그인으로 받은 토큰의 su 가 DB 값이다 — 관리 경로가 열린다.
    listed = await client.get("/api/v1/user/users", headers=_auth(login.json()))
    assert listed.status_code == 200


async def test_create_requires_password(env):
    client, maker, _ = env
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "nopass", "email": "nopass@ex.com"},
        headers=superuser_headers(),
    )
    assert resp.status_code == 422
    async with maker() as session:
        assert await session.scalar(select(User).where(User.username == "nopass")) is None


async def test_created_password_is_stored_as_argon2(env):
    client, maker, _ = env
    created = await client.post(
        "/api/v1/user/users",
        json={"username": "kim", "email": "kim@ex.com", "password": "password123"},
        headers=superuser_headers(),
    )
    async with maker() as session:
        user = await session.get(User, created.json()["id"])
    assert user is not None and user.hashed_password is not None
    assert user.hashed_password.startswith("$argon2")


# ------------------------------------------------------------------ 세션 폐기


async def test_deactivation_revokes_refresh_tokens(client):
    alice_id, alice = await _signup(client, "alice")
    url = f"/api/v1/user/users/{alice_id}"

    deactivated = await client.patch(url, json={"is_active": False}, headers=superuser_headers())
    assert deactivated.status_code == 200
    assert (await _refresh(client, alice)).status_code == 401

    # 다시 활성화해도 그 전에 발급된 refresh 는 죽어 있다 — 비활성화가 family 를 폐기했다.
    await client.patch(url, json={"is_active": True}, headers=superuser_headers())
    assert (await _refresh(client, alice)).status_code == 401


async def test_deactivation_revokes_the_family_itself(env):
    """비활성화 시점에 family 가 폐기 표시된다 — refresh 회전의 비활성 거부에 기대지 않는다
    (판정 규칙 revocation_for 의 비활성화 조건을 API 경로에서 직접 본다)."""
    client, _, redis = env
    alice_id, alice = await _signup(client, "alice")
    url = f"/api/v1/user/users/{alice_id}"

    await client.patch(url, json={"is_active": False}, headers=superuser_headers())

    assert await redis.exists(f"auth:fam:{_family(alice)}:revoked")


async def test_demotion_revokes_refresh_tokens(env):
    client, _, redis = env
    alice_id, alice = await _signup(client, "alice")
    url = f"/api/v1/user/users/{alice_id}"
    await client.patch(url, json={"is_superuser": True}, headers=superuser_headers())

    await client.patch(url, json={"is_superuser": False}, headers=superuser_headers())

    assert await redis.exists(f"auth:fam:{_family(alice)}:revoked")
    assert (await _refresh(client, alice)).status_code == 401


async def test_profile_update_keeps_refresh_tokens(env):
    """대조군 — 권한과 무관한 수정은 세션을 끊지 않는다."""
    client, _, redis = env
    alice_id, alice = await _signup(client, "alice")

    await client.patch(
        f"/api/v1/user/users/{alice_id}", json={"email": "n@ex.com"}, headers=_auth(alice)
    )

    assert not await redis.exists(f"auth:fam:{_family(alice)}:revoked")
    assert (await _refresh(client, alice)).status_code == 200


async def test_delete_revokes_refresh_tokens(env):
    client, _, redis = env
    alice_id, alice = await _signup(client, "alice")

    deleted = await client.delete(f"/api/v1/user/users/{alice_id}", headers=superuser_headers())

    assert deleted.status_code == 204
    assert await redis.exists(f"auth:fam:{_family(alice)}:revoked")
    assert (await _refresh(client, alice)).status_code == 401
