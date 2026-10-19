"""접속 로그 보존 정리 (security-ops-hardening ADR-002).

in-memory SQLite 로 서비스 → 리포지토리 → DELETE 를 실제로 돌린다. 시계는 주입한다.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from celery.schedules import crontab
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home import tasks as home_tasks
from app.features.home.dependencies import access_log_dependencies
from app.features.home.models.models import UserAccessLog
from app.features.home.services.access_log_retention_service import AccessLogRetentionService
from config import MiddlewareSettings

NOW = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _add(session, *created_at: datetime) -> None:
    for i, at in enumerate(created_at):
        session.add(
            UserAccessLog(
                ip_address="10.0.0.1", request_path=f"/p{i}", request_method="GET", created_at=at
            )
        )
    await session.commit()


async def _remaining(session) -> list[datetime]:
    rows = await session.execute(
        select(UserAccessLog.created_at).order_by(UserAccessLog.created_at)
    )
    return list(rows.scalars().all())


def _service(session, days=365, batch_size=5000) -> AccessLogRetentionService:
    return AccessLogRetentionService(
        session, retention_days=days, clock=lambda: NOW, batch_size=batch_size
    )


async def test_only_rows_older_than_the_cutoff_are_deleted(session):
    cutoff = NOW - timedelta(days=365)
    await _add(
        session,
        cutoff - timedelta(days=400),
        cutoff - timedelta(microseconds=1),
        cutoff,  # 정확히 N일 전 — 남는다
        cutoff + timedelta(seconds=1),
        NOW,
    )

    deleted = await _service(session).purge_expired()

    assert deleted == 2
    assert await _remaining(session) == [cutoff, cutoff + timedelta(seconds=1), NOW]


async def test_deletes_in_batches_and_commits_each_batch(session, monkeypatch):
    old = NOW - timedelta(days=500)
    await _add(session, *(old + timedelta(seconds=i) for i in range(5)))
    service = _service(session, batch_size=2)
    commits = []
    original_commit = service.commit

    async def counting_commit():
        commits.append(len(await _remaining(session)))
        await original_commit()

    monkeypatch.setattr(service, "commit", counting_commit)

    assert await service.purge_expired() == 5
    # 2 → 2 → 1(마지막 배치가 batch_size 보다 작아 멈춘다). 커밋 시점마다 남은 행이 줄어든다.
    assert commits == [3, 1, 0]
    assert await _remaining(session) == []


async def test_zero_retention_deletes_nothing(session, monkeypatch):
    await _add(session, NOW - timedelta(days=5000))
    service = _service(session, days=0)

    async def must_not_run(*_args):
        raise AssertionError("보존 0 인데 삭제 쿼리를 실행했다")

    monkeypatch.setattr(service.repository, "delete_created_before", must_not_run)

    assert await service.purge_expired() == 0
    assert len(await _remaining(session)) == 1


def test_negative_retention_is_rejected_by_service_and_settings():
    with pytest.raises(ValueError):
        AccessLogRetentionService(object(), retention_days=-1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MiddlewareSettings(_env_file=None, ACCESS_LOG_RETENTION_DAYS=-1)  # type: ignore[call-arg]


def test_retention_defaults_to_one_year_and_reads_the_env(monkeypatch):
    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 365  # type: ignore[call-arg]
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "30")
    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 30  # type: ignore[call-arg]


def test_provider_uses_the_configured_retention(monkeypatch):
    monkeypatch.setattr(
        access_log_dependencies.middleware_settings, "ACCESS_LOG_RETENTION_DAYS", 30
    )

    service = access_log_dependencies.build_access_log_retention_service(object())  # type: ignore[arg-type]

    assert isinstance(service, AccessLogRetentionService)
    assert service.retention_days == 30


def test_purge_task_is_scheduled_daily_at_0330_local_time():
    from app.celery.app import celery_app
    from config import timezone_settings

    assert home_tasks.PURGE_TASK_NAME in celery_app.tasks
    entry = celery_app.conf.beat_schedule[home_tasks.PURGE_TASK_NAME]
    assert entry["task"] == home_tasks.PURGE_TASK_NAME
    assert entry["schedule"] == crontab(hour=3, minute=30)
    # crontab 은 Celery timezone(= TIME_ZONE) 지역 시각으로 해석된다.
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE


def test_purge_task_builds_its_service_through_the_home_provider(monkeypatch):
    session = object()
    built_with = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class _FakeService:
        async def purge_expired(self):
            return 42

    def fake_provider(received):
        built_with.append(received)
        return _FakeService()

    monkeypatch.setattr(home_tasks, "background_db_session", fake_background_session)
    monkeypatch.setattr(home_tasks, "build_access_log_retention_service", fake_provider)
    monkeypatch.setattr(home_tasks, "run_async", asyncio.run)

    assert home_tasks.purge_expired_access_logs() == {"deleted": 42}
    assert built_with == [session]


async def test_rowcount_matches_count_query(session):
    """반환값이 실제로 지운 행 수와 같다(로그·태스크 결과가 거짓말하지 않는다)."""
    await _add(session, *(NOW - timedelta(days=366 + i) for i in range(7)))
    before = (await session.execute(select(func.count(UserAccessLog.id)))).scalar_one()

    deleted = await _service(session, batch_size=3).purge_expired()

    after = (await session.execute(select(func.count(UserAccessLog.id)))).scalar_one()
    assert deleted == before - after == 7
