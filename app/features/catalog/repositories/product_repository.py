"""Product Repository.

공통 CRUD 8개는 `BaseRepository` 가 제공한다. 공통으로 표현할 수 없는 조회만
도메인 메서드로 여기에 둔다 — 무엇을 어떤 컬럼으로 찾는지가 이 파일에 드러나야 한다.
"""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repositories.repository_base import BaseRepository
from app.features.catalog.models.models import Product


class ProductRepository(BaseRepository[Product, str]):
    """상품 Repository. PK 는 문자열 UUID 다."""

    model = Product

    async def list_active(self, *, skip: int = 0, limit: int = 100) -> Sequence[Product]:
        """판매 중인 상품만 최신순으로 조회한다."""
        stmt = (
            select(Product)
            .where(Product.is_active.is_(True))
            .order_by(Product.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return (await self.session.execute(stmt)).scalars().all()
