"""Reports 기능 의존성 (인터페이스 집합체).

Dependency 는 **조립만 한다** — commit 하지 않고 Service 메서드를 미리 실행하지도
않는다 (ADR-004).

리포트는 조회 전용이라 read-only Dependency 하나만 둔다. Raw SQL 이라는 이유로 쓰기
세션을 쓰지 않는다 — Raw 는 접근 방식이지 권한이 아니다. read-only 세션은
`DB_ROUTER_ENABLED` 와 무관하게 쓰기를 거부한다(INV-4).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    """조회 엔드포인트용 — 쓰기를 시도하면 실패한다."""
    return ReportService(session)
