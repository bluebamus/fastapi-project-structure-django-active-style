"""SQLAdmin 배선 테스트 (기능 소유 + registry 자동 취합 기준).

``ModelView`` 는 기능이 소유하고(``app/features/<name>/admin.py``), ``AppRegistry`` 가
발견된 앱에서 ``admin_views`` 를 모아 등록한다. ``main.py`` 는 ADMIN=true 일 때
``register_admin(app, engine, registry)`` 만 호출한다.

여기서 확인하는 것:
    1. registry 취합 결과가 기능 디렉터리에서 독립적으로 만든 기대 목록과 **순서까지** 같다
    2. 모델을 가진 기능은 빠짐없이 자기 ``admin.py`` 를 갖는다
    3. 부팅된 앱의 SQLAdmin 에 그대로 등록됐고 ``/admin`` 이 마운트됐다
    4. ADMIN=false 일 때 관리 계층이 **로드조차 되지 않는다** (SEC-01)
    5. 중앙 취합 목록이 코드에 남아 있지 않다 (FR-08)

1번이 핵심이다. 자동 취합은 편하지만 조용하다 — 앱 하나가 발견에서 빠지면 그 앱의
관리 화면만 사라지고 ``/admin`` 은 멀쩡히 뜬다. 그래서 기대 목록을 registry 가 아닌
**디렉터리에서 따로** 만들어 대조한다. 같은 출처를 쓰면 비교가 무의미해진다.
"""

from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys
from typing import cast

import pytest
from fastapi import FastAPI
from sqladmin import Admin

from app.core.db.session import engine as _ENGINE
from app.core.registry import AppRegistry

EXPECTED_MANAGED_MODELS = {
    "Post",
    "Product",
    "Reply",
    "SalesOrder",
    "SnsPost",
    "User",
    "UserAccessLog",
}

# main.py 가 있는 저장소 루트 (tests/ 의 부모).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FEATURES_DIR = _REPO_ROOT / "app" / "features"


class _Recorder:
    """SQLAdmin ``Admin`` 의 add_view 만 흉내낸다 — 실제 Admin 은 엔진이 필요하다."""

    def __init__(self) -> None:
        self.collected: list[type] = []

    def add_view(self, view: type) -> None:
        self.collected.append(view)


def _feature_dirs_with_admin() -> list[str]:
    """``admin.py`` 를 가진 기능 디렉터리 이름을 알파벳순으로.

    registry 를 쓰지 않고 파일시스템만 본다 — 비교 대상의 출처를 분리하기 위해서다.
    """
    return sorted(
        entry.name
        for entry in _FEATURES_DIR.iterdir()
        if entry.is_dir() and not entry.name.startswith("_") and (entry / "admin.py").is_file()
    )


def _expected_views() -> list[type]:
    """기능 디렉터리에서 직접 모은 기대 뷰 목록(앱 이름 사전순, 선언 순서 유지)."""
    views: list[type] = []
    for feature in _feature_dirs_with_admin():
        module = importlib.import_module(f"app.features.{feature}.admin")
        views.extend(module.admin_views)
    return views


def _installed_views() -> list[type]:
    """registry 가 실제로 등록하는 뷰 목록."""
    registry = AppRegistry()
    registry.discover()
    recorder = _Recorder()
    registry.install_admin(recorder)
    return recorder.collected


def _registry_diff(expected: list[type], actual: list[type]) -> dict[str, object]:
    """두 뷰 목록의 차이를 진단 가능한 형태로 돌려주는 **순수 함수**.

    모델 이름이 아니라 **클래스 자체**로 비교한다 — 서로 다른 클래스가 우연히 같은
    모델을 가리키는 경우를 구분하기 위해서다.
    이 함수 자체의 정확성은 아래 ``test_registry_diff_*`` 가 합성 입력으로 검증한다.
    """
    return {
        "missing": [v for v in expected if v not in actual],
        "unexpected": [v for v in actual if v not in expected],
        "duplicated": sorted({v.__name__ for v in actual if actual.count(v) > 1}),
        "order_only": set(expected) == set(actual) and expected != actual,
    }


# =============================================================================
# registry 취합 완전성
# =============================================================================
def test_feature_list_is_not_vacuous() -> None:
    """탐지 대상이 비어 있으면 아래 테스트가 헛통과한다."""
    assert len(_feature_dirs_with_admin()) >= 5


def test_registry_collects_every_feature_admin_view() -> None:
    """registry 취합 결과가 기능별 admin_views 전량과 **순서까지** 일치한다.

    순서를 계약에 넣는 이유: SQLAdmin 사이드바 메뉴가 ``add_view()`` 호출 순서를
    따르므로 순서가 사용자에게 보인다. registry 는 앱 이름 알파벳순으로 등록한다.
    """
    expected = _expected_views()
    actual = _installed_views()
    diff = _registry_diff(expected, actual)

    assert not diff["missing"], (
        f"기능에는 있는데 registry 가 등록하지 않은 뷰: "
        f"{[v.__name__ for v in cast(list, diff['missing'])]}. "
        "해당 앱이 발견에서 빠졌거나 admin.py 경로 규약을 벗어났는지 확인하세요."
    )
    assert not diff[
        "unexpected"
    ], f"registry 만 등록한 뷰: {[v.__name__ for v in cast(list, diff['unexpected'])]}"
    assert not diff["duplicated"], f"중복 등록된 뷰: {diff['duplicated']}"
    assert not diff["order_only"], (
        f"구성은 같으나 순서가 다릅니다. 기대(앱 이름 사전순): "
        f"{[v.__name__ for v in expected]} / 실제: {[v.__name__ for v in actual]}"
    )
    assert actual == expected


def test_registry_views_cover_expected_models() -> None:
    """취합된 뷰가 관리 대상 모델 전체를 담는다."""
    managed = {view.model.__name__ for view in _installed_views()}
    assert managed == EXPECTED_MANAGED_MODELS


def test_no_central_admin_list_remains() -> None:
    """중앙 취합 목록(ADMIN_VIEWS)이 코드에 남아 있지 않다 (FR-08).

    남아 있으면 "새 앱은 자동, 옛 앱은 수동" 인 반쪽 상태가 된다.
    """
    source = (_FEATURES_DIR / "admin.py").read_text(encoding="utf-8")
    code_lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
    joined = "\n".join(code_lines)

    assert "ADMIN_VIEWS: list" not in joined, "app/features/admin.py 에 중앙 뷰 목록이 남아 있다"
    for feature in _feature_dirs_with_admin():
        assert (
            f"from app.features.{feature}.admin import" not in joined
        ), f"app/features/admin.py 가 '{feature}' 의 admin 을 명시 import 하고 있다"


# --- 위 검사가 쓰는 비교 로직 자체의 유효성 (헛통과 방지) ---
class _VA:
    pass


class _VB:
    pass


class _VC:
    pass


def test_registry_diff_detects_missing_view() -> None:
    """기능에는 있는데 취합에 없는 뷰를 잡는다 — 자동 취합의 핵심 사각지대."""
    diff = _registry_diff([_VA, _VB], [_VA])
    assert diff["missing"] == [_VB]
    assert diff["unexpected"] == []


def test_registry_diff_detects_unexpected_and_duplicate() -> None:
    diff = _registry_diff([_VA], [_VA, _VB, _VB])
    assert diff["unexpected"] == [_VB, _VB]
    assert diff["duplicated"] == ["_VB"]


def test_registry_diff_detects_order_only_difference() -> None:
    """구성이 같고 순서만 다른 경우를 별도로 식별한다."""
    diff = _registry_diff([_VA, _VB], [_VB, _VA])
    assert diff["order_only"] is True
    assert diff["missing"] == [] and diff["unexpected"] == []


def test_registry_diff_reports_nothing_when_identical() -> None:
    diff = _registry_diff([_VA, _VB, _VC], [_VA, _VB, _VC])
    assert diff == {"missing": [], "unexpected": [], "duplicated": [], "order_only": False}


# =============================================================================
# 기능별 소유 계약
# =============================================================================
@pytest.mark.parametrize("feature", _feature_dirs_with_admin())
def test_feature_with_admin_module_exposes_views(feature: str) -> None:
    """admin.py 를 가진 기능은 admin_views 를 노출한다."""
    module = importlib.import_module(f"app.features.{feature}.admin")
    views = getattr(module, "admin_views", None)
    assert views, f"app/features/{feature}/admin.py 가 admin_views 를 노출하지 않습니다"


def test_every_model_feature_owns_admin_module() -> None:
    """모델을 가진 기능은 빠짐없이 자기 admin.py 를 갖는다.

    registry 는 admin.py 가 **없으면** 조용히 건너뛴다(선택 구성요소). 그래서
    "모델은 있는데 관리 화면만 안 만든 새 기능" 은 무신호로 지나갈 수 있다 —
    그것을 여기서 막는다.
    """
    from app.core.db.models_registry import iter_model_modules

    with_models = {dotted.split(".")[2] for dotted in iter_model_modules()}
    with_admin = set(_feature_dirs_with_admin())

    missing = with_models - with_admin
    assert not missing, f"모델은 있는데 admin.py 가 없는 기능: {sorted(missing)}"


# =============================================================================
# 부팅된 애플리케이션
# =============================================================================
def test_admin_layer_is_not_loaded_when_disabled() -> None:
    """ADMIN=false 면 sqladmin 을 아예 로드하지 않는다 (SEC-01).

    기능 패키지 ``__init__.py`` 가 ``admin_views`` 를 재노출하면, registry 가 라우터를
    얻으려고 패키지를 import 하는 것만으로 sqladmin 과 ModelView 가 전부 올라온다. 그러면
    ADMIN=false 는 "라우트만 안 붙임" 이 되어 설정의 의미가 실제와 어긋나고, sqladmin 을
    선택적 의존성으로 분리할 수도 없다(ADMIN-2).

    registry 쪽에도 같은 함정이 있다 — ``app/core/registry.py`` 가 모듈 레벨에서
    sqladmin 을 import 하면 이 검사가 깨진다.

    별도 프로세스로 확인한다 — 이 테스트 세션은 다른 테스트가 이미 ``main`` 을 import 해
    ``sys.modules`` 가 오염돼 있어, 같은 프로세스에서는 판별이 불가능하다.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, sys;"
            " os.environ['ADMIN'] = 'false'; os.environ['DEBUG'] = 'false';"
            " import main;"
            " print('SQLADMIN_LOADED=' + str('sqladmin' in sys.modules))",
        ],
        capture_output=True,
        text=True,
        errors="replace",
        cwd=_REPO_ROOT,
    )
    assert (
        "SQLADMIN_LOADED=" in result.stdout
    ), f"ADMIN=false 로 앱을 띄우지 못했습니다.\nstderr:\n{result.stderr[-2000:]}"
    assert "SQLADMIN_LOADED=False" in result.stdout, (
        "ADMIN=false 인데 sqladmin 이 로드됐습니다. 기능 패키지 __init__.py 또는 "
        "app/core/registry.py 가 admin 모듈을 import 하고 있지 않은지 확인하세요."
    )


def test_main_registers_every_admin_view() -> None:
    """부팅된 앱의 SQLAdmin 에 모든 모델 뷰가 등록된다."""
    import main

    registered = {view.model.__name__ for view in main.admin._views}
    assert registered == EXPECTED_MANAGED_MODELS


def test_admin_page_is_mounted() -> None:
    import main

    assert any(getattr(route, "path", "") == "/admin" for route in main.app.routes)


# =============================================================================
# 조립 함수의 책임 분리
# =============================================================================
def _fresh_app() -> FastAPI:
    """부팅된 main.app 을 오염시키지 않도록 매번 새 앱을 쓴다."""
    return FastAPI()


def test_create_admin_interface_mounts_but_registers_nothing() -> None:
    """생성 함수는 /admin 을 붙이되 ModelView 는 하나도 등록하지 않는다."""
    from app.features.admin import create_admin_interface

    app = _fresh_app()
    admin = create_admin_interface(app, _ENGINE)

    assert isinstance(admin, Admin)
    assert any(
        getattr(route, "path", "") == "/admin" for route in app.routes
    ), "create_admin_interface() 가 /admin 을 마운트하지 않았습니다"
    assert (
        list(admin._views) == []
    ), "create_admin_interface() 가 뷰를 등록했습니다 — 등록은 registry 의 책임입니다"


def test_register_admin_creates_then_installs_and_returns_same_admin(monkeypatch) -> None:
    """조합 함수는 생성 → 등록 순서로 부르고, 생성된 Admin 을 그대로 돌려준다.

    순서가 뒤집히면 등록 대상 Admin 이 아직 없다.
    """
    from app.features import admin as admin_module

    order: list[str] = []
    sentinel = object()

    def fake_create(app_arg, engine_arg):
        order.append("create")
        return sentinel

    class _FakeRegistry:
        def install_admin(self, admin_arg):
            order.append("install")
            assert admin_arg is sentinel, "생성된 Admin 이 등록 단계로 전달되지 않았습니다"
            return 0

    monkeypatch.setattr(admin_module, "create_admin_interface", fake_create)

    returned = admin_module.register_admin(
        _fresh_app(), _ENGINE, cast(AppRegistry, _FakeRegistry())
    )

    assert order == ["create", "install"], f"호출 순서가 생성→등록이 아닙니다: {order}"
    assert returned is sentinel, "register_admin() 이 생성된 Admin 을 반환하지 않았습니다"


def test_register_admin_reuses_the_given_registry() -> None:
    """register_admin 은 넘겨받은 registry 만 쓰고 스스로 발견하지 않는다 (NFR-05)."""
    from app.features.admin import register_admin

    empty = AppRegistry()  # discover() 를 부르지 않은 빈 레지스트리
    admin = register_admin(_fresh_app(), _ENGINE, empty)

    assert list(admin._views) == [], "register_admin 이 자체적으로 앱을 발견했습니다"


def test_register_admin_end_to_end_matches_expected_models() -> None:
    """조합 결과가 기대 모델 전체를 담는다(위임이 실제로 동작하는지)."""
    from app.features.admin import register_admin

    registry = AppRegistry()
    registry.discover()
    admin = register_admin(_fresh_app(), _ENGINE, registry)

    assert {view.model.__name__ for view in admin._views} == EXPECTED_MANAGED_MODELS
