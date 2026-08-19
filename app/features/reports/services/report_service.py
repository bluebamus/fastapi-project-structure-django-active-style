"""Reports 유스케이스.

기간 규칙은 **비즈니스 규칙이라 여기 있다**. SQL 에 넣으면 잘못된 기간이 조용히 빈
결과가 되고, View 에 넣으면 다른 진입점(배치·Celery)이 같은 규칙을 다시 써야 한다.

Raw 행을 DTO 로 바꾸는 경계도 여기다 (RAW-REP-005). Repository 는 `RowMapping` 까지만
돌려주고 View 는 DTO 만 본다 — `RowMapping` 이 View 까지 올라가면 SQL 컬럼 변경이
곧바로 응답 계약 변경이 된다.

조회이므로 commit 하지 않는다.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.reports.schemas.report_schema import DailySalesItem


class ReportService(BaseService):
    """매출 리포트 유스케이스."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = SalesReportRawRepository(session)

    async def get_daily_sales(self, *, start_date: date, end_date: date) -> list[DailySalesItem]:
        """기간 내 일별 매출을 집계한다.

        Raises:
            InvalidDateRangeException: 종료일이 시작일보다 빠를 때.
        """
        if end_date < start_date:
            raise InvalidDateRangeException(
                detail={"start_date": str(start_date), "end_date": str(end_date)}
            )

        self.log.debug("일별 매출 집계 %s~%s", start_date, end_date)
        rows = await self.repository.daily_sales(start_date=start_date, end_date=end_date)
        return [DailySalesItem.model_validate(dict(row)) for row in rows]
