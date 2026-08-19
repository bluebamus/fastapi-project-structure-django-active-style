"""Catalog 기능 의존성 (인터페이스 집합체).

Dependency 는 **조립만 한다** — commit 하지 않고 Service 메서드를 미리 실행하지도
않는다. 커밋은 쓰기 핸들러 본문이 `await service.commit()` 으로 수행한다(ADR-004).

조회는 read-only, 변경은 writer Dependency 를 쓴다. 쓰기용을 조회에 재사용하면
조회마다 불필요한 COMMIT 왕복이 생기고 한 세션에 커밋 주체가 둘이 될 수 있다.
read-only 세션은 `DB_ROUTER_ENABLED` 와 무관하게 쓰기를 거부한다(INV-4).
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.catalog.services.catalog_service import CatalogService


async def get_catalog_service(
    session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    """변경 엔드포인트용 — 첫 쿼리부터 writer 에 고정된다."""
    return CatalogService(session)


async def get_catalog_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    """조회 엔드포인트용 — 쓰기를 시도하면 실패한다."""
    return CatalogService(session)
