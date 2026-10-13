"""뷰 단위 접근 수준 선언과 기동 시 기본 거부 (access-policy ADR-001~003).

가드 단위 시험은 실제 앱이 아니라 매번 새로 만든 작은 FastAPI 앱으로 한다 — 어떤 선언이
어떤 판정을 낳는지만 본다. 실제 앱의 조립 경로에서 가드가 불리는지는 깨끗한 서브프로세스로
확인한다(같은 프로세스에서 main 을 다시 조립하면 다른 테스트가 쥔 ``app`` 과 갈라진다).
"""

import os
import subprocess
import sys
import textwrap

import pytest
from fastapi import APIRouter, FastAPI
from starlette.routing import Mount

from app.core.registry import AppContractError
from app.core.security.access import (
    AccessLevel,
    AccessPolicyGuard,
    LoginRequired,
    Public,
    PublicWrite,
    SuperuserRequired,
)
from app.core.security.dependencies import CurrentPrincipal, SuperuserPrincipal
from main import app as real_app

guard = AccessPolicyGuard()


def _levels(app: FastAPI) -> dict[tuple[str, str], set[AccessLevel]]:
    return {key: set(levels) for key, levels in guard.operations(app).items()}


def _one(method: str = "get", **route_kwargs) -> FastAPI:
    app = FastAPI()
    getattr(app, method)("/x", **route_kwargs)(lambda: None)
    return app


# ------------------------------------------------------------------ 위반 4종


def test_route_without_declaration_is_a_violation():
    problems = guard.violations(_one())
    assert len(problems) == 1
    assert "GET /x" in problems[0] and "선언이 없습니다" in problems[0]


@pytest.mark.parametrize(
    "deps",
    [[Public, LoginRequired], [Public, PublicWrite], [PublicWrite, SuperuserRequired]],
    ids=["public+login", "public+public_write", "public_write+superuser"],
)
def test_two_levels_are_a_violation(deps):
    problems = guard.violations(_one("post", dependencies=deps))
    assert len(problems) == 1 and "둘 이상" in problems[0]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_public_on_write_method_points_to_public_write(method):
    problems = guard.violations(_one(method, dependencies=[Public]))
    assert len(problems) == 1 and "PublicWrite" in problems[0]


def test_public_write_on_safe_method_is_a_violation():
    problems = guard.violations(_one("get", dependencies=[PublicWrite]))
    assert len(problems) == 1 and "안전한 메서드" in problems[0]


@pytest.mark.parametrize(
    ("method", "dep", "level"),
    [
        ("get", Public, AccessLevel.PUBLIC),
        ("post", PublicWrite, AccessLevel.PUBLIC_WRITE),
        ("post", LoginRequired, AccessLevel.LOGIN),
        ("delete", SuperuserRequired, AccessLevel.SUPERUSER),
    ],
)
def test_each_level_is_valid_alone(method, dep, level):
    app = _one(method, dependencies=[dep])
    assert guard.violations(app) == []
    assert _levels(app) == {(method.upper(), "/x"): {level}}


# ------------------------------------------------------------------ 인정되는 선언 형태


def test_principal_argument_counts_as_declaration():
    app = FastAPI()

    @app.post("/login")
    def needs_login(principal: CurrentPrincipal) -> None: ...

    @app.post("/admin")
    def needs_superuser(principal: SuperuserPrincipal) -> None: ...

    assert guard.violations(app) == []
    assert _levels(app) == {
        ("POST", "/login"): {AccessLevel.LOGIN},
        ("POST", "/admin"): {AccessLevel.SUPERUSER},
    }


def test_superuser_wins_over_the_login_it_contains():
    """require_superuser 가 내부에서 get_current_principal 을 쓴다 — 이중 선언이 아니다."""
    app = FastAPI()

    @app.post("/x", dependencies=[SuperuserRequired])
    def both(principal: CurrentPrincipal) -> None: ...

    assert _levels(app) == {("POST", "/x"): {AccessLevel.SUPERUSER}}


def test_router_level_dependencies_count_through_nested_includes():
    """라우터 단위 선언도 트리에 들어간다. FastAPI 0.141 의 중첩 include 를 실제로 펼친다."""
    inner = APIRouter(dependencies=[SuperuserRequired])
    inner.get("/deep")(lambda: None)
    middle = APIRouter()
    middle.include_router(inner, prefix="/v1")
    outer = APIRouter()
    outer.include_router(middle, prefix="/feature")
    app = FastAPI()
    app.include_router(outer, prefix="/api")

    assert _levels(app) == {("GET", "/api/feature/v1/deep"): {AccessLevel.SUPERUSER}}


def test_nested_undeclared_route_is_found():
    inner = APIRouter()
    inner.get("/deep")(lambda: None)
    outer = APIRouter()
    outer.include_router(inner, prefix="/v1")
    app = FastAPI()
    app.include_router(outer, prefix="/api")

    assert ["GET /api/v1/deep"] == [p.split(":")[0] for p in guard.violations(app)]


def test_hidden_routes_are_checked():
    app = _one(include_in_schema=False)
    assert len(guard.violations(app)) == 1


def test_docs_routes_and_mounts_are_excluded():
    app = FastAPI()  # /docs·/redoc·/openapi.json 은 Starlette Route 다
    app.mount("/admin", Mount("/", routes=[]))
    assert guard.operations(app) == {}
    assert guard.violations(app) == []


# ------------------------------------------------------------------ verify


def test_verify_reports_every_violation_at_once():
    app = FastAPI()
    app.get("/a")(lambda: None)
    app.post("/b", dependencies=[Public])(lambda: None)
    app.get("/c", dependencies=[PublicWrite])(lambda: None)
    app.get("/ok", dependencies=[Public])(lambda: None)

    with pytest.raises(AppContractError) as exc:
        guard.verify(app)

    message = str(exc.value)
    assert "3건" in message
    for where in ("GET /a", "POST /b", "GET /c"):
        assert where in message
    assert "/ok" not in message


def test_verify_passes_a_clean_app():
    guard.verify(_one(dependencies=[Public]))


# ------------------------------------------------------------------ 실제 앱


def test_real_app_passes_the_guard():
    assert guard.violations(real_app) == []


CHILD = textwrap.dedent(
    """
    import app.core.registry as registry

    original = registry.AppRegistry.install_routers

    def install_with_undeclared(self, app):
        count = original(self, app)

        @app.post("/api/undeclared")
        async def undeclared() -> None: ...

        return count

    registry.AppRegistry.install_routers = install_with_undeclared
    try:
        import main  # noqa: F401
    except registry.AppContractError as exc:
        print("BLOCKED", "POST /api/undeclared" in str(exc))
    else:
        print("STARTED")
    """
)


def test_main_refuses_to_assemble_with_an_undeclared_route():
    """가드가 main 의 조립 경로에서 실제로 불린다 — 라우터 결선 뒤에 붙은 라우트까지 본다.

    DB·Redis 에 닿지 않는다: main 을 import 만 하고 lifespan 은 돌리지 않는다.
    """
    result = subprocess.run(
        [sys.executable, "-c", CHILD],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    assert "BLOCKED True" in result.stdout, f"{result.stdout}\n{result.stderr}"
