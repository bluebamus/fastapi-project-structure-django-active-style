"""Alembic baseline 이 모델 스키마를 그대로 만들고 깨끗이 되돌리는지 확인한다.

운영(DEBUG=false)에서는 Alembic 이 유일한 스키마 경로다. 빈 SQLite 에서 autogenerate 가 시각 컬럼을
MySQL `DATETIME(6)` variant 로 렌더하는지, `upgrade head` 결과가 `Base.metadata` 와 같은지(diff 없음),
`downgrade base` 뒤 테이블이 남지 않는지 본다.
"""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata, produce_migrations, render_python_code
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.models.types import render_alembic_type
from config import db_settings


def test_upgrade_matches_models_and_downgrade_is_clean(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    # env.py 는 db_settings.ALEMBIC_URL 을 읽는다 — 이 필드가 대상 DB 를 정한다.
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", url)
    config = Config("alembic.ini")
    import_all_models()
    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            script = produce_migrations(MigrationContext.configure(conn), Base.metadata)
        rendered = render_python_code(script.upgrade_ops, render_item=render_alembic_type)
        assert 'sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")' in rendered
        assert "UTCDateTime" not in rendered

        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert set(sa.inspect(conn).get_table_names()) >= set(Base.metadata.tables)
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"

        command.downgrade(config, "base")
        with engine.connect() as conn:
            assert set(sa.inspect(conn).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()
