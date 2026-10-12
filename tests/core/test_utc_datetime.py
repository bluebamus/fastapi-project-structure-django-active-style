"""시각은 UTC·마이크로초로 저장하고 UTC aware 로 돌려준다 (service-hardening D1·D4, ADR-007).

`DateTime(timezone=True)` 는 MySQL 에서 오프셋과 소수 초를 잃었다. 여기서는 그 대체인
`UTCDateTime` 의 bind/result 규칙, SQLite 왕복, 모델 기본값, Alembic 렌더, API 응답의 오프셋을
고정한다. MySQL `DATETIME(6)` 왕복은 `tests/integration/test_mysql_utc_datetime.py` 가 본다.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.migration import MigrationContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db.models_registry import import_all_models
from app.core.models.models_base import Base
from app.core.models.types import UTCDateTime, render_alembic_type
from app.features.blog.models.models import Post
from config import TimezoneSettings
from main import app
from tests.auth_headers import user_headers
from tests.session_overrides import session_overrides

KST = ZoneInfo("Asia/Seoul")
REPO_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ TypeDecorator 단위


def test_bind_converts_aware_local_time_to_utc_naive():
    stored = UTCDateTime().process_bind_param(
        datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST), sqlite.dialect()
    )

    assert stored == datetime(2026, 1, 1, 15, 30, 0, 123456)
    assert stored.tzinfo is None


def test_bind_rejects_naive_datetime():
    """naive 값은 어느 지역 벽시계인지 알 수 없다 — 조용히 받지 않는다."""
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 2, 0, 30), sqlite.dialect())


def test_result_attaches_utc():
    loaded = UTCDateTime().process_result_value(datetime(2026, 1, 1, 15, 30), sqlite.dialect())

    assert loaded == datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
    assert loaded.tzinfo is UTC


def test_none_passes_through_both_ways():
    column_type = UTCDateTime()

    assert column_type.process_bind_param(None, sqlite.dialect()) is None
    assert column_type.process_result_value(None, sqlite.dialect()) is None


def test_mysql_column_keeps_microseconds():
    """MySQL 은 DATETIME(6) — 기본 DATETIME 은 소수 초를 반올림해 일별 집계 경계를 바꾼다."""
    assert UTCDateTime().compile(dialect=mysql.dialect()) == "DATETIME(6)"
    assert UTCDateTime().compile(dialect=sqlite.dialect()) == "DATETIME"


def test_every_datetime_column_uses_utc_type():
    """`Mapped[datetime]` 은 type_annotation_map 으로 모두 UTCDateTime 이 된다."""
    import_all_models()
    datetime_columns = {
        f"{table.name}.{column.name}": column.type
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, sa.DateTime | UTCDateTime)
    }

    assert datetime_columns, "시각 컬럼을 하나도 찾지 못했다"
    assert {
        name: type(column_type).__name__
        for name, column_type in datetime_columns.items()
        if not isinstance(column_type, UTCDateTime)
    } == {}


# ------------------------------------------------------------------ 시각 생성 단일 지점


def test_utc_now_is_aware_utc():
    now = TimezoneSettings(TIME_ZONE="Asia/Seoul").utc_now()

    assert now.utcoffset() == UTC.utcoffset(None)


def test_local_dates_to_utc_is_half_open_local_days():
    lower, upper = TimezoneSettings(TIME_ZONE="Asia/Seoul").local_dates_to_utc(
        date(2026, 1, 2), date(2026, 1, 3)
    )

    assert (lower, upper) == (
        datetime(2026, 1, 1, 15, 0, tzinfo=UTC),
        datetime(2026, 1, 3, 15, 0, tzinfo=UTC),
    )


# ------------------------------------------------------------------ SQLite 왕복·모델 기본값


@pytest.fixture
def sync_session():
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Post.__table__])
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_sqlite_roundtrip_keeps_microseconds_and_returns_utc(sync_session):
    written = datetime(2026, 1, 2, 0, 30, 0, 654321, tzinfo=KST)
    sync_session.add(Post(id="p1", title="t", content="c", created_at=written))
    sync_session.commit()
    sync_session.expire_all()

    loaded = sync_session.get(Post, "p1").created_at

    assert loaded == written  # 같은 순간
    assert loaded.tzinfo is UTC
    assert loaded.microsecond == 654321
    raw = sync_session.execute(sa.text("SELECT created_at FROM blog_posts")).scalar_one()
    assert str(raw).startswith("2026-01-01 15:30:00.654321"), "DB 에는 UTC 벽시계가 저장된다"


def test_naive_value_is_rejected_on_flush(sync_session):
    sync_session.add(Post(id="p2", title="t", content="c", created_at=datetime(2026, 1, 2)))

    with pytest.raises(StatementError, match="naive"):
        sync_session.flush()


def test_model_default_is_aware_utc(sync_session):
    sync_session.add(Post(id="p3", title="t", content="c"))
    sync_session.commit()
    sync_session.expire_all()

    post = sync_session.get(Post, "p3")

    assert post.created_at.tzinfo is UTC
    assert post.updated_at.tzinfo is UTC
    assert abs((datetime.now(UTC) - post.created_at).total_seconds()) < 60


def test_model_default_uses_utc_now_not_local_now(monkeypatch):
    """기본값의 시각 출처는 `utc_now()` 하나다 — 지역 `now()` 로 되돌아가지 않는다."""
    marker = datetime(2001, 2, 3, 4, 5, 6, tzinfo=UTC)
    monkeypatch.setattr(TimezoneSettings, "utc_now", lambda self: marker)
    monkeypatch.setattr(TimezoneSettings, "now", lambda self: datetime(1999, 1, 1, tzinfo=KST))
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Post.__table__])
    try:
        with Session(engine) as session:
            session.add(Post(id="p4", title="t", content="c"))
            session.commit()
            session.expire_all()
            post = session.get(Post, "p4")
            assert (post.created_at, post.updated_at) == (marker, marker)
    finally:
        engine.dispose()


# ------------------------------------------------------------------ Alembic


def test_autogenerate_renders_the_underlying_type():
    """리비전은 앱 클래스가 아니라 밑바탕 타입을 적는다 — 과거 리비전이 앱 코드에 묶이지 않는다."""
    engine = sa.create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"target_metadata": Base.metadata}
            )
            script = produce_migrations(context, Base.metadata)
    finally:
        engine.dispose()

    code = render_python_code(script.upgrade_ops, render_item=render_alembic_type)

    assert 'sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")' in code
    assert "UTCDateTime" not in code


def test_alembic_env_uses_the_render_hook_in_both_modes():
    source = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert source.count("render_item=render_alembic_type") == 2


# ------------------------------------------------------------------ API 응답


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides.update(
        session_overrides(async_sessionmaker(engine, expire_on_commit=False))
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=user_headers()
    ) as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def _is_utc_iso(value: str) -> bool:
    return (value.endswith("Z") or value.endswith("+00:00")) and datetime.fromisoformat(
        value
    ).utcoffset() == UTC.utcoffset(None)


async def test_api_response_carries_utc_offset(client):
    created = await client.post("/api/v1/blog/posts", json={"title": "t", "content": "c"})
    fetched = await client.get(f"/api/v1/blog/posts/{created.json()['id']}")

    for body in (created.json(), fetched.json()):
        assert _is_utc_iso(body["created_at"]), body["created_at"]
        assert _is_utc_iso(body["updated_at"]), body["updated_at"]
