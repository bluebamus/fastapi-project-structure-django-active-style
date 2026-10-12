"""리비전 a7c3e9f1b2d4 를 실제 MySQL 8.4 에 대고 확인한다 (service-hardening F2, ADR-015·ADR-016).

- upgrade: ``users.is_superuser``(NOT NULL, 기존 행 false)와 blog·sns·reply 의 ``author_id``
  (VARCHAR(36) NULL + 인덱스)가 생긴다.
- downgrade: 같은 컬럼·인덱스가 사라진다.
"""

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from config import db_settings

from .conftest import SYNC_URL

pytestmark = pytest.mark.mysql

_BEFORE = "e5a7c9d1f3b5"
_REVISION = "a7c3e9f1b2d4"
_AUTHORED_TABLES = ("blog_posts", "sns_posts", "replies")

_COLUMNS = sa.text(
    "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA = DATABASE() AND "
    "((TABLE_NAME = 'users' AND COLUMN_NAME = 'is_superuser') OR COLUMN_NAME = 'author_id') "
    "ORDER BY TABLE_NAME"
)
_INDEXED = sa.text(
    "SELECT DISTINCT TABLE_NAME FROM information_schema.STATISTICS "
    "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME = 'author_id' ORDER BY TABLE_NAME"
)


def _state(engine: sa.Engine) -> tuple[list[tuple], list[str]]:
    with engine.connect() as connection:
        columns = [tuple(row) for row in connection.execute(_COLUMNS)]
        indexed = [row[0] for row in connection.execute(_INDEXED)]
    return columns, indexed


def test_authorization_revision_adds_and_removes_columns_on_mysql(mysql_empty_schema, monkeypatch):
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", SYNC_URL)
    config = Config("alembic.ini")
    command.upgrade(config, _BEFORE)

    engine = sa.create_engine(SYNC_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, username, email, is_active, created_at, updated_at) "
                    "VALUES ('u1', 'old', 'old@example.com', 1, "
                    "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                )
            )

        command.upgrade(config, _REVISION)
        columns, indexed = _state(engine)
        assert columns == [
            ("blog_posts", "author_id", "varchar(36)", "YES"),
            ("replies", "author_id", "varchar(36)", "YES"),
            ("sns_posts", "author_id", "varchar(36)", "YES"),
            ("users", "is_superuser", "tinyint(1)", "NO"),
        ]
        assert indexed == sorted(_AUTHORED_TABLES)
        with engine.connect() as connection:
            existing = connection.execute(sa.text("SELECT is_superuser FROM users WHERE id = 'u1'"))
            assert existing.scalar_one() == 0

        command.downgrade(config, _BEFORE)
        assert _state(engine) == ([], [])
    finally:
        engine.dispose()
