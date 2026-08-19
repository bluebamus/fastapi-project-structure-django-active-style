"""Catalog 도메인 데이터베이스 모델.

상품(Product) 엔티티를 정의한다. 공통 PK·시간 컬럼은 각자 복사하지 않고 프로젝트
mixin 에서 받는다(INV-13) — 상품은 갱신되는 엔티티이므로 `UpdatedAtMixin` 도 함께 쓴다.
"""

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class Product(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """판매 상품.

    Attributes:
        id: UUID 기본키 (mixin)
        name: 상품명
        price: 판매가. 금액이라 float 이 아니라 `Numeric` 이다 — 이진 부동소수점은
            0.1 을 정확히 담지 못해 합계에서 오차가 눈에 보이게 쌓인다.
        is_active: 판매 활성 여부
        created_at / updated_at: 생성·수정 시각 (mixin)
    """

    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="상품명")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="판매가")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="판매 활성 여부"
    )
