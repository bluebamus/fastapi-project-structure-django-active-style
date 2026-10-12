"""store datetimes as UTC with microseconds (service-hardening D2)

Revision ID: e5a7c9d1f3b5
Revises: d4e6f8b12c34
Create Date: 2026-10-12 00:00:00.000000

모든 시각 컬럼을 MySQL `DATETIME(6)` 으로 넓히고, 기존 값을 KST 벽시계에서 UTC 로 옮긴다
(ADR-007). 앱은 이제 `UTCDateTime` 으로 UTC 를 저장하므로, 옮기지 않은 기존 행은 9시간 미래로
읽힌다.

가정: 기존 값은 모두 `Asia/Seoul` 벽시계다(이전 기본 `TIME_ZONE` 이고 모델 default 가
`timezone_settings.now()` 였다). Asia/Seoul 은 1988년 이후 DST 가 없어 고정 오프셋 `+09:00` 으로
옮겨도 정확하다 — 숫자 오프셋의 `CONVERT_TZ` 는 MySQL 타임존 테이블이 없어도 동작한다.
다른 `TIME_ZONE` 으로 운영하던 DB 는 이 리비전을 적용하기 전에 오프셋을 그 지역 값으로 바꿔야 한다.

SQLite(로컬·단위 테스트)는 형식 변화가 없고 시험용 데이터만 담으므로 no-op 이다. 방언은
`op.get_context().dialect` 로 본다 — `op.get_bind()` 는 오프라인(--sql) 모드에서 연결이 없다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "e5a7c9d1f3b5"
down_revision: str | Sequence[str] | None = "d4e6f8b12c34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (테이블, 컬럼) — 모두 NOT NULL 이다. 리비전은 모델을 import 하지 않고 이 시점의 목록을 고정한다.
_COLUMNS: tuple[tuple[str, str], ...] = (
    ("user_access_logs", "created_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("blog_posts", "created_at"),
    ("blog_posts", "updated_at"),
    ("replies", "created_at"),
    ("replies", "updated_at"),
    ("sns_posts", "created_at"),
    ("sns_posts", "updated_at"),
    ("catalog_products", "created_at"),
    ("catalog_products", "updated_at"),
    ("sales_orders", "created_at"),
)

_LOCAL_OFFSET = "+09:00"  # Asia/Seoul, DST 없음 — 위 모듈 설명의 가정


def _convert(table: str, column: str, source: str, target: str) -> None:
    """`UPDATE table SET column = CONVERT_TZ(column, source, target)` — Core 구성으로 만든다."""
    target_column = sa.column(column)
    op.execute(
        sa.table(table, target_column)
        .update()
        .values({column: sa.func.convert_tz(target_column, source, target)})
    )


def upgrade() -> None:
    """Upgrade schema — DATETIME(6) 으로 넓힌 뒤 KST → UTC."""
    if op.get_context().dialect.name != "mysql":
        return
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=mysql.DATETIME(fsp=6),
            existing_type=mysql.DATETIME(),
            existing_nullable=False,
        )
        _convert(table, column, _LOCAL_OFFSET, "+00:00")


def downgrade() -> None:
    """Downgrade schema — UTC → KST 로 되돌린 뒤 DATETIME 으로 좁힌다.

    좁힐 때 소수 초는 MySQL 이 반올림한다(되돌리기 전 형식에는 소수 초가 없었다).
    """
    if op.get_context().dialect.name != "mysql":
        return
    for table, column in _COLUMNS:
        _convert(table, column, "+00:00", _LOCAL_OFFSET)
        op.alter_column(
            table,
            column,
            type_=mysql.DATETIME(),
            existing_type=mysql.DATETIME(fsp=6),
            existing_nullable=False,
        )
