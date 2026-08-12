"""모듈은 있는데 export 가 틀린 경우를 "선택 기능 없음" 으로 처리하지 않는다 (NFR-04).

파일 부재와 계약 위반은 전혀 다른 사건이다.

    파일이 없다   → 그 기능을 안 쓰겠다는 선언. 정상.
    파일은 있는데
    export 가 틀리다 → 쓰려다 실패한 것. 조용히 건너뛰면 개발자는 자기가 만든
                       라우터·관리 화면이 왜 안 뜨는지 알 수 없다.

관대한 `getattr(module, "...", None)` 은 이 둘을 같은 것으로 만든다. 그래서
계약 위반은 `AppContractError` 로 기동을 멈춘다.
"""

import sys
import types

import pytest
from fastapi import APIRouter

from app.core.registry import AppContractError, AppModule


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


# ---------------------------------------------------------------------------
# 라우터 계약
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Admin 계약
# ---------------------------------------------------------------------------

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
