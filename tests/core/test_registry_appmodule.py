"""앱 하나의 구성요소 로딩 규칙 — 라우터·모델·Admin 은 모두 선택이다 (FR-07, BC-06)."""

from fastapi import APIRouter

from app.core.registry import AppModule

ALPHA = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
BETA = AppModule(name="beta", package="tests.core._fakeapps.beta")


def test_router_attr_follows_name_convention():
    assert ALPHA.router_attr == "alpha_router"
    assert ALPHA.prefix == "/api"


def test_load_router_returns_convention_router():
    assert isinstance(ALPHA.load_router(), APIRouter)


def test_load_router_missing_module_returns_none():
    """라우터 모듈이 없는 앱은 정상이다 — None 을 돌려주고 넘어간다."""
    assert BETA.load_router() is None


def test_load_admin_views_collects_module_level_list():
    views = BETA.load_admin_views()
    assert [v.__name__ for v in views] == ["WidgetAdmin", "GadgetAdmin"]


def test_load_admin_views_missing_module_returns_empty():
    """admin 모듈이 없는 앱은 정상이다 — 빈 목록."""
    assert ALPHA.load_admin_views() == []


def test_import_models_registers_tables():
    """models 를 import 하면 해당 앱의 메타데이터에 테이블이 올라온다."""
    BETA.import_models()

    from tests.core._fakeapps.beta.models import FakeBase

    assert set(FakeBase.metadata.tables) == {"fake_widgets", "fake_gadgets"}


def test_import_models_without_models_package_is_noop():
    """모델이 없는 앱(실제 `auth` 같은)도 예외 없이 통과한다 (BC-06)."""
    assert ALPHA.import_models() is None
