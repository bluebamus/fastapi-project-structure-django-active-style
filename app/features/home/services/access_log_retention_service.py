"""접속 로그 보존 정책 (security-ops-hardening ADR-002).

``ACCESS_LOG_RETENTION_DAYS`` 일보다 오래된 접속 로그를 배치로 나눠 지운다. 실행은
``app/features/home/tasks.py`` 의 Celery 태스크가 beat 스케줄(매일 03:30, ``TIME_ZONE``)로 한다.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository

DEFAULT_BATCH_SIZE = 5000


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AccessLogRetentionService(BaseService):
    """보존 기간이 지난 접속 로그를 지운다.

    **배치마다 커밋한다** — 다른 서비스와 달리 트랜잭션 경계를 스스로 정하는 이유는, 1년 치를
    한 트랜잭션으로 지우면 잠금이 길어지고 undo 로그가 커져 적재(INSERT)까지 막기 때문이다.
    중간에 실패해도 이미 커밋한 배치는 남고, 다음 실행이 나머지를 이어서 지운다(멱등).

    Args:
        session: 요청 밖 세션(``background_db_session``).
        retention_days: 보존 일수. ``0`` 이면 아무것도 지우지 않는다.
        clock: 기준 시각(UTC aware). 테스트가 시계를 주입한다.
        batch_size: 한 번에 지울 최대 행 수.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        retention_days: int,
        clock: Callable[[], datetime] = _utc_now,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        super().__init__(session)
        if retention_days < 0:
            raise ValueError("retention_days 는 0 이상이어야 합니다.")
        if batch_size < 1:
            raise ValueError("batch_size 는 1 이상이어야 합니다.")
        self.repository = UserAccessLogRepository(session)
        self.retention_days = retention_days
        self.batch_size = batch_size
        self._clock = clock

    def cutoff(self) -> datetime:
        """이 시각보다 **이전**(``<``)에 만든 행이 삭제 대상이다 — 정확히 N일 전 행은 남는다."""
        return self._clock() - timedelta(days=self.retention_days)

    async def purge_expired(self) -> int:
        """보존 기간이 지난 행을 배치로 지우고 지운 총 행 수를 돌려준다."""
        if self.retention_days == 0:
            self.log.info("접속 로그 보존 기간 0 — 삭제하지 않음")
            return 0
        cutoff = self.cutoff()
        total = 0
        while True:
            deleted = await self.repository.delete_created_before(cutoff, self.batch_size)
            await self.commit()
            total += deleted
            if deleted < self.batch_size:
                break
        self.log.info(
            "접속 로그 보존 정리 완료: deleted=%d cutoff=%s days=%d",
            total,
            cutoff.isoformat(),
            self.retention_days,
        )
        return total
