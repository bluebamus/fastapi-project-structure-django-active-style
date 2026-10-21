"""Auth 엔드포인트 테스트 — register/login/me/refresh/logout 전체 경로 (in-memory sqlite + fakeredis)."""

import bcrypt
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.exception import InvalidTokenException
from app.core.redis import get_redis
from app.features.auth.dependencies.auth_dependencies import get_token_service
from app.features.user.models.models import User
from config import jwt_settings
from main import app
from tests.session_overrides import session_overrides


@pytest_asyncio.fixture
async def env():
    """``(client, maker, redis)`` — DB 를 직접 보거나 Redis 상태를 볼 테스트용."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    # get_current_user 는 get_read_only_db_session 을 쓴다 — 함께 오버라이드하지 않으면
    # 인증 경로가 실제 MySQL 로 새어나간다.
    app.dependency_overrides.update(session_overrides(maker))
    # 로그인·가입 rate limit 과 refresh 저장소가 Redis 를 쓴다(lifespan 없이 띄우므로 가짜).
    fake_redis = FakeAsyncRedis()
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker, fake_redis
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(env):
    return env[0]


async def _register(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@ex.com", "password": password},
    )


async def _login(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )


async def test_register_returns_user_without_password(client):
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "password" not in body and "hashed_password" not in body
    assert body["is_active"] is True


async def test_register_duplicate_username_409(client):
    await _register(client)
    resp = await _register(client)
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "AUTH_USERNAME_DUPLICATE"


async def test_register_rejects_short_password(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@ex.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_login_and_access_me(client):
    await _register(client)
    login = await _login(client)
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_wrong_password_401(client):
    await _register(client)
    resp = await _login(client, password="wrong-password")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


async def test_me_without_token_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_401(client):
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_refresh_issues_working_access_token(client):
    await _register(client)
    login = await _login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]}
    )
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


async def test_refresh_rejects_access_token_401(client):
    await _register(client)
    login = await _login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["access_token"]}
    )
    assert resp.status_code == 401


# --------------------------------------------------------------- 단계 F1 흐름


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def _refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def test_token_response_carries_expires_in(client):
    await _register(client)
    body = (await _login(client)).json()
    assert body["expires_in"] == jwt_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


async def test_full_flow_register_login_me_refresh_logout(client):
    assert (await _register(client)).status_code == 201
    first = (await _login(client)).json()
    me = await client.get("/api/v1/auth/me", headers=_bearer(first["access_token"]))
    assert me.status_code == 200

    rotated = await _refresh(client, first["refresh_token"])
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    me = await client.get("/api/v1/auth/me", headers=_bearer(second["access_token"]))
    assert me.status_code == 200

    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": second["refresh_token"]}
    )
    assert logout.status_code == 204
    assert (await _refresh(client, second["refresh_token"])).status_code == 401


async def test_reused_refresh_token_revokes_the_whole_family(client):
    """소비된 refresh 가 다시 오면 401 이고, 그 사이 정상 회전으로 받은 토큰도 죽는다."""
    await _register(client)
    first = (await _login(client)).json()["refresh_token"]
    second = (await _refresh(client, first)).json()["refresh_token"]

    reuse = await _refresh(client, first)
    assert reuse.status_code == 401
    assert reuse.json()["error_code"] == "AUTH_INVALID_TOKEN"
    assert (await _refresh(client, second)).status_code == 401


async def test_other_login_family_survives_reuse_detection(client):
    """재사용 탐지는 그 family 만 끊는다 — 다른 기기의 로그인은 그대로다."""
    await _register(client)
    device_a = (await _login(client)).json()["refresh_token"]
    device_b = (await _login(client)).json()["refresh_token"]
    await _refresh(client, device_a)
    await _refresh(client, device_a)  # 재사용 → family A 폐기
    assert (await _refresh(client, device_b)).status_code == 200


async def test_logout_is_idempotent(client):
    await _register(client)
    token = (await _login(client)).json()["refresh_token"]
    await _refresh(client, token)  # 이미 소비된 토큰
    for _ in range(2):
        resp = await client.post("/api/v1/auth/logout", json={"refresh_token": token})
        assert resp.status_code == 204


async def test_logout_rejects_invalid_token(client):
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "not-a-token"})
    assert resp.status_code == 401


async def test_refresh_fails_for_deactivated_user(env):
    client, maker, _ = env
    await _register(client)
    token = (await _login(client)).json()["refresh_token"]
    async with maker() as session:
        await session.execute(User.__table__.update().values(is_active=False))
        await session.commit()
    assert (await _refresh(client, token)).status_code == 401


async def test_me_rejects_refresh_token(client):
    """type 혼동 — refresh 토큰을 Bearer 로 쓸 수 없다."""
    await _register(client)
    tokens = (await _login(client)).json()
    resp = await client.get("/api/v1/auth/me", headers=_bearer(tokens["refresh_token"]))
    assert resp.status_code == 401


async def test_login_migrates_legacy_bcrypt_hash(env):
    """이전 버전의 bcrypt 해시로 로그인하면 성공하고, 저장된 해시가 Argon2 로 바뀐다."""
    client, maker, _ = env
    legacy = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    async with maker() as session:
        session.add(User(username="old", email="old@ex.com", hashed_password=legacy))
        await session.commit()

    assert (await _login(client, username="old")).status_code == 200

    async with maker() as session:
        stored = (await session.execute(User.__table__.select())).one().hashed_password
    assert stored.startswith("$argon2")
    assert (await _login(client, username="old")).status_code == 200


async def test_login_is_rate_limited_per_ip_and_username(client):
    await _register(client)
    for _ in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS):
        assert (await _login(client, password="wrong-password")).status_code == 401

    blocked = await _login(client)  # 맞는 비밀번호여도 창 안에서는 막힌다
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "TOO_MANY_REQUESTS"
    retry_after = int(blocked.headers["Retry-After"])
    assert 0 < retry_after <= jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
    # 다른 사용자명은 IP 기준 한도 전까지 영향받지 않는다.
    assert (await _login(client, username="someone-else")).status_code == 401


async def test_successful_login_resets_the_username_counter(client):
    await _register(client)
    for _ in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS - 1):
        await _login(client, password="wrong-password")
    assert (await _login(client)).status_code == 200
    # 초기화되지 않았다면 이 중 두 번째 시도가 한도를 넘어 429 다.
    for _ in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS):
        assert (await _login(client, password="wrong-password")).status_code == 401


async def test_login_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(jwt_settings, "AUTH_LOGIN_IP_MAX_ATTEMPTS", 3)
    for name in ("a1", "a2", "a3"):
        assert (await _login(client, username=name)).status_code == 401
    assert (await _login(client, username="a4")).status_code == 429


async def test_register_is_rate_limited_per_ip(client):
    for i in range(jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS):
        assert (await _register(client, username=f"user{i}")).status_code == 201
    blocked = await _register(client, username="one-more")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


@pytest.mark.parametrize("path", ["/api/v1/auth/refresh", "/api/v1/auth/logout"])
async def test_refresh_endpoints_reject_access_token(client, path):
    await _register(client)
    access = (await _login(client)).json()["access_token"]
    resp = await client.post(path, json={"refresh_token": access})
    assert resp.status_code == 401


async def test_token_service_is_injected(client):
    """토큰 검증은 provider 로 주입된다 — override 한 서비스가 실제로 쓰인다."""

    class _RejectAll:
        def decode(self, token, expected_type):
            raise InvalidTokenException()

    await _register(client)
    access = (await _login(client)).json()["access_token"]
    app.dependency_overrides[get_token_service] = _RejectAll
    assert (await client.get("/api/v1/auth/me", headers=_bearer(access))).status_code == 401


async def test_every_auth_401_carries_www_authenticate_bearer(client):
    """로그인·refresh·logout·/me 의 모든 401 이 ``WWW-Authenticate: Bearer`` 를 싣는다 (e2e-policy-2 결정 3)."""
    await _register(client)
    tokens = (await _login(client)).json()
    await _refresh(client, tokens["refresh_token"])  # 소비 → 다음 사용은 재사용 탐지
    responses = {
        "login 비밀번호 틀림": await _login(client, password="wrong-password"),
        "login 없는 사용자": await _login(client, username="nobody"),
        "refresh 위조": await _refresh(client, "not-a-token"),
        "refresh access 토큰": await _refresh(client, tokens["access_token"]),
        "refresh 재사용": await _refresh(client, tokens["refresh_token"]),
        "logout 위조": await client.post(
            "/api/v1/auth/logout", json={"refresh_token": "not-a-token"}
        ),
        "me 토큰 없음": await client.get("/api/v1/auth/me"),
        "me refresh 토큰": await client.get(
            "/api/v1/auth/me", headers=_bearer(tokens["refresh_token"])
        ),
    }
    wrong = {
        name: (r.status_code, r.headers.get("www-authenticate"))
        for name, r in responses.items()
        if (r.status_code, r.headers.get("www-authenticate")) != (401, "Bearer")
    }
    assert not wrong, wrong


def test_every_401_exception_is_an_unauthorized_exception():
    """401 을 내는 앱 예외는 모두 ``UnauthorizedException`` 계열 — 헤더를 붙이는 곳이 하나다."""
    from app.core.exception import AppException, UnauthorizedException

    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    stray = [
        c.__name__
        for c in subclasses(AppException)
        if c.status_code == 401 and not issubclass(c, UnauthorizedException)
    ]
    assert not stray, stray
