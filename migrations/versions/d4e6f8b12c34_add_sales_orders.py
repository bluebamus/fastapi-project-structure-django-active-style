"""add sales_orders (Phase 8 Raw 예제)

Revision ID: d4e6f8b12c34
Revises: c3d5e7a91b02
Create Date: 2026-08-19 00:00:00.000000

집계 결과가 아니라 **원본** 테이블이다. 일별 매출은 Raw 집계 SQL 이 이 테이블 위에서
계산하며 집계 전용 테이블을 따로 두지 않는다.

기존 revision 은 재작성하지 않고 새 revision 을 덧붙인다. downgrade 도 구현해 두며,
MySQL 에서 head -> down_revision -> head 왕복이 실제로 도는지 통합 테스트가 확인한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e6f8b12c34"
down_revision: str | Sequence[str] | None = "c3d5e7a91b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — 매출 원본 주문 테이블을 만든다."""
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False, comment="주문 번호"),
        sa.Column(
            "customer_email",
            sa.String(length=255),
            nullable=False,
            comment="주문자 이메일(개인 식별자)",
        ),
        # 금액은 Numeric 이다. 집계가 SUM 을 쓰므로 부동소수점 오차가 그대로 누적된다.
        sa.Column(
            "total_amount", sa.Numeric(precision=12, scale=2), nullable=False, comment="주문 총액"
        ),
        # 일별 집계의 기준 컬럼. 조회 조건이므로 인덱스를 둔다.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_orders_order_no", "sales_orders", ["order_no"], unique=True)
    op.create_index("ix_sales_orders_created_at", "sales_orders", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sales_orders_created_at", table_name="sales_orders")
    op.drop_index("ix_sales_orders_order_no", table_name="sales_orders")
    op.drop_table("sales_orders")
