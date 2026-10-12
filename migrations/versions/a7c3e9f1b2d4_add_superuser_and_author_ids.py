"""add users.is_superuser and author_id on blog/sns/reply (service-hardening F2)

Revision ID: a7c3e9f1b2d4
Revises: e5a7c9d1f3b5
Create Date: 2026-10-12 00:00:00.000000

권한 2단계(ADR-016)와 소유권(ADR-015)의 저장소다.

- ``users.is_superuser`` — NOT NULL, 기존 행은 server default 로 false(모두 일반 사용자).
  첫 슈퍼유저는 ``scripts/create_superuser.py`` 로 만든다.
- ``blog_posts``·``sns_posts``·``replies`` 의 ``author_id`` — 작성자 사용자 id(String(36),
  NULL 허용, 인덱스). 기존 행은 작성자를 알 수 없어 NULL 로 두고, NULL 행은 슈퍼유저만
  수정·삭제한다. 사용자 삭제 뒤에도 글은 남기므로 FK 는 걸지 않는다.

리비전은 모델을 import 하지 않고 이 시점의 목록을 고정한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9f1b2d4"
down_revision: str | Sequence[str] | None = "e5a7c9d1f3b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUTHORED_TABLES: tuple[str, ...] = ("blog_posts", "sns_posts", "replies")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for table in _AUTHORED_TABLES:
        op.add_column(table, sa.Column("author_id", sa.String(length=36), nullable=True))
        op.create_index(op.f(f"ix_{table}_author_id"), table, ["author_id"], unique=False)


def downgrade() -> None:
    for table in reversed(_AUTHORED_TABLES):
        op.drop_index(op.f(f"ix_{table}_author_id"), table_name=table)
        op.drop_column(table, "author_id")
    op.drop_column("users", "is_superuser")
