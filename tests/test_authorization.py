"""라우트 권한 정책 (service-hardening 단계 F2 — ADR-014·ADR-015·ADR-016, INV-11).

README 의 권한 표와 같은 분류를 여기서 코드로 고정한다.

- PUBLIC     토큰 없이 된다.
- AUTH       로그인한 누구나(토큰 없으면 401).
- OWNER      작성자 본인(사용자 리소스는 본인) 또는 슈퍼유저 — 남이면 403.
- SUPERUSER  슈퍼유저 전용 — 일반 사용자는 403.

새 엔드포인트는 이 표에 분류되기 전까지 `test_every_operation_is_classified` 에서 막힌다.
토큰은 실제 ``TokenService`` 로 서명한다(``tests.auth_headers``) — 인증 의존성을 override 하지
않아야 서명·claims·``su`` 검사가 함께 시험된다.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.redis import get_redis
from app.core.security.dependencies import get_token_service
from app.features.blog.models.models import Post
from app.features.reply.models.models import Reply
from app.features.sns.models.models import SnsPost
from config import jwt_settings
from main import app
from tests.auth_headers import (
    OTHER_USER_ID,
    USER_ID,
    other_user_headers,
    superuser_headers,
    user_headers,
)
from tests.session_overrides import session_overrides

PUBLIC = "public"
AUTH = "auth"
OWNER = "owner"
SUPERUSER = "superuser"

# (메서드, 경로 템플릿) → 분류. README "권한 표" 와 같은 내용이다.
POLICY: dict[tuple[str, str], str] = {
    ("GET", "/health"): PUBLIC,
    ("GET", "/ready"): PUBLIC,
    ("POST", "/api/v1/auth/register"): PUBLIC,
    ("POST", "/api/v1/auth/login"): PUBLIC,
    ("POST", "/api/v1/auth/refresh"): PUBLIC,
    ("POST", "/api/v1/auth/logout"): PUBLIC,
    ("GET", "/api/v1/auth/me"): AUTH,
    ("GET", "/api/v1/blog/posts"): PUBLIC,
    ("GET", "/api/v1/blog/posts/{post_id}"): PUBLIC,
    ("POST", "/api/v1/blog/posts"): AUTH,
    ("PATCH", "/api/v1/blog/posts/{post_id}"): OWNER,
    ("DELETE", "/api/v1/blog/posts/{post_id}"): OWNER,
    ("GET", "/api/v1/sns/posts"): PUBLIC,
    ("GET", "/api/v1/sns/posts/{post_id}"): PUBLIC,
    ("POST", "/api/v1/sns/posts"): AUTH,
    ("PATCH", "/api/v1/sns/posts/{post_id}"): OWNER,
    ("DELETE", "/api/v1/sns/posts/{post_id}"): OWNER,
    ("GET", "/api/v1/reply/replies"): PUBLIC,
    ("GET", "/api/v1/reply/replies/{reply_id}"): PUBLIC,
    ("POST", "/api/v1/reply/replies"): AUTH,
    ("PATCH", "/api/v1/reply/replies/{reply_id}"): OWNER,
    ("DELETE", "/api/v1/reply/replies/{reply_id}"): OWNER,
    ("GET", "/api/v1/catalog/products"): PUBLIC,
    ("GET", "/api/v1/catalog/products/{product_id}"): PUBLIC,
    ("POST", "/api/v1/catalog/products"): SUPERUSER,
    ("PATCH", "/api/v1/catalog/products/{product_id}"): SUPERUSER,
    ("DELETE", "/api/v1/catalog/products/{product_id}"): SUPERUSER,
    ("GET", "/api/v1/reports/sales/daily"): SUPERUSER,
    ("GET", "/api/v1/home/access-logs"): SUPERUSER,
    ("GET", "/api/v1/home/access-logs/recent"): SUPERUSER,
    ("GET", "/api/v1/home/access-logs/by-ip/{ip_address}"): SUPERUSER,
    ("GET", "/api/v1/home/access-logs/by-user/{user_id}"): SUPERUSER,
    ("GET", "/api/v1/home/access-logs/stats"): SUPERUSER,
    ("GET", "/api/v1/user/users"): SUPERUSER,
    ("POST", "/api/v1/user/users"): SUPERUSER,
    ("GET", "/api/v1/user/users/{user_id}"): OWNER,
    ("PATCH", "/api/v1/user/users/{user_id}"): OWNER,
    ("DELETE", "/api/v1/user/users/{user_id}"): SUPERUSER,
}

# 슈퍼유저 전용 경로를 실제로 부를 때 쓰는 구체 요청(경로 변수·필수 query 채움).
SUPERUSER_REQUESTS: list[tuple[str, str, dict | None]] = [
    ("POST", "/api/v1/catalog/products", {"name": "Keyboard", "price": "10.00"}),
    ("PATCH", "/api/v1/catalog/products/p1", {"name": "Mouse"}),
    ("DELETE", "/api/v1/catalog/products/p1", None),
    ("GET", "/api/v1/reports/sales/daily?start_date=2026-08-01&end_date=2026-08-02", None),
    ("GET", "/api/v1/home/access-logs", None),
    ("GET", "/api/v1/home/access-logs/recent", None),
    ("GET", "/api/v1/home/access-logs/by-ip/10.0.0.1", None),
    ("GET", f"/api/v1/home/access-logs/by-user/{USER_ID}", None),
    ("GET", "/api/v1/home/access-logs/stats", None),
    ("GET", "/api/v1/user/users", None),
    (
        "POST",
        "/api/v1/user/users",
        {"username": "zed", "email": "zed@example.com", "password": "password123"},
    ),
    ("DELETE", f"/api/v1/user/users/{OTHER_USER_ID}", None),
]

# 로그인이 필요한 모든 분류(AUTH·OWNER·SUPERUSER)의 구체 요청 — 토큰 없으면 401.
PROTECTED_REQUESTS: list[tuple[str, str, dict | None]] = [
    ("GET", "/api/v1/auth/me", None),
    ("POST", "/api/v1/blog/posts", {"title": "t", "content": "c"}),
    ("PATCH", "/api/v1/blog/posts/p1", {"title": "t"}),
    ("DELETE", "/api/v1/blog/posts/p1", None),
    ("POST", "/api/v1/sns/posts", {"content": "c"}),
    ("PATCH", "/api/v1/sns/posts/p1", {"content": "c"}),
    ("DELETE", "/api/v1/sns/posts/p1", None),
    ("POST", "/api/v1/reply/replies", {"content": "c"}),
    ("PATCH", "/api/v1/reply/replies/r1", {"content": "c"}),
    ("DELETE", "/api/v1/reply/replies/r1", None),
    ("GET", f"/api/v1/user/users/{USER_ID}", None),
    ("PATCH", f"/api/v1/user/users/{USER_ID}", {"email": "a@example.com"}),
    *SUPERUSER_REQUESTS,
]

# 작성자가 있는 세 기능: (컬렉션 경로, 생성 본문, 수정 본문, 모델)
OWNED = {
    "blog": ("/api/v1/blog/posts", {"title": "t", "content": "c"}, {"title": "new"}, Post),
    "sns": ("/api/v1/sns/posts", {"content": "c"}, {"content": "new"}, SnsPost),
    "reply": ("/api/v1/reply/replies", {"content": "c"}, {"content": "new"}, Reply),
}


@pytest_asyncio.fixture
async def env():
    """``(client, maker, redis)`` — 기본 헤더가 없는(익명) 클라이언트."""
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


def _forge_access(**overrides) -> dict[str, str]:
    """운영 키로 서명하되 claims 일부를 바꾼 access 토큰 헤더."""
    now = datetime.now(UTC)
    claims = {
        "sub": USER_ID,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "j1",
        "iss": jwt_settings.JWT_ISSUER,
        "aud": jwt_settings.JWT_AUDIENCE,
        "username": "alice",
        "su": True,
    }
    secret = overrides.pop("secret", jwt_settings.ACCESS_TOKEN_SECRET_KEY)
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    token = jwt.encode(claims, secret, algorithm=jwt_settings.JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ 분류표


def test_every_operation_is_classified():
    """모든 공개 operation 이 권한 표에 있고, 로그인 필요 여부가 OpenAPI security 와 맞는다."""
    spec = app.openapi()
    seen: dict[tuple[str, str], bool] = {}
    for path, item in spec["paths"].items():
        if not (path.startswith("/api") or path in ("/health", "/ready")):
            continue
        for method, operation in item.items():
            seen[(method.upper(), path)] = bool(operation.get("security"))

    assert set(seen) == set(POLICY), "권한 표와 실제 operation 이 다릅니다 — README 권한 표도 함께"
    wrong = [key for key, secured in seen.items() if secured != (POLICY[key] != PUBLIC)]
    assert not wrong, f"OpenAPI security 표시가 분류와 다른 operation: {wrong}"


# ------------------------------------------------------------------ 401


@pytest.mark.parametrize(("method", "url", "body"), PROTECTED_REQUESTS)
async def test_protected_routes_reject_missing_token(client, method, url, body):
    resp = await client.request(method, url, json=body)
    assert resp.status_code == 401, resp.text
    # 저장소의 오류 형식(FastAPI 기본 HTTPException 의 "Not authenticated" 가 아니다).
    assert resp.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.parametrize(
    "headers",
    [
        # 허용 오차(leeway)를 넘겨 만료된 토큰.
        _forge_access(
            exp=datetime.now(UTC) - timedelta(seconds=jwt_settings.JWT_LEEWAY_SECONDS + 60)
        ),
        _forge_access(secret="x" * 64),
        _forge_access(su=None),
        _forge_access(su="yes"),
        {"Authorization": "Bearer not-a-jwt"},
    ],
    ids=["expired", "forged-signature", "no-su-claim", "su-not-bool", "garbage"],
)
async def test_invalid_access_tokens_are_rejected(client, headers):
    resp = await client.post(
        "/api/v1/blog/posts", json={"title": "t", "content": "c"}, headers=headers
    )
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_refresh_token_is_not_accepted_as_access(client):
    refresh, _ = get_token_service().issue_refresh(USER_ID, "fam1")
    resp = await client.get("/api/v1/user/users", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401


# ------------------------------------------------------------------ 403 / 슈퍼유저


@pytest.mark.parametrize(("method", "url", "body"), SUPERUSER_REQUESTS)
async def test_superuser_routes_reject_normal_user(client, method, url, body):
    resp = await client.request(method, url, json=body, headers=user_headers())
    assert resp.status_code == 403, resp.text
    assert resp.json()["error_code"] == "FORBIDDEN"


async def test_superuser_passes_admin_routes(client):
    headers = superuser_headers()
    created = await client.post(
        "/api/v1/catalog/products", json={"name": "Keyboard", "price": "10.00"}, headers=headers
    )
    assert created.status_code == 201
    assert (await client.get("/api/v1/user/users", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/home/access-logs", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/home/access-logs/stats", headers=headers)).status_code == 200


async def test_public_reads_need_no_token(client):
    for url in (
        "/api/v1/blog/posts",
        "/api/v1/sns/posts",
        "/api/v1/reply/replies",
        "/api/v1/catalog/products",
    ):
        assert (await client.get(url)).status_code == 200, url


# ------------------------------------------------------------------ 소유권


@pytest.mark.parametrize("feature", list(OWNED))
async def test_author_is_set_by_the_server(client, feature):
    collection, create, _, _ = OWNED[feature]
    resp = await client.post(
        collection,
        json={**create, "author": "someone-else", "author_id": OTHER_USER_ID},
        headers=user_headers(),
    )
    assert resp.status_code == 201
    assert resp.json()["author"] == "alice"
    assert resp.json()["author_id"] == USER_ID


@pytest.mark.parametrize("feature", list(OWNED))
async def test_other_user_cannot_modify(client, feature):
    collection, create, update, _ = OWNED[feature]
    item = (await client.post(collection, json=create, headers=user_headers())).json()
    url = f"{collection}/{item['id']}"

    patched = await client.patch(url, json=update, headers=other_user_headers())
    deleted = await client.delete(url, headers=other_user_headers())

    assert patched.status_code == 403
    assert deleted.status_code == 403
    still = (await client.get(url)).json()
    assert still == item


@pytest.mark.parametrize("feature", list(OWNED))
async def test_owner_can_modify_and_delete(client, feature):
    collection, create, update, _ = OWNED[feature]
    item = (await client.post(collection, json=create, headers=user_headers())).json()
    url = f"{collection}/{item['id']}"

    assert (await client.patch(url, json=update, headers=user_headers())).status_code == 200
    assert (await client.delete(url, headers=user_headers())).status_code == 204
    assert (await client.get(url)).status_code == 404


@pytest.mark.parametrize("feature", list(OWNED))
async def test_superuser_bypasses_ownership(client, feature):
    collection, create, update, _ = OWNED[feature]
    item = (await client.post(collection, json=create, headers=user_headers())).json()
    url = f"{collection}/{item['id']}"

    patched = await client.patch(url, json=update, headers=superuser_headers())
    assert patched.status_code == 200
    # 슈퍼유저가 고쳐도 작성자는 그대로다.
    assert patched.json()["author_id"] == USER_ID
    assert (await client.delete(url, headers=superuser_headers())).status_code == 204


@pytest.mark.parametrize("feature", list(OWNED))
async def test_legacy_rows_without_author_are_superuser_only(env, feature):
    """작성자 컬럼 도입 전의 행(author_id NULL)은 슈퍼유저만 고친다(ADR-015)."""
    client, maker, _ = env
    collection, create, update, model = OWNED[feature]
    async with maker() as session:
        row = model(**create, author="legacy")
        session.add(row)
        await session.commit()
    url = f"{collection}/{row.id}"

    assert (await client.patch(url, json=update, headers=user_headers())).status_code == 403
    assert (await client.patch(url, json=update, headers=superuser_headers())).status_code == 200
