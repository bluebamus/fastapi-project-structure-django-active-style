"""Home 도메인 등록은 AppRegistry 자동 배선으로 이뤄진다.

home 패키지 __init__.py 는 import 시점에 access-log sink 만 등록한다(register_sink).
라우터는 **재노출하지 않는다** — registry 가 컨벤션 경로 ``api/routers/router.py``
에서 직접 가져가 /api 에 마운트한다(Phase 1 패키지 init 경량화, 경계는
``tests/core/test_import_boundary.py``).
"""


def test_register_sink_installs_home_sink():
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.features.home.access_log_sink import HomeAccessLogSink, register_sink

    original = get_access_log_sink()
    try:
        set_access_log_sink(None)
        register_sink()
        assert isinstance(get_access_log_sink(), HomeAccessLogSink)
    finally:
        set_access_log_sink(original)


def test_home_package_stays_light():
    """패키지 __init__ 은 라우터를 재노출하지 않는다 — 발견만으로 라우팅 트리를 올리지 않기 위해."""
    from app.features import home

    assert not hasattr(
        home, "router"
    ), "home 패키지가 router 를 재노출합니다 — 발견 단계에서 라우팅 트리가 끌려옵니다."


def test_registry_mounts_home_router_under_api():
    """재노출 없이도 registry 가 home 라우터를 /api 에 마운트한다."""
    from app.features.home.api.routers.router import home_router

    assert home_router is not None

    from main import app

    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    paths = set(app.openapi()["paths"])
    assert any(p.startswith("/api/v1/home") for p in paths)
