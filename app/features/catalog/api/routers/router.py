"""Catalog 모듈 라우터 — v1 프리픽스로 Catalog 엔드포인트를 통합한다.

컨벤션: `AppRegistry` 가 이 모듈의 `catalog_router` 를 발견해 `/api` 에 마운트한다.
이 기능을 붙이려고 `main.py` 나 중앙 목록을 고치지 않는다 (C-1).
"""

from fastapi import APIRouter

from app.features.catalog.api.routers.v1 import products as products_v1

catalog_router = APIRouter()

catalog_router.include_router(
    products_v1.router,
    prefix="/v1/catalog",
    tags=["Catalog"],
)
