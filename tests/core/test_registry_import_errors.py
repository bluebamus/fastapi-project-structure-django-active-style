"""자동 발견이 "선택 파일 없음" 과 "파일 안의 import 오류" 를 구분하는지 고정한다 (NFR-03).

`AppRegistry` 는 `admin.py` · `models` · `api/routers/router.py` 를 **선택 파일**로
다뤄, 없으면 조용히 건너뛴다. 문제는 그 판정을 `ModuleNotFoundError` 하나로
한다는 점이다. 파일이 실제로 있고 그 **안의 import 한 줄이 틀린** 경우도 같은
예외로 잡혀 "선택 파일 없음" 으로 삼켜진다.

결과: 오타 하나에 서버는 에러 없이 뜨고, 그 기능의 라우터·Admin·테이블만
조용히 사라진다. 원인 추적이 매우 어렵다.

판정 기준은 "없다고 하는 모듈이 **내가 찾던 바로 그 모듈인가**" 다.
다른 모듈 때문이라면 숨기지 않고 원래 예외를 그대로 올린다.
"""

import pytest

from app.core.registry import AppModule

# ---------------------------------------------------------------------------
# 정상 경로 — 선택 파일이 없으면 조용히 건너뛴다
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 결함 경로 — 선택 파일 '안' 의 import 오류는 숨기지 않는다
# ---------------------------------------------------------------------------


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
