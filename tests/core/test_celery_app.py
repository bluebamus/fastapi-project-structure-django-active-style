import ast
from pathlib import Path

CELERY_PACKAGE = Path(__file__).resolve().parents[2] / "app" / "celery"


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")


def test_celery_include_comes_from_the_registry():
    """워커 include 는 registry 가 발견한 기능별 tasks 모듈이다(ADR-009)."""
    from app.celery.app import celery_app
    from app.core.registry import AppRegistry

    registry = AppRegistry()
    registry.discover()

    assert list(celery_app.conf.include) == registry.task_modules()
    assert "app.features.home.tasks" in celery_app.conf.include
    assert "app.celery.tasks" not in celery_app.conf.include


def test_celery_package_does_not_import_features():
    """중앙 Celery 패키지는 기능을 모른다 — 기능을 지워도 워커가 import 오류로 죽지 않는다."""
    offenders = []
    for path in sorted(CELERY_PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            offenders += [f"{path.name}: {n}" for n in names if n.startswith("app.features")]

    assert offenders == []


def test_celery_keeps_internal_times_in_utc():
    """ETA·만료·결과 시각은 UTC 로 다룬다(ADR-007). TIME_ZONE 은 beat 표시용으로만 남는다."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE
