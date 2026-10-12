"""home 기능의 Celery 태스크 (app/features/home/tasks.py — ADR-009)."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.features.home import tasks as home_tasks


def test_aggregate_task_registered_under_a_stable_name():
    from app.celery.app import celery_app

    assert "home.aggregate_access_stats" in celery_app.tasks
    assert home_tasks.aggregate_access_stats.name == "home.aggregate_access_stats"


def test_task_builds_its_service_through_the_home_provider(monkeypatch):
    """태스크는 서비스를 직접 만들지 않고 API 와 같은 provider 로 조립한다."""
    session = object()
    built_with = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class _FakeService:
        async def get_stats(self):
            return SimpleNamespace(total_count=7)

    def fake_provider(received):
        built_with.append(received)
        return _FakeService()

    monkeypatch.setattr(home_tasks, "background_db_session", fake_background_session)
    monkeypatch.setattr(home_tasks, "build_user_access_log_service", fake_provider)
    monkeypatch.setattr(home_tasks, "run_async", asyncio.run)

    assert home_tasks.aggregate_access_stats() == {"total": 7}
    assert built_with == [session]
