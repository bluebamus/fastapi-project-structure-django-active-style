"""Reports 도메인 데이터베이스 모델.

이 모델은 **집계 결과가 아니라 원본**이다. 일별 매출은 Raw 집계 SQL 로 계산하며
집계 전용 ORM 모델을 두지 않는다 (SCN-RAW-001). 이 클래스가 존재하는 이유는 셋이다.

    1. `sales_orders` 테이블의 스키마 소유권 — Alembic 이 여기서 DDL 을 만든다
    2. `Base.metadata` 등록 — 통합 테스트가 실제 스키마를 세울 수 있게
    3. Admin 이 원본 행을 조회할 수 있게 (읽기 전용 정책, `admin.py` 참고)

주문은 append-only 로 취급하므로 `UpdatedAtMixin` 을 쓰지 않는다 — 갱신 개념이
없는 모델에 수정 시각을 달면 "항상 생성 시각과 같은 컬럼" 이 하나 늘 뿐이다.
"""

from decimal import Decimal

from sqlalchemy import Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import CreatedAtMixin, UUIDPrimaryKeyMixin


class SalesOrder(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """매출 원본 주문.

    Attributes:
        id: UUID 기본키 (mixin)
        order_no: 주문 번호. 운영자가 UUID 대신 사람이 읽는 값으로 찾는다.
        customer_email: 주문자 이메일. **개인 식별자라 Admin list/export 에서 제외한다.**
        total_amount: 주문 총액. 금액이므로 `Numeric` 이다 — 이진 부동소수점은 0.1 을
            정확히 담지 못해 합계에서 오차가 눈에 보이게 쌓인다. 매출 집계가
            SUM 을 쓰므로 특히 그렇다.
        created_at: 주문 시각 (mixin). 일별 집계의 기준 컬럼이다.
    """

    __tablename__ = "sales_orders"
    # 일별 집계 SQL 의 유일한 필터 컬럼이다. 인덱스가 없으면 리포트 한 번이
    # 주문 테이블 전체를 훑는다. created_at 은 mixin 소유라 여기서 인덱스만 건다.
    __table_args__ = (Index("ix_sales_orders_created_at", "created_at"),)

    order_no: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True, comment="주문 번호"
    )
    customer_email: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="주문자 이메일(개인 식별자)"
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, comment="주문 총액"
    )
