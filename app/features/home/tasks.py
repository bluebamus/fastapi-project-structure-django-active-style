"""Home 기능의 Celery 태스크 (registry 가 발견하는 선택 모듈 — ADR-009).

워커는 `AppRegistry().task_modules()` 로 이 모듈을 include 한다. 이 앱 디렉터리를
지우면 태스크도 함께 사라지고 워커는 그대로 뜬다.

요청 밖이라 `Depends` 가 없다. 세션은 `background_db_session` 이 열고 닫으며(커밋·
롤백 포함), 서비스는 API 와 같은 provider 함수 `build_user_access_log_service` 로
조립한다 — 조립 경로를 두 벌 두지 않는다.
"""

from typing import Any

from celery.schedules import crontab

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_db_session
from app.features.home.dependencies.access_log_dependencies import (
    build_access_log_retention_service,
    build_user_access_log_service,
)

PURGE_TASK_NAME = "home.purge_expired_access_logs"


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크). 태스크 이름은 이동 전과 같다."""

    async def _run() -> dict[str, Any]:
        async with background_db_session() as session:
            stats = await build_user_access_log_service(session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result


@celery_app.task(name=PURGE_TASK_NAME)
def purge_expired_access_logs() -> dict[str, Any]:
    """보존 기간(``ACCESS_LOG_RETENTION_DAYS``)이 지난 접속 로그를 배치로 지운다."""

    async def _run() -> int:
        async with background_db_session() as session:
            return await build_access_log_retention_service(session).purge_expired()

    deleted: int = run_async(_run())
    return {"deleted": deleted}


# beat 스케줄은 태스크를 가진 기능이 등록한다 — 중앙 Celery 앱은 기능을 import 하지 않는다.
# beat 도 워커처럼 시작 시 include(이 모듈)를 import 하므로 이 등록이 보인다.
# crontab 은 Celery `timezone`(= TIME_ZONE) 지역 시각으로 해석된다: 매일 03:30.
celery_app.conf.beat_schedule[PURGE_TASK_NAME] = {
    "task": PURGE_TASK_NAME,
    "schedule": crontab(hour=3, minute=30),
}
