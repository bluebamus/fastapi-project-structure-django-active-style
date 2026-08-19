"""발견 목록을 실제로 결선하는 단계 — 라우터·모델·Admin (FR-02, FR-03, FR-04)."""

import pytest
from fastapi import APIRouter, FastAPI

from app.core.registry import AppContractError, AppModule, AppRegistry

FAKE_PACKAGE = "tests.core._fakeapps"


class _StubAdmin:
    """SQLAdmin `Admin` 의 add_view 만 흉내낸다 — 실제 Admin 은 엔진이 필요하다."""

    def __init__(self) -> None:
        self.collected: list[type] = []

    def add_view(self, view: type) -> None:
        self.collected.append(view)


def _discovered() -> AppRegistry:
    reg = AppRegistry()
    reg.discover(package=FAKE_PACKAGE)
    return reg


def test_install_routers_mounts_only_apps_with_routers():
    """alpha 만 라우터를 가지므로 1개가 `/api` 아래 마운트된다."""
    app = FastAPI()
    count = _discovered().install_routers(app)

    assert count == 1
    # app.routes 직접 순회는 FastAPI 0.141 의 _IncludedRouter 때문에 평탄화되지
    # 않는다 — 공개 계약인 OpenAPI 스키마로 확인한다.
    assert "/api/ping" in app.openapi()["paths"]


def test_install_routers_rejects_shared_router_object():
    """서로 다른 앱이 같은 APIRouter 객체를 내보내면 라우트가 중복 등록된다."""
    shared = APIRouter()
    SharedRouterModule = type(
        "SharedRouterModule",
        (AppModule,),
        {"load_router": lambda self: shared},
    )

    reg = AppRegistry()
    reg._apps = [
        SharedRouterModule(name="one", package="pkg.one"),
        SharedRouterModule(name="two", package="pkg.two"),
    ]

    with pytest.raises(AppContractError, match="같은 APIRouter"):
        reg.install_routers(FastAPI())


def test_import_models_skips_apps_without_models():
    """모델 없는 앱이 섞여 있어도 예외 없이 전체를 돈다."""
    assert _discovered().import_models() is None


def test_install_admin_collects_views_from_apps():
    """beta 의 `admin_views` 두 개가 SQLAdmin 에 등록된다."""
    stub = _StubAdmin()
    count = _discovered().install_admin(stub)

    assert count == 2
    assert [v.__name__ for v in stub.collected] == ["WidgetAdmin", "GadgetAdmin"]


def test_install_admin_rejects_duplicate_view():
    """같은 ModelView 를 두 앱이 내보내면 관리 화면에 중복 항목이 생긴다."""
    from tests.core._fakeapps.beta.admin import WidgetAdmin

    DupModule = type(
        "DupModule",
        (AppModule,),
        {"load_admin_views": lambda self: [WidgetAdmin]},
    )
    reg = AppRegistry()
    reg._apps = [
        DupModule(name="one", package="pkg.one"),
        DupModule(name="two", package="pkg.two"),
    ]

    with pytest.raises(AppContractError, match="중복 등록"):
        reg.install_admin(_StubAdmin())


def test_wiring_uses_the_discovered_list_only():
    """결선은 스스로 다시 스캔하지 않고 마지막 discover() 결과만 쓴다 (NFR-05).

    두 번째 스캔 로직이 생기면 런타임과 Alembic 의 앱 목록이 어긋날 수 있다.
    발견 목록을 비우면 결선 결과도 비어야 한다.
    """
    reg = _discovered()
    reg._apps = []

    app = FastAPI()
    assert reg.install_routers(app) == 0
    assert reg.install_admin(_StubAdmin()) == 0


def test_import_models_registers_models_without_package_reexport(tmp_path, monkeypatch):
    """`models/__init__.py` 재export 없이도 모델이 등록된다.

    예전에는 등록이 각 앱 `models/__init__.py` 의 재export 한 줄에 걸려 있었다.
    scaffold 로 만든 앱은 그 줄이 없어 테이블이 조용히 빠졌고, 증상은 한참 뒤에
    "마이그레이션이 비어 있음" 으로만 나타났다.
    """
    import sys

    from sqlalchemy.orm import DeclarativeBase

    from app.core.registry import AppModule

    monkeypatch.syspath_prepend(str(tmp_path))
    package = tmp_path / "probe_feature"
    (package / "models").mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    # 재export 를 **일부러 비워 둔다** — scaffold 가 만드는 상태와 같다.
    (package / "models" / "__init__.py").write_text("", encoding="utf-8")
    (package / "models" / "models.py").write_text("MARKER = 'registered'\n", encoding="utf-8")

    try:
        AppModule(name="probe_feature", package="probe_feature").import_models()
        assert sys.modules["probe_feature.models.models"].MARKER == "registered"
    finally:
        for name in list(sys.modules):
            if name == "probe_feature" or name.startswith("probe_feature."):
                sys.modules.pop(name, None)

    assert DeclarativeBase is not None  # import 사용 표시
