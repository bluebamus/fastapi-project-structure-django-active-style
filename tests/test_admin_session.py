"""/admin 관리 세션(Redis 서버 세션)·CSRF·기간 필터 (admin-session-hardening ADR-001~ADR-005).

``tests/test_admin_login.py`` 의 조립(SQLite 파일 DB + fakeredis + 운영 ``create_admin_interface``)을
그대로 쓴다. 실제 DB·Redis 서버에 접속하지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.session import Base
from app.core.security.admin_session import AdminSessionStore
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.dependencies import get_password_hasher
from app.core.security.refresh_store import RefreshTokenStore
from app.features.auth.admin_auth import ADMIN_SESSION_COOKIE, CSRF_REJECTED_MESSAGE
from app.features.catalog.models.models import Product
from app.features.user.schemas.user_schema import UserUpdate
from app.features.user.services.user_service import UserService
from tests.test_admin_login import (
    IDLE,
    MAX_AGE,
    _add_user,
    _login,
    build_admin_app,
    logout,
    page_token,
    session_store,
)

_SID = re.compile(r"^[A-Za-z0-9_-]{43}$")  # token_urlsafe(32)
_HMAC_KEY = re.compile(r"^admin:sess:[0-9a-f]{64}$")


class Clock:
    def __init__(self) -> None:
        import time

        self.now = time.time()

    def __call__(self) -> float:
        return self.now


@pytest_asyncio.fixture
async def env(tmp_path):
    """``(client, maker, redis, clock, new_client)`` — 시계를 바꿀 수 있는 저장소로 조립한다."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'admin.db').as_posix()}"
    engine = create_async_engine(db_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = FakeAsyncRedis()
    clock = Clock()
    app = build_admin_app(engine, maker, redis, lambda: session_store(redis, clock=clock))
    clients: list[AsyncClient] = []

    def new_client() -> AsyncClient:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield new_client(), maker, redis, clock, new_client
    for client in clients:
        await client.aclose()
    await engine.dispose()


async def _logged_in(env, username: str = "root") -> str:
    client, maker, *_ = env
    user_id = await _add_user(maker, username)
    assert (await _login(client, username)).status_code == 302
    return user_id


def _sid(client) -> str:
    return client.cookies.get(ADMIN_SESSION_COOKIE)


# =============================================================================
# §1 Redis 서버 세션
# =============================================================================
async def test_cookie_carries_only_a_random_session_id(env):
    client, _, redis, *_ = env
    user_id = await _logged_in(env)

    sid = _sid(client)
    assert _SID.match(sid)
    assert user_id not in sid and "." not in sid  # 서명·내용이 없다
    keys = sorted(k.decode() for k in await redis.keys("admin:sess:*"))
    assert keys == [session_store(redis).key(sid)]
    assert _HMAC_KEY.match(keys[0]) and sid not in keys[0]
    raw = (await redis.get(keys[0])).decode()
    assert sid not in raw and f'"user_id": "{user_id}"' in raw
    assert await redis.smembers(f"admin:user_sessions:{user_id}") == {keys[0].encode()}


async def test_logout_kills_copied_cookie(env):
    client, _, redis, _, new_client = env
    await _logged_in(env)
    copied = _sid(client)

    assert (await logout(client)).status_code == 302
    thief = new_client()
    response = await thief.get("/admin/", headers={"Cookie": f"{ADMIN_SESSION_COOKIE}={copied}"})

    assert response.status_code == 302 and response.headers["location"].endswith("/admin/login")
    assert await redis.keys("admin:sess:*") == []
    # Redis 에 없는 세션 ID 쿠키는 지운다.
    assert f"{ADMIN_SESSION_COOKIE}=null" in response.headers.get("set-cookie", "")


async def test_login_rotates_the_session_id_and_deletes_the_old_key(env):
    client, maker, redis, *_ = env
    await _add_user(maker, "root")
    await client.get("/admin/login")  # 로그인 전 익명 세션(CSRF 토큰)
    before = _sid(client)
    old_key = session_store(redis).key(before)
    assert await redis.exists(old_key)

    assert (await _login(client, "root")).status_code == 302

    assert _sid(client) != before
    assert not await redis.exists(old_key)


async def test_each_request_resets_the_idle_ttl(env):
    client, _, redis, *_ = env
    await _logged_in(env)
    key = session_store(redis).key(_sid(client))
    await redis.expire(key, 5)

    assert (await client.get("/admin/")).status_code == 200

    assert IDLE - 5 <= await redis.ttl(key) <= IDLE


async def test_idle_expiry_logs_out(env):
    client, _, redis, *_ = env
    await _logged_in(env)
    await redis.delete(session_store(redis).key(_sid(client)))  # 미사용 만료로 TTL 이 다 됐다

    assert (await client.get("/admin/")).status_code == 302


async def test_absolute_expiry_is_never_extended(env):
    client, _, redis, clock, _ = env
    await _logged_in(env)
    key = session_store(redis).key(_sid(client))

    clock.now += MAX_AGE - 10
    assert (await client.get("/admin/")).status_code == 200
    assert 0 < await redis.ttl(key) <= 10  # 미사용 만료가 절대 만료를 넘지 않는다

    clock.now += 11
    assert await redis.exists(key)  # Redis TTL 이 아직이어도
    assert (await client.get("/admin/")).status_code == 302  # 생성 시각 기준으로 거부


def _service(maker_session, redis) -> UserService:
    return UserService(
        maker_session,
        get_password_hasher(),
        RefreshTokenStore(redis, 60),
        OwnershipPolicy(),
        session_store(redis),
    )


_ROOT = Principal(id="op", username="op", is_superuser=True)


@pytest.mark.parametrize("change", ["deactivate", "demote", "delete"])
async def test_user_changes_revoke_every_admin_session_of_that_user(env, change):
    client, maker, redis, _, new_client = env
    user_id = await _logged_in(env)
    other = new_client()
    assert (await _login(other, "root")).status_code == 302
    bystander = new_client()
    await _add_user(maker, "other-admin")
    assert (await _login(bystander, "other-admin")).status_code == 302
    assert len(await redis.smembers(f"admin:user_sessions:{user_id}")) == 2

    async with maker() as session:
        service = _service(session, redis)
        if change == "delete":
            await service.delete_user(user_id)
        else:
            field = "is_active" if change == "deactivate" else "is_superuser"
            await service.update_user(user_id, UserUpdate(**{field: False}), _ROOT)
        # DB 는 되돌린다 — 매 요청 DB 확인(이중 방어)이 아니라 세션 폐기로 끊기는지 본다.
        await session.rollback()

    for browser in (client, other):
        assert (await browser.get("/admin/")).status_code == 302
    assert (await bystander.get("/admin/")).status_code == 200
    assert not await redis.exists(f"admin:user_sessions:{user_id}")


async def test_profile_update_keeps_admin_sessions(env):
    client, maker, redis, *_ = env
    user_id = await _logged_in(env)

    async with maker() as session:
        await _service(session, redis).update_user(
            user_id, UserUpdate(email="x@example.com"), _ROOT
        )
        await session.commit()

    assert (await client.get("/admin/")).status_code == 200


def test_user_service_provider_injects_the_admin_session_store():
    import inspect

    from app.features.user.dependencies.user_dependencies import get_user_service

    default = inspect.signature(get_user_service).parameters["admin_sessions"].default
    from app.core.security.dependencies import get_admin_session_store

    assert default.dependency is get_admin_session_store


def test_admin_disabled_builds_no_store(monkeypatch):
    from app.core.security import dependencies

    monkeypatch.setattr(dependencies.app_settings, "ADMIN_DISABLED", True)
    assert dependencies.get_admin_session_store(FakeAsyncRedis()) is None
    monkeypatch.setattr(dependencies.app_settings, "ADMIN_DISABLED", False)
    assert isinstance(dependencies.get_admin_session_store(FakeAsyncRedis()), AdminSessionStore)


class _BrokenRedis(FakeAsyncRedis):
    async def get(self, *args, **kwargs):
        raise RedisConnectionError("down")


@pytest.mark.parametrize("failure", ["no-client", "connection-error"])
async def test_redis_failure_fails_closed_with_503(tmp_path, failure):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'a.db').as_posix()}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    broken = _BrokenRedis()

    def store() -> AdminSessionStore:
        if failure == "no-client":
            raise RedisConnectionError("Redis 가 준비되지 않았습니다.")
        return session_store(broken)

    app = build_admin_app(engine, maker, broken, store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/admin/user/list", headers={"Cookie": f"{ADMIN_SESSION_COOKIE}=whatever"}
        )
    await engine.dispose()

    assert response.status_code == 503  # 통과(200)도 500 도 아니다


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"ADMIN_SESSION_IDLE_SECONDS": 7200, "ADMIN_SESSION_MAX_AGE_SECONDS": 3600}, "이하"),
        ({"ADMIN_SESSION_IDLE_SECONDS": 59}, "greater than or equal"),
        ({"ADMIN_SESSION_MAX_AGE_SECONDS": 0}, "greater than or equal"),
    ],
)
def test_session_settings_are_validated(values, message):
    from config import SessionSettings

    with pytest.raises(ValidationError, match=message):
        SessionSettings(_env_file=None, **values)  # type: ignore[call-arg]


def test_session_settings_defaults():
    from config import SessionSettings

    settings = SessionSettings(_env_file=None)  # type: ignore[call-arg]
    assert (settings.ADMIN_SESSION_MAX_AGE_SECONDS, settings.ADMIN_SESSION_IDLE_SECONDS) == (
        28800,
        1800,
    )


# =============================================================================
# §2 로그인 이후 CSRF — 생성·수정·삭제·일괄 삭제·로그아웃
# =============================================================================
async def _product(maker, name: str = "p1") -> str:
    async with maker() as session:
        product = Product(name=name, price=10)
        session.add(product)
        await session.commit()
        return str(product.id)


async def _count_products(maker) -> int:
    async with maker() as session:
        return len((await session.execute(select(Product))).scalars().all())


async def _send(client, kind: str, maker, how: str, token: str | None):
    """kind 요청을 토큰 위치(how: form/header)와 값으로 보낸다."""
    headers = {"X-CSRF-Token": token} if how == "header" and token is not None else {}
    form = {"csrf_token": token} if how == "form" and token is not None else {}
    if kind == "create":
        return await client.post(
            "/admin/product/create",
            data={"name": "created", "price": "12.50", "is_active": "y", "save": "Save", **form},
            headers=headers,
        )
    if kind == "edit":
        pk = await _product(maker)
        return await client.post(
            f"/admin/product/edit/{pk}",
            data={"name": "edited", "price": "1", "save": "Save", **form},
            headers=headers,
        )
    if kind == "delete":
        pk = await _product(maker)
        return await client.request(
            "DELETE", f"/admin/product/delete?pks={pk}", headers=headers, data=form or None
        )
    if kind == "bulk-delete":
        pks = [await _product(maker, f"p{i}") for i in range(2)]
        return await client.request(
            "DELETE", f"/admin/product/delete?pks={','.join(pks)}", headers=headers
        )
    assert kind == "logout"
    return await client.post("/admin/logout", data=form, headers=headers)


_KINDS = ["create", "edit", "delete", "bulk-delete", "logout"]


@pytest.mark.parametrize("kind", _KINDS)
@pytest.mark.parametrize("token", ["missing", "wrong"])
async def test_state_changing_request_without_a_valid_token_is_403(env, kind, token):
    client, maker, *_ = env
    await _logged_in(env)
    before = await _count_products(maker)
    value = None if token == "missing" else "forged-token-value"
    how = "form" if kind in ("create", "edit", "logout") else "header"

    response = await _send(client, kind, maker, how, value)

    assert response.status_code == 403
    assert CSRF_REJECTED_MESSAGE in response.text
    after = await _count_products(maker)
    assert after == before + {"create": 0, "edit": 1, "delete": 1, "bulk-delete": 2}.get(kind, 0)
    assert (await client.get("/admin/")).status_code == 200  # 로그아웃되지 않았다


_EXPECTED = {"create": 302, "edit": 302, "delete": 200, "bulk-delete": 200, "logout": 302}


# 삭제는 sqladmin 이 본문 없는 AJAX DELETE 로 보낸다 — 스크립트가 헤더로만 싣는다.
@pytest.mark.parametrize(
    ("kind", "how"),
    [(k, h) for k in _KINDS for h in ("form", "header") if not (h == "form" and "delete" in k)],
)
async def test_state_changing_request_with_the_session_token_succeeds(env, kind, how):
    client, maker, *_ = env
    await _logged_in(env)
    token = await page_token(client)

    response = await _send(client, kind, maker, how, token)

    assert response.status_code == _EXPECTED[kind], response.text[:300]
    if kind == "create":  # 본문을 버퍼링한 뒤 다시 흘려보냈다 — 실제로 저장됐다
        async with maker() as session:
            names = [p.name for p in (await session.execute(select(Product))).scalars()]
        assert names == ["created"]
    if kind in ("delete", "bulk-delete"):
        assert await _count_products(maker) == 0
    if kind == "logout":
        assert (await client.get("/admin/")).status_code == 302


async def test_token_from_another_session_is_rejected(env):
    client, maker, _, _, new_client = env
    await _logged_in(env)
    attacker = new_client()
    await _add_user(maker, "attacker")
    assert (await _login(attacker, "attacker")).status_code == 302
    foreign = await page_token(attacker)

    response = await _send(client, "create", maker, "header", foreign)

    assert response.status_code == 403


async def test_get_requests_need_no_token(env):
    client, maker, *_ = env
    await _logged_in(env)
    pk = await _product(maker)

    for path in (
        "/admin/",
        "/admin/product/list",
        f"/admin/product/details/{pk}",
        "/admin/product/create",
        "/admin/product/export/csv",
        "/admin/statics/js/main.js",
    ):
        assert (await client.get(path)).status_code == 200, path


async def test_logout_cannot_happen_by_get(env):
    client, *_ = env
    await _logged_in(env)

    response = await client.get("/admin/logout")

    assert response.status_code == 405
    assert (await client.get("/admin/")).status_code == 200


async def test_csrf_failure_is_not_the_login_page(env):
    client, maker, *_ = env
    await _logged_in(env)

    response = await _send(client, "create", maker, "form", None)

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/plain")
    assert 'name="password"' not in response.text


async def test_anonymous_post_is_403_before_login_redirect(env):
    """세션이 없으면(익명) 토큰도 없다 — 거부한다."""
    client, maker, *_ = env

    assert (await _send(client, "create", maker, "form", "anything")).status_code == 403


@pytest.mark.parametrize("page", ["index", "list", "create", "edit", "details"])
async def test_rendered_admin_pages_carry_the_meta_token_and_script(env, page):
    client, maker, *_ = env
    await _logged_in(env)
    pk = await _product(maker)
    path = {
        "index": "/admin/",
        "list": "/admin/product/list",
        "create": "/admin/product/create",
        "edit": f"/admin/product/edit/{pk}",
        "details": f"/admin/product/details/{pk}",
    }[page]

    html = (await client.get(path)).text
    token = await page_token(client, path)

    assert client.cookies.get(ADMIN_SESSION_COOKIE)
    assert token and len(token) >= 43
    assert '<meta name="admin-logout-url" content="http://test/admin/logout">' in html
    assert 'setRequestHeader("X-CSRF-Token", token)' in html  # XHR($.ajax DELETE)
    assert 'headers.set("X-CSRF-Token", token)' in html  # fetch(가져오기)
    assert 'input.name = "csrf_token"' in html  # 폼 hidden 필드
    assert 'form.method = "POST"' in html  # 로그아웃 링크 → POST


async def test_page_token_is_the_session_token_and_rotates_on_login(env):
    client, maker, *_ = env
    await _add_user(maker, "root")
    login_page = await client.get("/admin/login")
    anonymous = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text).group(1)

    assert (await _login(client, "root")).status_code == 302
    assert await page_token(client) != anonymous
    assert await page_token(client) == await page_token(client, "/admin/product/list")


_PKG = Path(__import__("sqladmin").__file__).parent / "templates" / "sqladmin"


def test_packaged_templates_still_fit_the_base_override():
    """sqladmin 을 올렸을 때 덮어쓴 base.html 이 원본과 어긋나면 여기서 실패한다."""
    base = (_PKG / "base.html").read_text(encoding="utf-8")
    assert "{% block head_tail %}" in base
    overriding = [
        p.name
        for p in _PKG.rglob("*.html")
        if p.name != "base.html" and "block head_tail" in p.read_text(encoding="utf-8")
    ]
    assert overriding == []  # 어떤 화면도 head_tail 을 덮어쓰지 않아 스크립트가 항상 실린다
    layout = (_PKG / "layout.html").read_text(encoding="utf-8")
    assert "request.url_for('admin:logout')" in layout  # 스크립트가 가로채는 링크
    main_js = (_PKG.parent.parent / "statics" / "js" / "main.js").read_text(encoding="utf-8")
    assert "method: 'DELETE'" in main_js  # 삭제는 jQuery XHR
    assert "fetch(frm.attr('action')" in main_js  # 가져오기는 fetch
    filters = (_PKG / "filters" / "operation_filter.html").read_text(encoding="utf-8")
    assert "get_operation_options_for_model" in filters  # 기간 필터 템플릿의 바탕


# =============================================================================
# §3 기간 필터 — 모든 created_at 뷰에서 실제로 좁혀진다
# =============================================================================
async def test_range_filter_narrows_every_created_at_list(env):
    from tests.test_admin_login import _admin_views

    client, *_ = env
    await _logged_in(env)
    from config import timezone_settings

    today = timezone_settings.now().date().isoformat()
    for view in _admin_views():
        for value in (f"{today}~{today}", "2000-01-01~2000-01-02", "bad~value"):
            params = {"created_at": value, "created_at_op": "range"}
            response = await client.get(f"/admin/{view.identity}/list", params=params)
            assert response.status_code == 200, (view.identity, value)

    async def listed(value: str) -> bool:
        params = {"created_at": value, "created_at_op": "range"}
        return "root" in (await client.get("/admin/user/list", params=params)).text

    assert await listed(f"{today}~{today}") is True
    assert await listed(f"{today}~") is True
    assert await listed("2000-01-01~2000-01-02") is False
    assert await listed(f"~{today}") is True


async def test_range_filter_template_renders_two_dates_and_quick_links(env):
    client, *_ = env
    await _logged_in(env)

    html = (await client.get("/admin/user/list")).text

    assert 'data-local-date-range="created_at"' in html
    assert "data-range-start" in html and "data-range-end" in html
    assert 'name="created_at_op" value="range"' in html
    assert "created_at_op=range" in html and "최근 7일" in html


# =============================================================================
# 관리 화면 직접 수정·삭제의 즉시 폐기 — 커밋 전, 세션 + refresh
# (admin-session-hardening ADR-008 — ADR-007 대체, R-705 해소)
# =============================================================================
async def _target_with_two_browsers(env):
    """운영자 root 로그인 + 대상 target 이 두 브라우저로 로그인하고 API refresh family 하나를 가진 상태."""
    client, maker, redis, _, new_client = env
    await _logged_in(env)
    target_id = await _add_user(maker, "target")
    browsers = [new_client(), new_client()]
    for browser in browsers:
        assert (await _login(browser, "target")).status_code == 302
    assert len(await redis.smembers(f"admin:user_sessions:{target_id}")) == 2
    await _refresh_store(redis).register("jti-target", target_id, "fam-target")
    return target_id, browsers


def _refresh_store(redis):
    from app.core.security.dependencies import get_refresh_token_store, get_token_service

    return get_refresh_token_store(redis, get_token_service())


async def _refresh_revoked(redis) -> bool:
    return await _refresh_store(redis).is_family_revoked("fam-target")


async def _edit_user(client, user_id: str, **overrides) -> int:
    """관리 화면 수정 폼 제출 — 체크박스는 값이 있으면 켜짐, None 이면 빠져 꺼짐."""
    form = {
        "username": "target",
        "email": "target@example.com",
        "is_active": "y",
        "is_superuser": "y",
        **overrides,
    }
    data = {k: v for k, v in form.items() if v is not None}
    data |= {"save": "Save", "csrf_token": await page_token(client)}
    return (await client.post(f"/admin/user/edit/{user_id}", data=data)).status_code


async def _live_sessions(redis, user_id: str) -> tuple[int, int]:
    """(사용자 인덱스 크기, 실제로 살아 있는 세션 키 수)."""
    keys = await redis.smembers(f"admin:user_sessions:{user_id}")
    alive = [key for key in keys if await redis.exists(key)]
    return len(keys), len(alive)


async def _db_user(maker, user_id: str):
    from app.features.user.models.models import User

    async with maker() as session:
        return await session.get(User, user_id)


@pytest.mark.parametrize(
    ("change", "refresh_revoked"),
    [({"is_active": None}, True), ({"is_superuser": None}, False)],
    ids=["deactivate", "demote"],
)
async def test_admin_ui_edit_revokes_sessions_and_refresh_of_that_user(
    env, change, refresh_revoked
):
    """비활성화는 관리 세션 + refresh, 강등은 관리 세션만(refresh 는 회전 때 DB 권한으로 재발급)."""
    client, maker, redis, *_ = env
    target_id, browsers = await _target_with_two_browsers(env)

    assert await _edit_user(client, target_id, **change) == 302

    assert await _live_sessions(redis, target_id) == (0, 0)
    assert await _refresh_revoked(redis) is refresh_revoked
    for browser in browsers:
        assert (await browser.get("/admin/")).status_code == 302
    assert (await client.get("/admin/")).status_code == 200  # 운영자 세션은 그대로
    user = await _db_user(maker, target_id)
    assert (user.is_active, user.is_superuser) == (
        "is_active" not in change,
        "is_superuser" not in change,
    )


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ((True, True, "h"), (False, True, "h"), (True, True)),  # 비활성화
        ((True, True, "h"), (True, False, "h"), (True, False)),  # 강등 — refresh 유지
        ((True, True, "h"), (True, True, "h2"), (True, True)),  # 비밀번호 해시 변경
        ((True, True, "h"), (True, True, "h"), (False, False)),  # 일반 수정
        ((False, False, "h"), (False, False, "h"), (False, False)),  # 이미 비활성·일반
        ((True, False, "h"), (True, True, "h"), (False, False)),  # 승격은 폐기 아님
    ],
    ids=["deactivate", "demote", "password", "plain", "already-off", "promote"],
)
def test_revocation_for_returns_both_sets_from_one_rule(before, after, expected):
    from app.features.user.admin import DELETED, Revocation, revocation_for

    keys = ("is_active", "is_superuser", "hashed_password")
    result = revocation_for(
        dict(zip(keys, before, strict=False)), dict(zip(keys, after, strict=False))
    )

    assert result == Revocation(*expected)
    assert DELETED == Revocation(admin_sessions=True, refresh=True)


async def test_admin_ui_plain_edit_keeps_sessions_and_refresh(env):
    client, maker, redis, *_ = env
    target_id, browsers = await _target_with_two_browsers(env)

    assert await _edit_user(client, target_id, email="renamed@example.com") == 302

    assert await _live_sessions(redis, target_id) == (2, 2)
    assert await _refresh_revoked(redis) is False
    assert (await _db_user(maker, target_id)).email == "renamed@example.com"
    for browser in browsers:
        assert (await browser.get("/admin/")).status_code == 200


async def test_admin_ui_delete_revokes_sessions_and_refresh_of_that_user(env):
    client, maker, redis, *_ = env
    target_id, browsers = await _target_with_two_browsers(env)
    token = await page_token(client)

    response = await client.request(
        "DELETE", f"/admin/user/delete?pks={target_id}", headers={"X-CSRF-Token": token}
    )

    assert response.status_code == 200
    assert "error=" not in response.text
    assert await _db_user(maker, target_id) is None
    assert await _live_sessions(redis, target_id) == (0, 0)
    assert await _refresh_revoked(redis) is True
    for browser in browsers:
        assert (await browser.get("/admin/")).status_code == 302


async def test_password_hash_change_through_the_admin_hook_revokes_access(env):
    """폼은 비밀번호를 노출하지 않는다 — 커밋 전 훅이 hashed_password 변경도 폐기 사유로 보는지 직접 본다."""
    from starlette.requests import Request

    from app.core.security import admin_session
    from app.core.security.dependencies import get_password_hasher
    from app.features.user.admin import UserAdmin

    _, maker, redis, *_ = env
    target_id, browsers = await _target_with_two_browsers(env)
    user = await _db_user(maker, target_id)
    request = Request({"type": "http", admin_session._STORE_KEY: session_store(redis)})
    new_hash = get_password_hasher().hash("another-horse-2")

    await UserAdmin().on_model_change({"email": user.email}, user, False, request)
    assert await _live_sessions(redis, target_id) == (2, 2)  # 해시가 그대로면 유지

    await UserAdmin().on_model_change({"hashed_password": new_hash}, user, False, request)
    assert await _live_sessions(redis, target_id) == (0, 0)
    assert await _refresh_revoked(redis) is True
    for browser in browsers:
        assert (await browser.get("/admin/")).status_code == 302


async def test_self_demotion_ends_the_current_session_too(env):
    client, _, redis, *_ = env
    root_id = await _logged_in(env)

    status = await _edit_user(
        client, root_id, username="root", email="root@example.com", is_superuser=None
    )

    assert status == 302
    assert await redis.keys("admin:sess:*") == []  # 응답 끝의 저장이 세션을 되살리지 않았다
    assert (await client.get("/admin/")).status_code == 302


@pytest.mark.parametrize("failing", ["admin-sessions", "refresh"])
async def test_revoke_failure_blocks_the_edit_commit(env, monkeypatch, failing):
    """Redis 폐기가 실패하면 커밋하지 않는다 — "DB 는 비활성화됨 + 세션은 살아 있음" 이 남지 않는다."""
    from app.core.security.refresh_store import RefreshTokenStore

    client, maker, redis, *_ = env
    target_id, browsers = await _target_with_two_browsers(env)

    async def broken(self, user_id):
        raise RedisConnectionError("down")

    owner = AdminSessionStore if failing == "admin-sessions" else RefreshTokenStore
    monkeypatch.setattr(owner, "revoke_user", broken)

    status = await _edit_user(client, target_id, is_active=None)

    assert status == 400  # sqladmin 이 훅 예외를 수정 폼 오류로 다시 그린다
    assert (await _db_user(maker, target_id)).is_active is True  # 커밋되지 않았다
    for browser in browsers:
        assert (await browser.get("/admin/")).status_code == 200  # 세션도 그대로 — 일관된 상태


async def test_revoke_failure_blocks_the_delete_commit(env, monkeypatch):
    client, maker, *_ = env
    target_id, _ = await _target_with_two_browsers(env)

    async def broken(self, user_id):
        raise RedisConnectionError("down")

    monkeypatch.setattr(AdminSessionStore, "revoke_user", broken)
    token = await page_token(client)

    response = await client.request(
        "DELETE", f"/admin/user/delete?pks={target_id}", headers={"X-CSRF-Token": token}
    )

    assert response.status_code == 200 and "error=" in response.text  # 목록에 오류로 표시
    assert await _db_user(maker, target_id) is not None  # 삭제가 커밋되지 않았다


async def test_save_does_not_resurrect_a_revoked_session():
    """폐기된 세션을 같은 요청 끝의 저장(세션 내용이 바뀐 경우)이 되살리지 않는다(SET XX)."""
    redis = FakeAsyncRedis()
    store = session_store(redis)
    await store.save("sid", {"user_id": "u1"}, store.now(), create=True)
    await store.revoke_user("u1")

    await store.save("sid", {"user_id": "u1", "csrf_token": "t"}, store.now())

    assert await redis.keys("admin:*") == []
    await store.save("sid", {"user_id": "u1"}, store.now(), create=True)  # 새 세션은 만든다
    assert await redis.exists(store.key("sid"))
