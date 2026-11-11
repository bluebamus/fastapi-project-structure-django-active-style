"""Celery 앱 — 설정, registry 기반 include, UTC, 태스크 등록, `run_async` 이벤트 루프 재사용."""

import asyncio

from app.celery.task import run_async


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")


def test_celery_include_comes_from_the_registry():
    """워커 include 는 registry 가 발견한 기능별 tasks 모듈이다."""
    from app.celery.app import celery_app
    from app.core.registry import AppRegistry

    registry = AppRegistry()
    registry.discover()

    assert list(celery_app.conf.include) == registry.task_modules()
    assert "app.features.home.tasks" in celery_app.conf.include
    assert "app.celery.tasks" not in celery_app.conf.include


def test_celery_keeps_internal_times_in_utc():
    """ETA·만료·결과 시각은 UTC 로 다룬다. TIME_ZONE 은 beat 표시용으로만 남는다."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE


def test_celery_include_modules_import_and_register_their_tasks():
    """워커가 기동할 때 하는 include import 를 여기서 한다.

    ``tasks.py`` 의 import 오류·이름 오타가 워커 기동 때가 아니라 CI 에서 드러난다.
    include 모듈마다 자기 모듈에서 정의한 태스크가 하나 이상 등록돼야 한다.
    """
    from app.celery.app import celery_app

    celery_app.loader.import_default_modules()

    registered = {task.__module__ for task in celery_app.tasks.values()}
    missing = [module for module in celery_app.conf.include if module not in registered]
    assert celery_app.conf.include, "include 가 비어 있다 — 발견이 깨졌다"
    assert missing == []
    assert "home.aggregate_access_stats" in celery_app.tasks


def test_run_async_reuses_a_single_live_loop() -> None:
    """연속 호출이 '동일한, 닫히지 않은' 루프에서 실행되어야 한다.

    루프 바인딩 자원(aiomysql 커넥션 등)이 태스크 간 재사용돼도 살아남으려면
    이 성질이 필수다. 매 호출 asyncio.run() 이면 루프가 매번 새로 생성·종료되어
    이 단언이 깨진다(= C1 재발).
    """
    seen: dict[str, asyncio.AbstractEventLoop] = {}

    async def capture(key: str) -> None:
        seen[key] = asyncio.get_running_loop()

    run_async(capture("first"))
    run_async(capture("second"))

    assert seen["first"] is seen["second"], "연속 태스크가 서로 다른 루프에서 실행됨"
    assert not seen["first"].is_closed(), "재사용 루프가 호출 사이에 닫힘"


def test_run_async_returns_coroutine_result() -> None:
    """브릿지가 코루틴의 반환값을 그대로 전달한다(기존 계약 유지)."""

    async def compute() -> int:
        await asyncio.sleep(0)
        return 21 * 2

    assert run_async(compute()) == 42
