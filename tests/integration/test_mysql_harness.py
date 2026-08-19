"""MySQL 8.4 통합 smoke (계획서 §10 Phase 5).

이 단계의 범위는 **인프라가 실제로 선다**는 것까지다. Raw SQL 계약은 Phase 6,
예제 기능은 Phase 7~8 에서 이 하네스 위에 쌓인다.

여기서 확인하는 것:
  1. 컨테이너가 실제로 MySQL 8.x 로 응답한다 (SQLite 로 착각하고 통과하지 않는다)
  2. runtime 과 같은 registry metadata 로 MySQL 에 스키마가 선다
  3. 기존 Alembic chain 이 MySQL 에서 head 까지 올라가고, base 로 내려갔다가,
     다시 head 로 올라온다 (upgrade / downgrade / re-upgrade)

3번이 이 단계의 핵심이다. SQLite 에서만 돌던 체인은 MySQL 방언(ALTER 제약, 인덱스
이름 길이, FK 순서)에서 처음 깨지는 경우가 많고, downgrade 는 거의 아무도 실행해
보지 않은 채 배포에 들어간다.
"""

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from config import db_settings

from .conftest import SYNC_URL, populate_metadata

pytestmark = pytest.mark.mysql

_EXPECTED_TABLES = {
    "user_access_logs",
    "users",
    "blog_posts",
    "replies",
    "sns_posts",
}


def _alembic_on_mysql(monkeypatch) -> Config:
    """Alembic 이 테스트 MySQL 을 향하게 한다.

    env.py 가 `db_settings.ALEMBIC_URL` 을 읽고, 그 값은
    `ALEMBIC_DATABASE_URL` 오버라이드에서 온다 — 단위 테스트와 같은 경로다.
    """
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", SYNC_URL)
    return Config("alembic.ini")


@pytest.mark.asyncio
async def test_mysql_dialect_is_really_mysql(mysql_session_maker):
    """SQLite 로 착각하고 초록을 받지 않도록 서버 정체를 확인한다."""
    async with mysql_session_maker() as session:
        version = (await session.execute(sa.text("SELECT VERSION()"))).scalar_one()
        dialect = session.bind.dialect.name

    assert dialect == "mysql", f"방언이 mysql 이 아닙니다: {dialect}"
    assert version.startswith("8."), f"MySQL 8.x 가 아닙니다: {version}"


@pytest.mark.asyncio
async def test_registry_metadata_creates_schema_on_mysql(mysql_session_maker):
    """runtime 과 같은 registry 결과로 MySQL 에 스키마가 선다."""
    async with mysql_session_maker() as session:
        rows = (await session.execute(sa.text("SHOW TABLES"))).scalars().all()

    missing = _EXPECTED_TABLES - set(rows)
    assert not missing, f"MySQL 에 생성되지 않은 테이블: {sorted(missing)}"


def test_alembic_chain_upgrades_on_mysql(mysql_empty_schema, monkeypatch):
    """빈 MySQL 에서 head 까지 올라간다."""
    config = _alembic_on_mysql(monkeypatch)

    command.upgrade(config, "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"마이그레이션이 생성하지 않은 테이블: {sorted(missing)}"
    assert "alembic_version" in tables


def test_alembic_chain_downgrades_and_re_upgrades_on_mysql(mysql_empty_schema, monkeypatch):
    """head -> base -> head 가 MySQL 에서 모두 성공한다.

    downgrade 는 실행해 보지 않은 채 배포되는 일이 흔하다. 롤백 경로가 실제로
    도는지 여기서 확인한다.
    """
    config = _alembic_on_mysql(monkeypatch)

    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = sa.create_engine(SYNC_URL)
    try:
        after_downgrade = set(sa.inspect(engine).get_table_names())
        assert not (
            _EXPECTED_TABLES & after_downgrade
        ), f"downgrade 후에도 남은 테이블: {sorted(_EXPECTED_TABLES & after_downgrade)}"

        command.upgrade(config, "head")
        after_reupgrade = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    missing = _EXPECTED_TABLES - after_reupgrade
    assert not missing, f"재적용 후 없는 테이블: {sorted(missing)}"


def test_migrated_schema_matches_models_on_mysql(mysql_empty_schema, monkeypatch):
    """MySQL 에 적용된 결과가 모델 metadata 와 일치한다(방언 드리프트 없음)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.core.db.session import Base

    populate_metadata()
    command.upgrade(_alembic_on_mysql(monkeypatch), "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        with engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()

    assert not diff, f"MySQL 스키마와 모델이 어긋납니다: {diff}"
