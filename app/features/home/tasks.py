"""Home 기능의 Celery 태스크 (registry 가 발견하는 선택 모듈 — ADR-009).

워커는 `AppRegistry().task_modules()` 로 이 모듈을 include 한다. 이 앱 디렉터리를
지우면 태스크도 함께 사라지고 워커는 그대로 뜬다.

요청 밖이라 `Depends` 가 없다. 세션은 `background_db_session` 이 열고 닫으며(커밋·
롤백 포함), 서비스는 API 와 같은 provider 함수 `build_user_access_log_service` 로
조립한다 — 조립 경로를 두 벌 두지 않는다.
"""

from typing import Any

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_db_session
from app.features.home.dependencies.access_log_dependencies import (
    build_user_access_log_service,
)


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크). 태스크 이름은 이동 전과 같다."""

    async def _run() -> dict[str, Any]:
        async with background_db_session() as session:
            stats = await build_user_access_log_service(session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result
