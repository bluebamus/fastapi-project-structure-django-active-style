"""
UserAccessLog Service

접속 로그 관련 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성 또는 background_db_session 이 책임진다.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.home.exceptions import InvalidDateRangeException
from app.features.home.models.models import UserAccessLog
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.features.home.schemas.user_access_log_schema import (
    AccessLogStats,
    BrowserStats,
    DeviceTypeStats,
    OSStats,
    UserAccessLogCreate,
)

# 길이 상한은 모델 컬럼에서 도출한다 — 숫자를 두 번 적지 않는다(Text 는 length=None 이라 빠진다).
_COLUMN_LIMITS: dict[str, int] = {
    column.name: column.type.length
    for column in UserAccessLog.__table__.columns
    if isinstance(column.type, String) and column.type.length
}


def truncate_to_columns(data: dict[str, Any]) -> dict[str, Any]:
    """문자열 값을 모델 컬럼 길이로 자른 사본을 돌려준다.

    헤더·쿠키는 클라이언트가 길이를 정한다. 컬럼보다 긴 값이 오면 MySQL strict 모드는
    INSERT 전체를 거부해 그 요청의 접속 기록이 통째로 사라진다 — 잘린 기록이 없는 기록보다 낫다.
    """
    return {
        key: value[: _COLUMN_LIMITS[key]]
        if isinstance(value, str) and key in _COLUMN_LIMITS
        else value
        for key, value in data.items()
    }


class UserAccessLogService(BaseService):
    """접속 로그 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = UserAccessLogRepository(session)

    async def create_access_log(
        self,
        data: UserAccessLogCreate | dict[str, Any],
    ) -> UserAccessLog:
        """접속 로그를 생성한다(커밋은 호출자가 수행)."""
        data_dict = data.model_dump() if isinstance(data, UserAccessLogCreate) else data
        self.log.debug("접속 로그 생성: path=%s", data_dict.get("request_path"))
        return await self.repository.create(truncate_to_columns(data_dict))

    async def get_access_logs(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[UserAccessLog], int]:
        """접속 로그 목록과 전체 개수를 조회한다."""
        self.log.debug("접속 로그 목록 조회: skip=%s, limit=%s", skip, limit)
        logs = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total

    async def get_recent_logs(self, limit: int = 50) -> Sequence[UserAccessLog]:
        """최근 접속 로그를 조회한다."""
        self.log.debug("최근 접속 로그 조회: limit=%s", limit)
        return await self.repository.get_recent_logs(limit=limit)

    async def get_logs_by_ip(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """IP 주소로 접속 로그를 조회한다."""
        self.log.debug("IP별 접속 로그 조회: ip=%s", ip_address)
        return await self.repository.get_by_ip(ip_address=ip_address, skip=skip, limit=limit)

    async def get_logs_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """사용자 ID로 접속 로그를 조회한다."""
        self.log.debug("사용자별 접속 로그 조회: user_id=%s", user_id)
        return await self.repository.get_by_user_id(user_id=user_id, skip=skip, limit=limit)

    async def get_logs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """날짜 범위로 접속 로그를 조회한다."""
        if start_date > end_date:
            self.log.warning("잘못된 날짜 범위: start=%s end=%s", start_date, end_date)
            raise InvalidDateRangeException(
                detail={"start_date": str(start_date), "end_date": str(end_date)},
            )
        self.log.debug("날짜 범위 접속 로그 조회: %s ~ %s", start_date, end_date)
        return await self.repository.get_by_date_range(
            start_date=start_date, end_date=end_date, skip=skip, limit=limit
        )

    async def get_stats(self) -> AccessLogStats:
        """접속 로그 통계를 조회한다."""
        self.log.debug("접속 로그 통계 조회 시작")
        total_count = await self.repository.count()
        device_counts = await self.repository.count_by_device_type()
        os_counts = await self.repository.count_by_os()
        browser_counts = await self.repository.count_by_browser()
        return AccessLogStats(
            total_count=total_count,
            device_types=[
                DeviceTypeStats(device_type=k, count=v) for k, v in device_counts.items()
            ],
            os_list=[OSStats(os_name=k, count=v) for k, v in os_counts.items()],
            browsers=[BrowserStats(browser_name=k, count=v) for k, v in browser_counts.items()],
        )
