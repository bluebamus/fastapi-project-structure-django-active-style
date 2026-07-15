"""SQLAdmin 배선 테스트 (AppRegistry 구조).

``AppRegistry.install_admin`` 은 발견된 각 앱의 ``app.domains.<name>.admin`` 을 직접
import 하여 ``admin_views`` 를 SQLAdmin 에 등록한다. 뷰가 없는 앱은 예외 없이 건너뛰므로
(``load_admin_views`` 의 ``getattr(module, "admin_views", [])``), 등록 누락은 조용히
지나간다. 여기서 실제 등록 개수와 대상 모델을 고정해 그 침묵을 막는다.

(default 저장소는 main.py 가 패키지 모듈에서 admin_views 를 읽으므로 배선 방식이
다르고, 그래서 이 파일은 저장소마다 다르다.)
"""

from __future__ import annotations

from app.core.registry import AppRegistry

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}


class _StubAdmin:
    """SQLAdmin 대신 등록 호출만 수집한다(DB·앱 부팅 불필요)."""

    def __init__(self) -> None:
        self.collected: list[type] = []

    def add_view(self, view: type) -> None:
        self.collected.append(view)


def test_registry_installs_every_domain_admin_view() -> None:
    registry = AppRegistry()
    registry.discover()

    stub = _StubAdmin()
    count = registry.install_admin(stub)

    registered = {view.model.__name__ for view in stub.collected}
    assert registered == EXPECTED_MANAGED_MODELS
    assert count == len(EXPECTED_MANAGED_MODELS)


def test_every_discovered_app_with_models_provides_admin_views() -> None:
    """모델을 가진 앱은 하나도 빠짐없이 admin_views 를 내놓는다."""
    registry = AppRegistry()
    registry.discover()

    for module in registry.enabled_apps:
        views = module.load_admin_views()
        assert views, f"앱 '{module.name}' 이 admin_views 를 노출하지 않습니다(빈 admin.py?)"
