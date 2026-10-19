"""/admin 로그인 (admin-login REQ-001, ADR-002~ADR-005).

SQLite 파일 DB + fakeredis 로 새 FastAPI 앱에 ``create_admin_interface`` 를 붙여 실제 HTTP 흐름을
돈다. 백엔드의 협력 객체(세션 팩토리·Redis)만 바꿔 넣고, 해시기·템플릿·sqladmin 은 운영 그대로다.
``main.app`` 의 조립(운영 협력 객체)은 맨 아래 두 테스트가 따로 본다.
"""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from starlette.requests import Request

from app.core.db.session import Base
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.registry import AppRegistry
from app.core.security.dependencies import get_password_hasher
from app.core.security.rate_limiter import RateLimiter
from app.features.admin import create_admin_interface
from app.features.auth import admin_auth
from app.features.auth.admin_auth import (
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_MAX_AGE,
    THROTTLED_MESSAGE,
    AdminAuthBackend,
)
from app.features.auth.exceptions import InvalidCredentialsException
from app.features.user.models.models import User
from config import session_settings
from scripts import create_superuser

BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
BOOTSTRAP_SRI = "sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"
PASSWORD = "correct-horse-1"
SECRET = "test-admin-session-secret-key-0123456789"

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# main.py 와 같은 발견 목록 — 모든 모델이 metadata 에 오르고(테이블 생성), 모든 ModelView 를 등록한다.
REGISTRY = AppRegistry()
REGISTRY.discover()
REGISTRY.import_models()


def build_admin_app(
    engine: AsyncEngine, session_factory: SessionFactory, redis: FakeAsyncRedis
) -> FastAPI:
    """운영과 같은 ``create_admin_interface`` 에 테스트 협력 객체로 만든 백엔드를 넣는다."""
    app = FastAPI()
    backend = AdminAuthBackend(
        session_factory=session_factory,
        hasher=get_password_hasher(),
        rate_limiter=lambda: RateLimiter(redis),
        ip_resolver=ClientIPResolver(0),
        secret_key=SECRET,
        https_only=False,
    )
    admin = create_admin_interface(app, engine, authentication_backend=backend)
    REGISTRY.install_admin(admin)
    return app


@pytest_asyncio.fixture
async def env(tmp_path):
    """``(client, maker, redis, db_url)`` — 파일 DB 라 다른 이벤트 루프(스크립트)에서도 연다."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'admin.db').as_posix()}"
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    redis = FakeAsyncRedis()
    app = build_admin_app(engine, session_factory, redis)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, maker, redis, db_url
    await engine.dispose()


async def _add_user(maker, username, *, superuser=True, active=True, password=PASSWORD) -> str:
    async with maker() as session:
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=get_password_hasher().hash(password),
            is_superuser=superuser,
            is_active=active,
        )
        session.add(user)
        await session.commit()
        return user.id


_CSRF_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')


async def csrf_token(client) -> str:
    """로그인 화면을 열어 세션에 묶인 CSRF 토큰을 꺼낸다(브라우저가 하는 일)."""
    page = await client.get("/admin/login")
    match = _CSRF_INPUT.search(page.text)
    assert match, "로그인 화면에 CSRF hidden 필드가 없다"
    return match.group(1)


async def _login(client, username, password=PASSWORD):
    data = {"username": username, "password": password, "csrf_token": await csrf_token(client)}
    return await client.post("/admin/login", data=data)


def _set_cookie(response) -> str:
    return "; ".join(response.headers.get_list("set-cookie")).lower()


# =============================================================================
# 백엔드 — 로그인 판정
# =============================================================================
async def test_superuser_login_redirects_to_index_and_sets_session_cookie(env):
    client, maker, *_ = env
    await _add_user(maker, "root")

    response = await _login(client, "root")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/")
    assert client.cookies.get(ADMIN_SESSION_COOKIE)


async def test_session_cookie_attributes(env):
    client, maker, *_ = env
    await _add_user(maker, "root")

    cookie = _set_cookie(await _login(client, "root"))

    assert cookie.startswith(f"{ADMIN_SESSION_COOKIE}=")
    assert "path=/admin" in cookie
    assert "samesite=strict" in cookie
    assert "httponly" in cookie
    assert f"max-age={ADMIN_SESSION_MAX_AGE}" in cookie
    assert ADMIN_SESSION_MAX_AGE == 8 * 60 * 60
    assert "secure" not in cookie  # https_only=False 로 조립했다


def test_admin_cookie_name_differs_from_access_log_session_cookie():
    assert ADMIN_SESSION_COOKIE != session_settings.SESSION_COOKIE_NAME


@pytest.mark.parametrize(
    ("case", "username", "password"),
    [
        ("wrong-password", "root", "wrong-password-1"),
        ("unknown-user", "nobody", PASSWORD),
        ("not-superuser", "plain", PASSWORD),
        ("inactive", "retired", PASSWORD),
    ],
)
async def test_failed_login_is_400_with_one_indistinguishable_message(
    env, case, username, password
):
    client, maker, *_ = env
    await _add_user(maker, "root")
    await _add_user(maker, "plain", superuser=False)
    await _add_user(maker, "retired", active=False)

    response = await _login(client, username, password)

    assert response.status_code == 400, case
    assert "alert alert-danger" in response.text
    assert InvalidCredentialsException.message in response.text
    # 세션 쿠키는 CSRF 토큰 때문에 이미 있다 — 로그인 상태가 아니라는 것을 본다.
    assert (await client.get("/admin/")).status_code == 302


async def test_too_many_attempts_rerenders_login_with_429_and_retry_after(env, monkeypatch):
    client, maker, redis, _ = env
    await _add_user(maker, "root")
    monkeypatch.setattr(admin_auth.jwt_settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)

    for _ in range(2):
        assert (await _login(client, "root", "wrong-password-1")).status_code == 400
    response = await _login(client, "root")  # 맞는 비밀번호여도 창 안에서는 막힌다

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert THROTTLED_MESSAGE in response.text
    assert '<form action="' in response.text
    # API 로그인(auth:rl:)과 키를 나눠 센다.
    keys = {key.decode() for key in await redis.keys("*")}
    assert keys and all(key.startswith("admin:rl:") for key in keys)


async def test_successful_login_resets_the_per_user_counter(env, monkeypatch):
    client, maker, *_ = env
    await _add_user(maker, "root")
    monkeypatch.setattr(admin_auth.jwt_settings, "AUTH_LOGIN_MAX_ATTEMPTS", 2)

    assert (await _login(client, "root", "wrong-password-1")).status_code == 400
    assert (await _login(client, "root")).status_code == 302
    assert (await _login(client, "root", "wrong-password-1")).status_code == 400
    assert (await _login(client, "root")).status_code == 302


async def test_login_replaces_any_existing_session_content(env):
    """세션 고정 방지 — 로그인 전에 심어 둔 값은 남지 않고 사용자 id 만 남는다."""
    _, maker, redis, _ = env
    user_id = await _add_user(maker, "root")
    backend = AdminAuthBackend(
        session_factory=lambda: maker(),
        hasher=get_password_hasher(),
        rate_limiter=lambda: RateLimiter(redis),
        ip_resolver=ClientIPResolver(0),
        secret_key=SECRET,
        https_only=False,
    )
    session = {"user_id": "attacker-chosen", "planted": "x", "csrf_token": "known-token"}
    body = f"username=root&password={PASSWORD}&csrf_token=known-token".encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/admin/login",
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            "client": ("10.0.0.1", 1234),
            "session": session,
        },
        receive,
    )

    assert await backend.login(request) is True
    assert session == {"user_id": user_id}


# =============================================================================
# 로그인 폼 CSRF (security-ops-hardening ADR-003) — synchronizer token
# =============================================================================
async def _post_login(client, **data):
    return await client.post(
        "/admin/login", data={"username": "root", "password": PASSWORD, **data}
    )


async def test_login_page_carries_a_session_bound_csrf_token(env):
    client, *_ = env

    first = await csrf_token(client)
    again = await csrf_token(client)

    assert len(first) >= 43  # token_urlsafe(32)
    assert first == again  # 같은 세션 안에서는 유지 — 탭을 두 번 열어도 앞 폼이 죽지 않는다
    assert client.cookies.get(ADMIN_SESSION_COOKIE)


@pytest.mark.parametrize(
    "token", [None, "", "forged-token-value"], ids=["missing", "empty", "wrong"]
)
async def test_post_without_a_valid_token_is_403_before_rate_limit_and_credentials(
    env, monkeypatch, token
):
    client, maker, redis, _ = env
    await _add_user(maker, "root")
    await csrf_token(client)  # 세션에는 정상 토큰이 있다

    async def must_not_run(*_args, **_kwargs):
        raise AssertionError("CSRF 실패인데 자격 확인을 했다")

    monkeypatch.setattr(admin_auth, "verify_credentials", must_not_run)
    response = await _post_login(client, **({} if token is None else {"csrf_token": token}))

    assert response.status_code == 403
    assert admin_auth.CSRF_FAILED_MESSAGE in response.text
    assert await redis.keys("*") == []  # 레이트 리밋 카운터도 건드리지 않는다
    assert (await client.get("/admin/")).status_code == 302


async def test_post_without_any_session_is_403(env):
    client, maker, *_ = env
    await _add_user(maker, "root")

    response = await _post_login(client, csrf_token="anything")

    assert response.status_code == 403


async def test_rerendered_form_after_403_lets_the_user_retry(env):
    client, maker, *_ = env
    await _add_user(maker, "root")

    rejected = await _post_login(client)  # 토큰 없이(예: 만료된 탭)
    token = _CSRF_INPUT.search(rejected.text).group(1)
    retried = await _post_login(client, csrf_token=token)

    assert rejected.status_code == 403
    assert retried.status_code == 302


async def test_token_from_another_session_is_rejected(env):
    client, maker, *_ = env
    await _add_user(maker, "root")
    attacker_token = await csrf_token(client)
    client.cookies.clear()
    await csrf_token(client)  # 피해자 세션은 자기 토큰을 갖는다

    response = await _post_login(client, csrf_token=attacker_token)

    assert response.status_code == 403


async def test_token_rotates_after_successful_login(env):
    client, maker, *_ = env
    await _add_user(maker, "root")
    before = await csrf_token(client)

    assert (await _post_login(client, csrf_token=before)).status_code == 302
    after = await csrf_token(client)

    assert after != before


async def test_token_comparison_is_constant_time(env, monkeypatch):
    client, maker, *_ = env
    await _add_user(maker, "root")
    token = await csrf_token(client)
    calls = []
    real = admin_auth.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(admin_auth.hmac, "compare_digest", spy)
    assert (await _post_login(client, csrf_token=token)).status_code == 302
    # hmac 모듈은 세션 쿠키 서명 검증도 쓴다 — CSRF 비교 호출이 그중에 있는지 본다.
    assert (token.encode(), token.encode()) in calls


async def test_non_ascii_token_is_rejected_not_500(env):
    client, maker, *_ = env
    await _add_user(maker, "root")
    await csrf_token(client)

    assert (await _post_login(client, csrf_token="토큰")).status_code == 403


# =============================================================================
# 백엔드 — 요청별 인증·로그아웃
# =============================================================================
async def test_demoted_user_is_rejected_on_the_next_request(env):
    client, maker, *_ = env
    user_id = await _add_user(maker, "root")
    await _login(client, "root")
    assert (await client.get("/admin/")).status_code == 200

    async with maker() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_superuser=False))
        await session.commit()
    response = await client.get("/admin/")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert client.cookies.get(ADMIN_SESSION_COOKIE) is None  # 세션을 비웠다


async def test_deactivated_user_is_rejected_on_the_next_request(env):
    client, maker, *_ = env
    user_id = await _add_user(maker, "root")
    await _login(client, "root")

    async with maker() as session:
        await session.execute(update(User).where(User.id == user_id).values(is_active=False))
        await session.commit()

    assert (await client.get("/admin/")).status_code == 302


async def test_logout_clears_the_session(env):
    client, maker, *_ = env
    await _add_user(maker, "root")
    await _login(client, "root")

    response = await client.get("/admin/logout")

    assert response.status_code == 302
    assert client.cookies.get(ADMIN_SESSION_COOKIE) is None
    assert (await client.get("/admin/")).status_code == 302


# =============================================================================
# 로그인 화면
# =============================================================================
async def test_login_page_is_the_bootstrap_override(env):
    client, *_ = env

    response = await client.get("/admin/login")

    assert response.status_code == 200
    html = response.text
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="ko">' in html
    assert 'name="viewport"' in html
    assert f'href="{BOOTSTRAP_CSS}"' in html
    assert f'integrity="{BOOTSTRAP_SRI}"' in html
    assert 'crossorigin="anonymous"' in html
    assert "<script" not in html  # JS 없음
    assert re.search(r'<form action="http://test/admin/login" method="POST">', html)
    assert re.search(
        r'id="username" name="username"[^>]*autocomplete="username" required autofocus', html
    )
    assert re.search(
        r'id="password" name="password" type="password"[^>]*autocomplete="current-password" required',
        html,
    )
    assert '<label for="username"' in html and '<label for="password"' in html
    assert "alert-danger" not in html


async def test_error_message_is_html_escaped(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr(InvalidCredentialsException, "message", "<script>alert(1)</script>")

    response = await _login(client, "nobody")

    assert response.status_code == 400
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>alert(1)" not in response.text


def test_template_overrides_the_packaged_login_template():
    from app.features.admin import ADMIN_TEMPLATES_DIR

    assert (ADMIN_TEMPLATES_DIR / "sqladmin" / "login.html").is_file()
    assert Path(ADMIN_TEMPLATES_DIR).parts[-3:] == ("app", "templates", "admin")


# =============================================================================
# 통합 — create_superuser 로 만든 계정으로 /admin 로그인
# =============================================================================
def _script_session_factory(db_url: str) -> SessionFactory:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        # 스크립트는 asyncio.run 으로 자기 루프를 연다 — 엔진도 그 루프에서 만들고 닫는다.
        engine = create_async_engine(db_url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    return factory


async def test_create_superuser_then_full_admin_login_flow(env):
    client, maker, _, db_url = env
    code = await asyncio.to_thread(
        create_superuser.main,
        ["--username", "ops-admin", "--email", "ops@example.com", "--password-stdin"],
        session_factory=_script_session_factory(db_url),
        stdin=io.StringIO(PASSWORD + "\n"),
    )
    assert code == 0
    await _add_user(maker, "regular", superuser=False)

    first = await client.get("/admin/")
    assert first.status_code == 302 and first.headers["location"].endswith("/admin/login")
    assert (await _login(client, "ops-admin", "wrong-password-1")).status_code == 400
    assert (await _login(client, "regular")).status_code == 400  # 일반 사용자는 실패
    assert (await _login(client, "ops-admin")).status_code == 302
    assert (await client.get("/admin/")).status_code == 200
    assert (await client.get("/admin/logout")).status_code == 302
    assert (await client.get("/admin/")).status_code == 302


# =============================================================================
# main.app 조립 — 운영 협력 객체
# =============================================================================
def test_main_app_admin_uses_the_login_backend():
    import main
    from config import app_settings

    backend = main.admin.authentication_backend
    assert isinstance(backend, AdminAuthBackend)
    assert backend.templates is main.admin.templates
    options = backend.middlewares[0].kwargs
    assert options["secret_key"] == session_settings.SESSION_SECRET_KEY
    assert options["https_only"] is (app_settings.ENV in ("staging", "production"))


async def test_main_app_redirects_anonymous_admin_to_the_login_page():
    import main

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        index = await client.get("/admin/")
        page = await client.get("/admin/login")

    assert index.status_code == 302 and index.headers["location"].endswith("/admin/login")
    assert page.status_code == 200 and BOOTSTRAP_SRI in page.text


# =============================================================================
# 설정 제거 회귀 — 예전 "무인증 허용" 확인 플래그
# =============================================================================
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REMOVED_FLAG = "ADMIN_ALLOW_UNAUTHENTICATED"


def test_unauthenticated_admin_flag_is_gone_from_code_and_current_docs():
    from config import AppSettings

    assert _REMOVED_FLAG not in AppSettings.model_fields
    targets = [
        *(_REPO_ROOT / "app").rglob("*.py"),
        *(_REPO_ROOT / "app").rglob("*.html"),
        _REPO_ROOT / "main.py",
        _REPO_ROOT / "config.py",
        _REPO_ROOT / ".env.example",
        _REPO_ROOT / "README.md",
        *(_REPO_ROOT / "docs" / "guides").glob("*.*"),
    ]
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in targets
        if _REMOVED_FLAG in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_leftover_flag_in_environment_does_not_break_settings(monkeypatch):
    from config import AppSettings

    monkeypatch.setenv(_REMOVED_FLAG, "true")
    assert AppSettings(_env_file=None).ADMIN_DISABLED is False  # type: ignore[call-arg]


# =============================================================================
# 세션 사용 범위 — 서명 세션은 /admin 전용이다 (admin-login ADR-008)
# =============================================================================
def _signed_admin_cookie(secret: str, user_id: str) -> str:
    """starlette ``SessionMiddleware`` 와 같은 방식으로 서명한 세션 쿠키 값."""
    import json
    from base64 import b64encode

    from itsdangerous import TimestampSigner

    data = b64encode(json.dumps({"user_id": user_id}).encode("utf-8"))
    return TimestampSigner(secret).sign(data).decode("utf-8")


async def test_crafted_cookie_is_a_valid_admin_session(env):
    """대조군 — 아래 API 테스트가 쓰는 쿠키가 실제로 /admin 에서는 통하는 쿠키다."""
    client, maker, *_ = env
    user_id = await _add_user(maker, "root")
    cookie = _signed_admin_cookie(SECRET, user_id)

    response = await client.get("/admin/", headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={cookie}"})

    assert response.status_code == 200


def test_session_middleware_lives_only_in_the_admin_sub_app():
    import main

    assert "SessionMiddleware" not in [m.cls.__name__ for m in main.app.user_middleware]
    assert "SessionMiddleware" in [m.cls.__name__ for m in main.admin.admin.user_middleware]


async def test_admin_session_cookie_does_not_authenticate_the_api():
    import main

    cookie = _signed_admin_cookie(session_settings.SESSION_SECRET_KEY, "any-superuser-id")
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/me", headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={cookie}"}
        )

    assert response.status_code == 401


async def test_admin_session_cookie_is_never_set_outside_admin():
    import main

    cookie = _signed_admin_cookie(session_settings.SESSION_SECRET_KEY, "any-superuser-id")
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.get(path, headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={cookie}"})
            for path in ("/health", "/openapi.json", "/api/v1/auth/me", "/does-not-exist")
        ]

    assert all(ADMIN_SESSION_COOKIE not in _set_cookie(r) for r in responses)


# =============================================================================
# 등록된 모든 관리 화면 — 로그인한 슈퍼유저의 목록·필터·상세 (admin-login F-006)
# =============================================================================
def _filter_params(view) -> list[dict[str, str]]:
    """뷰의 필터마다 쿼리 — bool 은 true, 날짜 필터는 연산 3종 + 잘못된 입력 1건,
    연산 필터는 equals 1(문자열·숫자 모두 유효)."""
    from sqladmin.filters import BooleanFilter

    from app.core.admin_filters import LocalDateFilter

    params = []
    for flt in view.column_filters:
        name = flt.parameter_name
        if isinstance(flt, BooleanFilter):
            params.append({name: "true"})
        elif isinstance(flt, LocalDateFilter):
            params += [{name: "2026-10-19", f"{name}_op": op} for op, _ in flt.OPERATIONS]
            params.append({name: "not-a-date", f"{name}_op": "on"})  # 500 이 아니라 필터 없이 200
        else:
            params.append({name: "1", f"{name}_op": "equals"})
    return params


def _admin_views() -> list:
    from app.features.admin import ADMIN_TEMPLATES_DIR  # noqa: F401 - 조립 모듈 로드 확인

    class _Collect:
        def __init__(self) -> None:
            self.views: list = []

        def add_view(self, view) -> None:
            self.views.append(view)

    collector = _Collect()
    REGISTRY.install_admin(collector)
    return collector.views


@pytest.mark.parametrize("view", _admin_views(), ids=lambda v: v.identity)
async def test_every_admin_list_page_and_filter_returns_200(env, view):
    client, maker, *_ = env
    await _add_user(maker, "root")
    assert (await _login(client, "root")).status_code == 302

    assert (await client.get(f"/admin/{view.identity}/list")).status_code == 200
    # 모든 뷰가 필터를 가진다(최소 created_at 날짜 필터). 필터마다 쿼리를 돌린다.
    for params in _filter_params(view):
        response = await client.get(f"/admin/{view.identity}/list", params=params)
        assert response.status_code == 200, (view.identity, params)


async def test_admin_detail_page_returns_200(env):
    client, maker, *_ = env
    user_id = await _add_user(maker, "root")
    await _login(client, "root")

    response = await client.get(f"/admin/user/details/{user_id}")

    assert response.status_code == 200
    assert "root" in response.text


def test_filter_queries_are_actually_exercised():
    """대조군 — 목록 테스트가 필터를 하나도 돌리지 않는 헛통과가 아니다
    (기존 14개 + 7개 뷰의 날짜 필터 × 4 쿼리)."""
    assert sum(len(_filter_params(v)) for v in _admin_views()) == 14 + 7 * 4


def test_every_view_with_created_at_has_the_local_date_filter():
    """security-ops-hardening ADR-004 — created_at 이 있는 모든 관리 목록은 날짜로 거를 수 있다."""
    from app.core.admin_filters import LocalDateFilter

    missing = [
        view.identity
        for view in _admin_views()
        if hasattr(view.model, "created_at")
        and not any(
            isinstance(f, LocalDateFilter) and f.parameter_name == "created_at"
            for f in view.column_filters
        )
    ]
    assert missing == []
    assert len(_admin_views()) == 7


async def test_date_filter_narrows_the_real_list_page(env):
    """실제 목록 화면 — 오늘(TIME_ZONE) 가입한 root 는 '같은 날' 에 보이고 '이전' 에는 안 보인다."""
    from config import timezone_settings

    client, maker, *_ = env
    await _add_user(maker, "root")
    await _add_user(maker, "datefilterprobe")
    assert (await _login(client, "root")).status_code == 302
    today = timezone_settings.now().date().isoformat()

    async def listed(op: str) -> bool:
        params = {"created_at": today, "created_at_op": op}
        response = await client.get("/admin/user/list", params=params)
        assert response.status_code == 200
        return "datefilterprobe" in response.text

    assert await listed("on") is True
    assert await listed("on_or_after") is True
    assert await listed("before") is False
