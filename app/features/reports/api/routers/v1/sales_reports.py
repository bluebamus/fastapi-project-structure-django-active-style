"""Reports v1 API 엔드포인트 — 일별 매출 리포트.

조회이므로 commit 하지 않는다. Raw SQL 이라는 이유로 쓰기 세션을 쓰지 않는다.

View 는 HTTP 역할만 한다: 파라미터 수신 → Service 호출 → 응답 변환. 기간 검증도
SQL 도 여기 없다.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.exception import ErrorResponse
from app.features.reports.dependencies.report_dependencies import get_report_service_readonly
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

router = APIRouter()

_INVALID_RANGE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "종료일이 시작일보다 빠름"}
}


@router.get(
    "/sales/daily",
    response_model=DailySalesReportResponse,
    responses=_INVALID_RANGE,
    summary="일별 매출 리포트",
    description=(
        "지정한 기간의 주문 수와 총 매출을 일별로 집계합니다. "
        "시작일과 종료일은 모두 포함하며, 주문이 없는 날은 결과에 포함되지 않습니다."
    ),
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(description="조회 시작일(포함)", examples=["2026-08-01"]),
    end_date: date = Query(description="조회 종료일(포함)", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(start_date=start_date, end_date=end_date)
    return DailySalesReportResponse(start_date=start_date, end_date=end_date, items=items)
