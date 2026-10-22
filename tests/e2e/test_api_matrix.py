"""L2 API 전수 매트릭스 — operation 마다 정상·검증 오류·미인증·권한 부족·없음·잘못된 메서드·접근 정책 대조.

operation 정의(`OPS`)는 이 파일이 소유하고, 실제 앱에서 뽑은 인벤토리(OpenAPI·선언 접근 수준)와
test_inventory.py 가 대조한다 — 새 operation 이 생기면 여기에 줄을 더하지 않는 한 그 테스트가 실패한다.
해당하지 않는 칸은 test_inventory.py 의 `NOT_APPLICABLE` 에 사유와 함께 적는다.
"""

from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from tests.e2e.conftest import Api, User, wait_until

V1 = "/api/v1"
PUBLIC, PUBLIC_WRITE, LOGIN, SUPER = "Public", "PublicWrite", "LoginRequired", "SuperuserRequired"


# ---------------------------------------------------------------------------
# 세계: 사용자 셋과 기능별 리소스 하나씩
# ---------------------------------------------------------------------------


@dataclass
class World:
    api: Api
    owner: User
    other: User
    admin: User
    post: str
    sns: str
    reply: str
    product: str

    def as_(self, who: str | None) -> dict[str, str]:
        return {} if who is None else getattr(self, who).auth


@pytest.fixture(scope="module")
def world(api: Api) -> World:
    owner, other, admin = api.user(), api.user(), api.admin()

    def made(url: str, user: User, body: dict[str, Any]) -> str:
        r = api.request("POST", url, json=body, headers=user.auth)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    post = made(f"{V1}/blog/posts", owner, {"title": "t", "content": "c"})
    return World(
        api=api,
        owner=owner,
        other=other,
        admin=admin,
        post=post,
        sns=made(f"{V1}/sns/posts", owner, {"content": "s"}),
        reply=made(f"{V1}/reply/replies", owner, {"content": "r", "post_id": post}),
        product=made(f"{V1}/catalog/products", admin, {"name": "p", "price": "12.50"}),
    )


def fresh(w: World, kind: str) -> str:
    """삭제 칸용 새 리소스."""
    url, who, body = {
        "post": (f"{V1}/blog/posts", "owner", {"title": "d", "content": "d"}),
        "sns": (f"{V1}/sns/posts", "owner", {"content": "d"}),
        "reply": (f"{V1}/reply/replies", "owner", {"content": "d", "post_id": w.post}),
        "product": (f"{V1}/catalog/products", "admin", {"name": "d", "price": "1.00"}),
        "user": (
            f"{V1}/user/users",
            "admin",
            {
                "username": "d_" + secrets.token_hex(4),
                "email": "d@example.com",
                "password": "Pw-" + secrets.token_hex(6),
            },
        ),
    }[kind]
    if kind == "user":
        body["email"] = f"{body['username']}@example.com"
    r = w.api.request("POST", url, json=body, headers=w.as_(who))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# operation 정의
# ---------------------------------------------------------------------------


@dataclass
class Op:
    """한 operation. ``ok`` 는 정상 요청을 만든다(누가·무엇을), ``bad`` 는 422 요청, ``table`` 은 DB 반영 확인."""

    level: str
    ok: Callable[[World], dict[str, Any]]
    status: int
    bad: Callable[[World], dict[str, Any]] | None = None
    owned: Callable[[World], dict[str, Any]] | None = None  # 남의 것 → 403
    missing: Callable[[World], dict[str, Any]] | None = None  # 없는 id → 404
    table: str | None = None  # 쓰기: 이 테이블에서 반영 확인


def _login_form(w: World) -> dict[str, Any]:
    return {"data": {"username": w.owner.username, "password": w.owner.password}}


def _refresh(w: World) -> str:
    r = w.api.login(w.owner.username, w.owner.password)
    assert r.status_code == 200, r.text
    return r.json()["refresh_token"]


def _new_user_body() -> dict[str, Any]:
    name = "n_" + secrets.token_hex(5)
    return {
        "username": name,
        "email": f"{name}@example.com",
        "password": "Pw-" + secrets.token_hex(6),
    }


NOPE = str(uuid.uuid4())
LIST_BAD = {"params": {"limit": 0}}
NOT_OBJECT = {"json": [1]}

OPS: dict[str, Op] = {
    "POST /api/v1/auth/register": Op(
        PUBLIC_WRITE,
        lambda w: {"json": _new_user_body()},
        201,
        bad=lambda w: {"json": {**_new_user_body(), "password": "short"}},
        table="users",
    ),
    "POST /api/v1/auth/login": Op(
        PUBLIC_WRITE,
        _login_form,
        200,
        bad=lambda w: {"data": {"username": w.owner.username}},
    ),
    "POST /api/v1/auth/refresh": Op(
        PUBLIC_WRITE,
        lambda w: {"json": {"refresh_token": _refresh(w)}},
        200,
        bad=lambda w: {"json": {}},
    ),
    "POST /api/v1/auth/logout": Op(
        PUBLIC_WRITE,
        lambda w: {"json": {"refresh_token": _refresh(w)}},
        204,
        bad=lambda w: {"json": {}},
    ),
    "GET /api/v1/auth/me": Op(LOGIN, lambda w: {"who": "owner"}, 200),
    "POST /api/v1/blog/posts": Op(
        LOGIN,
        lambda w: {"who": "owner", "json": {"title": "a", "content": "b"}},
        201,
        bad=lambda w: {"who": "owner", "json": {"title": "", "content": "b"}},
        table="blog_posts",
    ),
    "GET /api/v1/blog/posts": Op(PUBLIC, lambda w: {}, 200, bad=lambda w: LIST_BAD),
    "GET /api/v1/blog/posts/{post_id}": Op(
        PUBLIC,
        lambda w: {"path": w.post},
        200,
        missing=lambda w: {"path": NOPE},
    ),
    "PATCH /api/v1/blog/posts/{post_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": w.post, "json": {"title": "patched"}},
        200,
        bad=lambda w: {"who": "owner", "path": w.post, **NOT_OBJECT},
        owned=lambda w: {"who": "other", "path": w.post, "json": {"title": "x"}},
        missing=lambda w: {"who": "owner", "path": NOPE, "json": {"title": "x"}},
        table="blog_posts",
    ),
    "DELETE /api/v1/blog/posts/{post_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": fresh(w, "post")},
        204,
        owned=lambda w: {"who": "other", "path": w.post},
        missing=lambda w: {"who": "owner", "path": NOPE},
        table="blog_posts",
    ),
    "POST /api/v1/catalog/products": Op(
        SUPER,
        lambda w: {"who": "admin", "json": {"name": "n", "price": "3.30"}},
        201,
        bad=lambda w: {"who": "admin", "json": {"name": "n", "price": "abc"}},
        owned=lambda w: {"who": "owner", "json": {"name": "n", "price": "1"}},
        table="catalog_products",
    ),
    "GET /api/v1/catalog/products": Op(PUBLIC, lambda w: {}, 200, bad=lambda w: LIST_BAD),
    "GET /api/v1/catalog/products/{product_id}": Op(
        PUBLIC,
        lambda w: {"path": w.product},
        200,
        missing=lambda w: {"path": NOPE},
    ),
    "PATCH /api/v1/catalog/products/{product_id}": Op(
        SUPER,
        lambda w: {"who": "admin", "path": w.product, "json": {"name": "patched"}},
        200,
        bad=lambda w: {"who": "admin", "path": w.product, **NOT_OBJECT},
        owned=lambda w: {"who": "owner", "path": w.product, "json": {"name": "x"}},
        missing=lambda w: {"who": "admin", "path": NOPE, "json": {"name": "x"}},
        table="catalog_products",
    ),
    "DELETE /api/v1/catalog/products/{product_id}": Op(
        SUPER,
        lambda w: {"who": "admin", "path": fresh(w, "product")},
        204,
        owned=lambda w: {"who": "owner", "path": w.product},
        missing=lambda w: {"who": "admin", "path": NOPE},
        table="catalog_products",
    ),
    "GET /api/v1/home/access-logs": Op(
        SUPER,
        lambda w: {"who": "admin"},
        200,
        bad=lambda w: {"who": "admin", **LIST_BAD},
        owned=lambda w: {"who": "owner"},
    ),
    "GET /api/v1/home/access-logs/recent": Op(
        SUPER,
        lambda w: {"who": "admin"},
        200,
        bad=lambda w: {"who": "admin", "params": {"limit": 101}},
        owned=lambda w: {"who": "owner"},
    ),
    "GET /api/v1/home/access-logs/by-ip/{ip_address}": Op(
        SUPER,
        lambda w: {"who": "admin", "path": "10.77.0.1"},
        200,
        bad=lambda w: {"who": "admin", "path": "10.77.0.1", **LIST_BAD},
        owned=lambda w: {"who": "owner", "path": "10.77.0.1"},
    ),
    "GET /api/v1/home/access-logs/by-user/{user_id}": Op(
        SUPER,
        lambda w: {"who": "admin", "path": w.owner.id},
        200,
        bad=lambda w: {"who": "admin", "path": w.owner.id, **LIST_BAD},
        owned=lambda w: {"who": "owner", "path": w.owner.id},
    ),
    "GET /api/v1/home/access-logs/stats": Op(
        SUPER,
        lambda w: {"who": "admin"},
        200,
        owned=lambda w: {"who": "owner"},
    ),
    "POST /api/v1/reply/replies": Op(
        LOGIN,
        lambda w: {"who": "owner", "json": {"content": "c", "post_id": w.post}},
        201,
        bad=lambda w: {"who": "owner", "json": {"content": ""}},
        table="replies",
    ),
    "GET /api/v1/reply/replies": Op(PUBLIC, lambda w: {}, 200, bad=lambda w: LIST_BAD),
    "GET /api/v1/reply/replies/{reply_id}": Op(
        PUBLIC,
        lambda w: {"path": w.reply},
        200,
        missing=lambda w: {"path": NOPE},
    ),
    "PATCH /api/v1/reply/replies/{reply_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": w.reply, "json": {"content": "patched"}},
        200,
        bad=lambda w: {"who": "owner", "path": w.reply, **NOT_OBJECT},
        owned=lambda w: {"who": "other", "path": w.reply, "json": {"content": "x"}},
        missing=lambda w: {"who": "owner", "path": NOPE, "json": {"content": "x"}},
        table="replies",
    ),
    "DELETE /api/v1/reply/replies/{reply_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": fresh(w, "reply")},
        204,
        owned=lambda w: {"who": "other", "path": w.reply},
        missing=lambda w: {"who": "owner", "path": NOPE},
        table="replies",
    ),
    "GET /api/v1/reports/sales/daily": Op(
        SUPER,
        lambda w: {
            "who": "admin",
            "params": {"start_date": "2026-10-01", "end_date": "2026-10-02"},
        },
        200,
        bad=lambda w: {"who": "admin", "params": {"start_date": "2026-10-01"}},
        owned=lambda w: {
            "who": "owner",
            "params": {"start_date": "2026-10-01", "end_date": "2026-10-02"},
        },
    ),
    "POST /api/v1/sns/posts": Op(
        LOGIN,
        lambda w: {"who": "owner", "json": {"content": "s"}},
        201,
        bad=lambda w: {"who": "owner", "json": {"content": "x" * 501}},
        table="sns_posts",
    ),
    "GET /api/v1/sns/posts": Op(PUBLIC, lambda w: {}, 200, bad=lambda w: LIST_BAD),
    "GET /api/v1/sns/posts/{post_id}": Op(
        PUBLIC,
        lambda w: {"path": w.sns},
        200,
        missing=lambda w: {"path": NOPE},
    ),
    "PATCH /api/v1/sns/posts/{post_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": w.sns, "json": {"content": "patched"}},
        200,
        bad=lambda w: {"who": "owner", "path": w.sns, **NOT_OBJECT},
        owned=lambda w: {"who": "other", "path": w.sns, "json": {"content": "x"}},
        missing=lambda w: {"who": "owner", "path": NOPE, "json": {"content": "x"}},
        table="sns_posts",
    ),
    "DELETE /api/v1/sns/posts/{post_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": fresh(w, "sns")},
        204,
        owned=lambda w: {"who": "other", "path": w.sns},
        missing=lambda w: {"who": "owner", "path": NOPE},
        table="sns_posts",
    ),
    "POST /api/v1/user/users": Op(
        SUPER,
        lambda w: {"who": "admin", "json": _new_user_body()},
        201,
        bad=lambda w: {"who": "admin", "json": {**_new_user_body(), "password": "short"}},
        owned=lambda w: {"who": "owner", "json": _new_user_body()},
        table="users",
    ),
    "GET /api/v1/user/users": Op(
        SUPER,
        lambda w: {"who": "admin"},
        200,
        bad=lambda w: {"who": "admin", **LIST_BAD},
        owned=lambda w: {"who": "owner"},
    ),
    "GET /api/v1/user/users/{user_id}": Op(
        LOGIN,
        lambda w: {"who": "owner", "path": w.owner.id},
        200,
        owned=lambda w: {"who": "other", "path": w.owner.id},
        missing=lambda w: {"who": "admin", "path": NOPE},
    ),
    "PATCH /api/v1/user/users/{user_id}": Op(
        LOGIN,
        lambda w: {
            "who": "owner",
            "path": w.owner.id,
            "json": {"email": f"{w.owner.username}+p@example.com"},
        },
        200,
        bad=lambda w: {"who": "owner", "path": w.owner.id, "json": {"email": "not-an-email"}},
        owned=lambda w: {"who": "other", "path": w.owner.id, "json": {"email": "x@example.com"}},
        missing=lambda w: {"who": "admin", "path": NOPE, "json": {"email": "x@example.com"}},
        table="users",
    ),
    "DELETE /api/v1/user/users/{user_id}": Op(
        SUPER,
        lambda w: {"who": "admin", "path": fresh(w, "user")},
        204,
        owned=lambda w: {"who": "owner", "path": w.other.id},
        missing=lambda w: {"who": "admin", "path": NOPE},
        table="users",
    ),
    "GET /health": Op(PUBLIC, lambda w: {}, 200),
    "GET /ready": Op(PUBLIC, lambda w: {}, 200),
}


def call(w: World, op_key: str, spec: dict[str, Any], *, who: Any = "spec") -> Any:
    method, template = op_key.split(" ", 1)
    spec = dict(spec)
    actor = spec.pop("who", None) if who == "spec" else who
    spec.pop("who", None)
    url = template
    if "path" in spec:
        url = template[: template.index("{")] + str(spec.pop("path"))
    headers = {**w.as_(actor), **spec.pop("headers", {})}
    return w.api.request(method, url, headers=headers, **spec)


# ---------------------------------------------------------------------------
# 응답 스키마 — OpenAPI 와 대조(필수 키·타입, $ref·anyOf·배열 재귀)
# ---------------------------------------------------------------------------

_TYPES = {
    "string": str,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "number": (int, float),
    "null": type(None),
}


def check_schema(
    openapi: dict[str, Any], schema: dict[str, Any], value: Any, where: str = "$"
) -> None:
    if "$ref" in schema:
        schema = openapi["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                return check_schema(openapi, option, value, where)
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(f"{where}: anyOf 어느 것과도 맞지 않음 {errors}")
    kind = schema.get("type")
    if kind:
        assert isinstance(value, _TYPES[kind]) and not (
            kind == "integer" and isinstance(value, bool)
        ), f"{where}: {kind} 기대, {type(value).__name__} 받음"
    if kind == "object" or "properties" in schema:
        for key in schema.get("required", []):
            assert key in value, f"{where}: 필수 키 {key} 없음"
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                check_schema(openapi, sub, value[key], f"{where}.{key}")
    if kind == "array":
        for i, item in enumerate(value):
            check_schema(openapi, schema.get("items", {}), item, f"{where}[{i}]")


def response_schema(openapi: dict[str, Any], op_key: str, status: int) -> dict[str, Any] | None:
    method, path = op_key.split(" ", 1)
    content = openapi["paths"][path][method.lower()]["responses"][str(status)].get("content")
    return content["application/json"]["schema"] if content else None


def row(stack: Any, table: str, row_id: str) -> dict[str, Any] | None:
    import pymysql.cursors

    with stack.mysql(cursorclass=pymysql.cursors.DictCursor) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT * FROM `{table}` WHERE id = %s", (row_id,))  # noqa: S608 - 테이블은 OPS 상수
        return cur.fetchone()


# ---------------------------------------------------------------------------
# 칸별 테스트
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op_key", list(OPS))
def test_normal(op_key, world, inventory, stack, cover):
    """정상: 2xx, 응답 스키마 = OpenAPI, 쓰기는 primary DB 반영."""
    op = OPS[op_key]
    spec = op.ok(world)
    method = op_key.split(" ", 1)[0]

    def attempt() -> Any:
        r = call(world, op_key, spec)
        if r.status_code == op.status:
            return r
        if r.status_code == 404 and method == "GET":
            return None  # 읽기는 replica — 방금 만든 리소스가 복제될 때까지 기다린다
        pytest.fail(f"{op_key}: {r.status_code} {r.text[:300]}")

    response = wait_until(attempt, 15, f"{op_key} {op.status}")
    schema = response_schema(inventory["openapi"], op_key, op.status)
    if schema is not None:
        check_schema(inventory["openapi"], schema, response.json())
    if op.table:
        target = spec.get("path") or (response.json() or {}).get("id")
        stored = row(stack, op.table, target)
        if method == "DELETE":
            assert stored is None, f"{op.table}.{target} 가 남았습니다"
        else:
            assert stored is not None, f"{op.table}.{target} 가 없습니다"
            for key, value in (spec.get("json") or {}).items():
                if key in stored and key != "password":
                    assert str(stored[key]) == str(value) or key == "price", (
                        key,
                        stored[key],
                        value,
                    )
    cover(op_key, "정상")


@pytest.mark.parametrize("op_key", [k for k, op in OPS.items() if op.bad])
def test_validation_error(op_key, world, inventory, stack, cover):
    """검증 오류: 422 + 앱 공통 오류 형식(ErrorResponse, VALIDATION_ERROR, detail[field·message·type]).

    OpenAPI 가 그 operation 에 광고한 422 스키마로 실제 본문을 검증한다(P-001 → integration-e2e ADR-009:
    문서 = 실제 형식). 광고 스키마 이름은 산출물 ``openapi-422.json`` 에 기록한다.
    """
    openapi = inventory["openapi"]
    response = call(world, op_key, OPS[op_key].bad(world))
    assert response.status_code == 422, response.text
    body = response.json()
    documented = response_schema(openapi, op_key, 422) or {}
    assert documented == {"$ref": "#/components/schemas/ErrorResponse"}, documented
    check_schema(openapi, documented, body)
    assert body["error_code"] == "VALIDATION_ERROR", body
    assert body["detail"] and all(
        set(d) == {"field", "message", "type"} for d in body["detail"]
    ), body
    DOCUMENTED_422[op_key] = documented.get("$ref", "").rsplit("/", 1)[-1]
    (stack.artifacts / "openapi-422.json").write_text(
        json.dumps(DOCUMENTED_422, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    cover(op_key, "검증 오류")


DOCUMENTED_422: dict[str, str] = {}


@pytest.mark.parametrize("op_key", [k for k, op in OPS.items() if op.level in (LOGIN, SUPER)])
def test_unauthenticated(op_key, world, cover):
    """미인증: 토큰 없음·위조 토큰 → 401 + WWW-Authenticate: Bearer."""
    spec = OPS[op_key].ok(world)
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        response = call(world, op_key, {**spec, "headers": headers}, who=None)
        assert response.status_code == 401, response.text
        assert response.headers.get("www-authenticate", "").startswith("Bearer"), response.headers
        assert response.json()["error_code"], response.text
    cover(op_key, "미인증")


@pytest.mark.parametrize("op_key", [k for k, op in OPS.items() if op.owned])
def test_forbidden(op_key, world, cover):
    """권한 부족: 슈퍼유저 전용을 일반 사용자가, 남의 리소스를 다른 사용자가 → 403."""
    response = call(world, op_key, OPS[op_key].owned(world))
    assert response.status_code == 403, response.text
    assert response.json()["error_code"], response.text
    cover(op_key, "권한 부족")


@pytest.mark.parametrize("op_key", [k for k, op in OPS.items() if op.missing])
def test_not_found(op_key, world, cover):
    response = call(world, op_key, OPS[op_key].missing(world))
    assert response.status_code == 404, response.text
    assert response.json()["error_code"], response.text
    cover(op_key, "없음")


PATHS = sorted({k.split(" ", 1)[1] for k in OPS})
ALLOW_SEEN: dict[str, str] = {}


@pytest.mark.parametrize("path", PATHS)
def test_method_not_allowed(path, world, inventory, stack, cover):
    """잘못된 메서드(PUT): 405 + Allow. 메서드 분할 경로는 현행 유지 — Allow 값을 산출물에 기록한다."""
    allowed = {m.upper() for m in inventory["openapi"]["paths"][path]}
    assert "PUT" not in allowed
    url = path.replace("{", "").replace("}", "")  # 아무 값이나 — 메서드 판정이 먼저다
    response = world.api.request("PUT", url, headers=world.admin.auth)
    assert response.status_code == 405, response.text
    allow = {m.strip() for m in response.headers.get("allow", "").split(",") if m.strip()}
    assert allow and allow <= allowed | {"HEAD"}, (allow, allowed)
    ALLOW_SEEN[path] = ", ".join(sorted(allow))
    (stack.artifacts / "allow-405.json").write_text(
        json.dumps(ALLOW_SEEN, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for key in OPS:
        if key.split(" ", 1)[1] == path:
            cover(key, "잘못된 메서드")


@pytest.mark.parametrize("op_key", list(OPS))
def test_access_policy_matches_declaration(op_key, world, inventory, cover):
    """선언(인벤토리)과 실제 응답: 익명·일반·슈퍼유저 각각."""
    method, path = op_key.split(" ", 1)
    op = OPS[op_key]
    assert inventory["access"][op_key] == [op.level], (inventory["access"][op_key], op.level)

    def status(who: str | None) -> int:
        # 주체마다 요청을 새로 만든다 — refresh 토큰은 한 번 쓰면 재사용 거부(401)다.
        spec = {k: v for k, v in op.ok(world).items() if k != "who"}
        if "path" in spec and method != "GET" and op.missing:
            spec["path"] = NOPE  # 쓰기는 없는 id 로 — 판정만 보고 데이터를 건드리지 않는다
        return call(world, op_key, spec, who=who).status_code

    anonymous, member, superuser = status(None), status("other"), status("admin")
    if op.level in (PUBLIC, PUBLIC_WRITE):
        assert anonymous not in (401, 403), anonymous
    else:
        assert anonymous == 401, anonymous
    if op.level == SUPER:
        assert member == 403, member
    else:
        assert member != 401, member
    assert superuser not in (401, 403), superuser
    cover(op_key, "접근 정책 대조")
