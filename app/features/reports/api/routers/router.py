"""Reports 모듈 라우터 — v1 프리픽스로 Reports 엔드포인트를 통합한다.

컨벤션: `AppRegistry` 가 이 모듈의 `reports_router` 를 발견해 `/api` 에 마운트한다.
이 기능을 붙이려고 `main.py` 나 중앙 목록을 고치지 않는다 (C-1).
"""

from fastapi import APIRouter

from app.features.reports.api.routers.v1 import sales_reports as sales_reports_v1

reports_router = APIRouter()

reports_router.include_router(
    sales_reports_v1.router,
    prefix="/v1/reports",
    tags=["Reports"],
)
