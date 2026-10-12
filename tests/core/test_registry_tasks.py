"""registry 의 Celery 태스크 모듈 발견 (service-hardening 단계 E, ADR-009).

`tasks.py` 는 다른 구성요소와 같은 **선택 모듈**이다 — 있으면 워커 include 에 들어가고,
없으면 빠진다. 앱 디렉터리를 지우면 그 앱의 태스크도 함께 사라져야 하고, 남은 앱으로
include 를 만드는 데 실패하면 안 된다.
"""

import sys

from app.core.registry import AppRegistry


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
