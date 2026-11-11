"""home 기능의 Celery 태스크 (app/features/home/tasks.py)."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from celery.schedules import crontab

from app.features.home import tasks as home_tasks


def test_aggregate_task_registered_under_a_stable_name():
    from app.celery.app import celery_app

    assert "home.aggregate_access_stats" in celery_app.tasks
    assert home_tasks.aggregate_access_stats.name == "home.aggregate_access_stats"


def test_purge_task_is_scheduled_daily_at_0330_local_time():
    from app.celery.app import celery_app
    from config import timezone_settings

    assert home_tasks.PURGE_TASK_NAME in celery_app.tasks
    entry = celery_app.conf.beat_schedule[home_tasks.PURGE_TASK_NAME]
    assert entry["task"] == home_tasks.PURGE_TASK_NAME
    assert entry["schedule"] == crontab(hour=3, minute=30)
    # crontab 은 Celery timezone(= TIME_ZONE) 지역 시각으로 해석된다.
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE


def _fake_session_and_provider(monkeypatch, provider_name: str, service):
    session = object()
    built_with = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    def fake_provider(received):
        built_with.append(received)
        return service

    monkeypatch.setattr(home_tasks, "background_db_session", fake_background_session)
    monkeypatch.setattr(home_tasks, provider_name, fake_provider)
    monkeypatch.setattr(home_tasks, "run_async", asyncio.run)
    return session, built_with


def test_aggregate_task_returns_the_total_from_a_background_session(monkeypatch):
    class _Service:
        async def get_stats(self):
            return SimpleNamespace(total_count=7)

    session, built_with = _fake_session_and_provider(
        monkeypatch, "build_user_access_log_service", _Service()
    )

    assert home_tasks.aggregate_access_stats() == {"total": 7}
    assert built_with == [session]


def test_purge_task_returns_the_deleted_count_from_a_background_session(monkeypatch):
    class _Service:
        async def purge_expired(self):
            return 42

    session, built_with = _fake_session_and_provider(
        monkeypatch, "build_access_log_retention_service", _Service()
    )

    assert home_tasks.purge_expired_access_logs() == {"deleted": 42}
    assert built_with == [session]
