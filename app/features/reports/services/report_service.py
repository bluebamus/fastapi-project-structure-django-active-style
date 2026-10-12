"""Reports 유스케이스.

기간 규칙은 **비즈니스 규칙이라 여기 있다**. SQL 에 넣으면 잘못된 기간이 조용히 빈
결과가 되고, View 에 넣으면 다른 진입점(배치·Celery)이 같은 규칙을 다시 써야 한다.

Raw 행을 DTO 로 바꾸는 경계도 여기다 (RAW-REP-005). Repository 는 `RowMapping` 까지만
돌려주고 View 는 DTO 만 본다 — `RowMapping` 이 View 까지 올라가면 SQL 컬럼 변경이
곧바로 응답 계약 변경이 된다.

날짜는 설정 `TIME_ZONE` 의 영업일이다(ADR-007). DB 는 UTC 순간을 저장하므로, 지역 날짜 범위를
UTC 경계와 지역 오프셋으로 바꾸는 일도 기간 규칙의 일부로 여기서 한다. 시간대는 생성자로 받는다
(기본은 전역 설정) — 테스트가 다른 지역을 넣어 경계를 확인한다.

조회이므로 commit 하지 않는다.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.reports.schemas.report_schema import DailySalesItem
from config import TimezoneSettings, timezone_settings

# 한 번에 집계할 수 있는 최대 일수(양 끝 포함). 윤년 1년치까지 — 그보다 긴 기간은
# 일별 집계가 아니라 배치·월별 집계의 일이고, 과대 스캔이 replica 를 붙잡는다.
MAX_REPORT_DAYS = 366
# 경계 계산이 `end_date + 1일` 을 하므로 9999-12-31 은 넘친다(date 범위 밖 → OverflowError).
MIN_REPORT_DATE = date(1970, 1, 1)
MAX_REPORT_DATE = date(9998, 12, 31)


class ReportService(BaseService):
    """매출 리포트 유스케이스."""

    def __init__(
        self, session: AsyncSession, timezone: TimezoneSettings = timezone_settings
    ) -> None:
        super().__init__(session)
        self.repository = SalesReportRawRepository(session)
        self.timezone = timezone

    async def get_daily_sales(self, *, start_date: date, end_date: date) -> list[DailySalesItem]:
        """기간 내 일별 매출을 집계한다.

        Raises:
            InvalidDateRangeException: 종료일이 시작일보다 빠르거나, 날짜가 허용 범위
                (1970-01-01~9998-12-31) 밖이거나, 기간이 366일을 넘을 때.
        """
        detail = {"start_date": str(start_date), "end_date": str(end_date)}
        if end_date < start_date:
            raise InvalidDateRangeException(detail=detail)
        if start_date < MIN_REPORT_DATE or end_date > MAX_REPORT_DATE:
            raise InvalidDateRangeException(
                message=f"날짜는 {MIN_REPORT_DATE}~{MAX_REPORT_DATE} 범위여야 합니다.",
                detail=detail,
            )
        if (end_date - start_date).days + 1 > MAX_REPORT_DAYS:
            raise InvalidDateRangeException(
                message=f"조회 기간은 최대 {MAX_REPORT_DAYS}일입니다.",
                detail=detail,
            )

        self.log.debug("일별 매출 집계 %s~%s", start_date, end_date)
        start_at, end_at = self.timezone.local_dates_to_utc(start_date, end_date)
        rows = await self.repository.daily_sales(
            start_at=start_at,
            end_at=end_at,
            tz_offset=self.timezone.utc_offset(start_at),
        )
        return [DailySalesItem.model_validate(dict(row)) for row in rows]
