"""AppRegistry 결선 — 컨벤션 모듈 로드, export 계약 위반, 선택 모듈 부재와 import 오류 구분,
라우터·모델·관리 화면·Celery 태스크 결선.
"""

import sys
import types

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
    """결선은 스스로 다시 스캔하지 않고 마지막 discover() 결과만 쓴다.

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


def _install(monkeypatch, dotted: str, **attrs):
    """이미 import 에 성공한 모듈을 흉내낸다.

    여기서 검사하는 것은 import 성공 **이후** 의 속성 계약이므로, 실제 파일을
    만들 필요가 없다. `importlib.import_module` 은 `sys.modules` 를 먼저 보므로
    이 주입이 그대로 사용된다.
    """
    module = types.ModuleType(dotted)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, dotted, module)
    return module


ROUTER_DOTTED = "probe_contract.api.routers.router"


def test_router_module_without_convention_export_fails(monkeypatch):
    """라우터 모듈은 있는데 `<name>_router` 가 없다 — 이름 오타의 전형이다."""
    _install(monkeypatch, ROUTER_DOTTED, some_other_router=APIRouter())

    with pytest.raises(AppContractError, match="probe_router"):
        AppModule(name="probe", package="probe_contract").load_router()


def test_router_export_of_wrong_type_fails(monkeypatch):
    """이름은 맞는데 APIRouter 가 아니다 — include_router 단계에서 터지기 전에 막는다."""
    _install(monkeypatch, ROUTER_DOTTED, probe_router="나는 라우터가 아니다")

    with pytest.raises(AppContractError, match="APIRouter 가 아닙니다"):
        AppModule(name="probe", package="probe_contract").load_router()


def test_valid_router_export_passes(monkeypatch):
    """정상 계약은 통과한다 — 위 두 가드가 정상 앱을 막지 않는지 확인."""
    router = APIRouter()
    _install(monkeypatch, ROUTER_DOTTED, probe_router=router)

    assert AppModule(name="probe", package="probe_contract").load_router() is router


ADMIN_DOTTED = "probe_contract.admin"


def test_admin_module_without_admin_views_fails(monkeypatch):
    """`admin.py` 는 있는데 `admin_views` 가 없다.

    과거 이 상황이 조용히 넘어가, `/admin` 은 정상 마운트된 채 등록 뷰만
    빠진 상태를 아무도 눈치채지 못했다.
    """
    _install(monkeypatch, ADMIN_DOTTED, ADMIN_VIEWS=[])

    with pytest.raises(AppContractError, match="admin_views"):
        AppModule(name="probe", package="probe_contract").load_admin_views()


def test_admin_views_not_a_list_fails(monkeypatch):
    """단일 클래스를 그대로 넣는 실수 — 순회하면 엉뚱하게 동작한다."""
    from tests.core._fakeapps.beta.admin import WidgetAdmin

    _install(monkeypatch, ADMIN_DOTTED, admin_views=WidgetAdmin)

    with pytest.raises(AppContractError, match="list 가 아닙니다"):
        AppModule(name="probe", package="probe_contract").load_admin_views()


def test_admin_views_item_must_be_modelview(monkeypatch):
    """ModelView 가 아닌 것을 넣으면 add_view 가 런타임에 이상하게 실패한다."""

    class NotAView:
        pass

    _install(monkeypatch, ADMIN_DOTTED, admin_views=[NotAView])

    with pytest.raises(AppContractError, match="ModelView 서브클래스가 아닙니다"):
        AppModule(name="probe", package="probe_contract").load_admin_views()


def test_valid_admin_views_pass(monkeypatch):
    """정상 계약은 통과한다."""
    from tests.core._fakeapps.beta.admin import GadgetAdmin, WidgetAdmin

    _install(monkeypatch, ADMIN_DOTTED, admin_views=[WidgetAdmin, GadgetAdmin])

    views = AppModule(name="probe", package="probe_contract").load_admin_views()
    assert views == [WidgetAdmin, GadgetAdmin]


def test_missing_optional_admin_is_skipped(fake_app):
    """`admin.py` 자체가 없으면 빈 목록을 돌려주고 넘어간다."""
    fake_app("probe_pkg_a", "__package__")
    assert AppModule(name="probe_a", package="probe_pkg_a").load_admin_views() == []


def test_missing_optional_router_is_skipped(fake_app):
    """라우터 모듈이 없으면 None 을 돌려주고 넘어간다."""
    fake_app("probe_pkg_b", "__package__")
    assert AppModule(name="probe_b", package="probe_pkg_b").load_router() is None


def test_missing_optional_models_is_skipped(fake_app):
    """models 가 없으면 조용히 넘어간다(모델 없는 기능도 있다)."""
    fake_app("probe_pkg_c", "__package__")
    AppModule(name="probe_c", package="probe_pkg_c").import_models()  # 예외 없이 통과


def test_broken_import_inside_admin_is_raised(fake_app):
    """`admin.py` 는 있는데 그 안의 import 가 틀렸다면 즉시 실패해야 한다."""
    fake_app("probe_pkg_d", "__package__")
    fake_app("probe_pkg_d.admin", "import definitely_not_a_real_module_xyz  # 오타를 흉내낸다")

    with pytest.raises(ModuleNotFoundError) as caught:
        AppModule(name="probe_d", package="probe_pkg_d").load_admin_views()

    # 원래 원인이 그대로 보존돼야 추적이 가능하다.
    assert "definitely_not_a_real_module_xyz" in str(caught.value)


def test_broken_import_inside_router_is_raised(fake_app):
    """라우터 모듈 내부의 import 오류도 숨기지 않는다."""
    fake_app("probe_pkg_e", "__package__")
    fake_app("probe_pkg_e.api", "__package__")
    fake_app("probe_pkg_e.api.routers", "__package__")
    fake_app("probe_pkg_e.api.routers.router", "import definitely_not_a_real_module_xyz")

    with pytest.raises(ModuleNotFoundError) as caught:
        AppModule(name="probe_e", package="probe_pkg_e").load_router()
    assert "definitely_not_a_real_module_xyz" in str(caught.value)


def test_broken_import_inside_models_is_raised(fake_app):
    """models 내부의 import 오류를 삼키면 테이블이 조용히 사라진다 — 즉시 실패."""
    fake_app("probe_pkg_f", "__package__")
    fake_app("probe_pkg_f.models", "import definitely_not_a_real_module_xyz")

    with pytest.raises(ModuleNotFoundError) as caught:
        AppModule(name="probe_f", package="probe_pkg_f").import_models()
    assert "definitely_not_a_real_module_xyz" in str(caught.value)


def test_parent_package_absence_still_counts_as_missing(fake_app):
    """`a.b.c` 를 찾는데 `a.b` 가 없으면 `c` 도 없는 것 — 선택 부재로 본다.

    상위 패키지 부재까지 오류로 올리면, 라우터 디렉터리를 만들지 않은 앱이
    전부 기동 실패한다.
    """
    fake_app("probe_pkg_g", "__package__")  # api/ 하위를 만들지 않는다
    assert AppModule(name="probe_g", package="probe_pkg_g").load_router() is None


def test_task_modules_lists_only_apps_with_a_tasks_module(fake_app):
    fake_app("probe_feats.alpha", "__package__")
    fake_app("probe_feats.alpha.tasks", "VALUE = 1\n")
    fake_app("probe_feats.beta", "__package__")

    registry = AppRegistry()
    registry.discover("probe_feats")

    assert registry.task_modules() == ["probe_feats.alpha.tasks"]


def test_removing_the_app_with_tasks_still_builds_the_include(fake_app):
    """태스크를 가진 앱이 없는 구성 — 목록이 비어도 오류가 아니다."""
    fake_app("probe_nohome.beta", "__package__")

    registry = AppRegistry()
    registry.discover("probe_nohome")

    assert registry.task_modules() == []


def test_task_discovery_does_not_import_the_task_module(fake_app):
    """태스크 모듈은 `celery_app` 을 import 한다 — 발견이 import 하면 순환이 된다."""
    fake_app("probe_lazy.alpha", "__package__")
    fake_app("probe_lazy.alpha.tasks", "raise RuntimeError('import 되면 안 된다')\n")

    registry = AppRegistry()
    registry.discover("probe_lazy")

    assert registry.task_modules() == ["probe_lazy.alpha.tasks"]
    assert "probe_lazy.alpha.tasks" not in sys.modules


def test_real_registry_finds_the_home_tasks_module():
    registry = AppRegistry()
    registry.discover()

    assert "app.features.home.tasks" in registry.task_modules()
