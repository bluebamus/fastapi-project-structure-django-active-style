"""add catalog_products (Phase 7 ORM 예제)

Revision ID: c3d5e7a91b02
Revises: b2f1a9c0d3e4
Create Date: 2026-08-19 00:00:00.000000

기존 revision 은 재작성하지 않고 새 revision 을 덧붙인다. downgrade 도 구현해 두며,
MySQL 에서 head -> down_revision -> head 왕복이 실제로 도는지 통합 테스트가 확인한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d5e7a91b02"
down_revision: str | Sequence[str] | None = "b2f1a9c0d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — 상품 테이블을 만든다."""
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False, comment="상품명"),
        # 금액은 Numeric 이다. 이진 부동소수점은 0.1 을 정확히 담지 못해 합계에서
        # 오차가 눈에 보이게 쌓인다.
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False, comment="판매가"),
        sa.Column("is_active", sa.Boolean(), nullable=False, comment="판매 활성 여부"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("catalog_products")
