"""Catalog 유스케이스.

가격 정책·상태 전환·중복 판정 같은 규칙이 있다면 이 계층에 둔다. 지금은 최소 CRUD 를
Repository 에 위임하는 얇은 계층이다 — 비어 있는 것이 정상이며, 규칙이 생기면 여기에
쌓인다(View 나 Repository 로 새어나가지 않게).

commit 은 여기서 하지 않는다. 트랜잭션 경계는 쓰기 View 가 응답 직전에 한 번 닫는다(ADR-004).
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate, ProductUpdate


class CatalogService(BaseService):
    """상품 유스케이스."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = ProductRepository(session)

    async def create_product(self, payload: ProductCreate) -> Product:
        self.log.debug("상품 생성")
        return await self.repository.create(payload.model_dump())

    async def list_products(self, *, skip: int, limit: int) -> tuple[Sequence[Product], int]:
        """목록과 전체 개수를 함께 돌려준다(페이지네이션 응답에 둘 다 필요하다)."""
        items = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return items, total

    async def get_product(self, product_id: str) -> Product | None:
        return await self.repository.get_by_id(product_id)

    async def update_product(self, product_id: str, payload: ProductUpdate) -> Product | None:
        """제공된 필드만 반영한다.

        `exclude_unset` 이라 "명시적으로 null 을 보냄" 과 "필드를 안 보냄" 이 구분된다.
        아무 필드도 안 보낸 PATCH 는 Repository 에서 존재 확인 후 no-op 이 된다.
        """
        return await self.repository.update(product_id, payload.model_dump(exclude_unset=True))

    async def delete_product(self, product_id: str) -> bool:
        return await self.repository.delete(product_id)
