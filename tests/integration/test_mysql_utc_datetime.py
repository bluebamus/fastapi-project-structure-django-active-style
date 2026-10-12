"""UTC·마이크로초 저장을 실제 MySQL 8.4 에 대고 확인한다 (service-hardening D1·D2·D3, ADR-007).

SQLite 는 시각을 문자열로 저장해 소수 초·오프셋 문제를 드러내지 않는다. 여기서 보는 것:

1. `UTCDateTime` 이 MySQL 에서 `DATETIME(6)` 으로 왕복한다 — 마이크로초 보존, UTC aware 반환.
2. 리포트의 지역 자정 경계 — 2026-01-01T15:30:00Z 주문은 KST 로 1월 2일 00:30 이므로 1월 2일에 묶인다.
3. 리비전 `e5a7c9d1f3b5` 가 기존 KST 값을 UTC 로 옮기고(upgrade), downgrade 가 되돌린다.
   모든 시각 컬럼의 정밀도가 6 이 된다(Alembic 비교는 인자 수가 다르면 정밀도 차이를 놓친다).
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.features.blog.models.models import Post
from app.features.reports.services.report_service import ReportService
from config import TimezoneSettings, db_settings

from .conftest import SYNC_URL

pytestmark = pytest.mark.mysql

KST = ZoneInfo("Asia/Seoul")
SEOUL = TimezoneSettings(TIME_ZONE="Asia/Seoul")

_PRE_UTC_REVISION = "d4e6f8b12c34"
_UTC_REVISION = "e5a7c9d1f3b5"

_DATETIME_PRECISIONS = sa.text(
    "SELECT TABLE_NAME, COLUMN_NAME, DATETIME_PRECISION FROM information_schema.COLUMNS "
    "WHERE TABLE_SCHEMA = DATABASE() AND DATA_TYPE = 'datetime' "
    "AND TABLE_NAME <> 'alembic_version' ORDER BY TABLE_NAME, COLUMN_NAME"
)


# ------------------------------------------------------------------ 1. 왕복


async def test_datetime_roundtrip_keeps_microseconds_and_utc_on_mysql(mysql_session_maker):
    written = datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST)
    async with mysql_session_maker() as session:
        session.add(Post(id="utc-1", title="t", content="c", created_at=written))
        await session.commit()

    async with mysql_session_maker() as session:
        loaded = (await session.get(Post, "utc-1")).created_at
        raw = (
            await session.execute(sa.text("SELECT created_at FROM blog_posts WHERE id = 'utc-1'"))
        ).scalar_one()

    assert loaded == written
    assert loaded.tzinfo is UTC
    assert loaded.microsecond == 123456
    assert raw == datetime(2026, 1, 1, 15, 30, 0, 123456), "DB 에는 UTC 벽시계가 저장된다"


async def test_metadata_columns_are_datetime_6_on_mysql(mysql_session_maker):
    async with mysql_session_maker() as session:
        rows = (await session.execute(_DATETIME_PRECISIONS)).all()

    assert rows, "시각 컬럼을 찾지 못했다"
    assert {(table, column) for table, column, precision in rows if precision != 6} == set()


# ------------------------------------------------------------------ 2. 지역 자정 경계


_INSERT_ORDER = sa.text(
    "INSERT INTO sales_orders (id, order_no, customer_email, total_amount, created_at) "
    "VALUES (:id, :order_no, 'buyer@example.com', :amount, :created_at)"
)


async def test_order_after_local_midnight_buckets_into_next_local_day_on_mysql(
    mysql_session_maker,
):
    async with mysql_session_maker() as session:
        for order_id, created_at in (
            ("late-utc", datetime(2026, 1, 1, 15, 30, 0)),  # = 2026-01-02 00:30 KST
            ("before-midnight", datetime(2026, 1, 1, 14, 59, 59, 999999)),  # = 01-01 23:59:59 KST
        ):
            await session.execute(
                _INSERT_ORDER,
                {
                    "id": order_id,
                    "order_no": order_id,
                    "amount": Decimal("1.00"),
                    "created_at": created_at,
                },
            )
        await session.commit()

    async with mysql_session_maker() as session:
        service = ReportService(session, SEOUL)
        jan_2 = await service.get_daily_sales(
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 2)
        )
        both = await service.get_daily_sales(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))

    assert [(item.sales_date, item.order_count) for item in jan_2] == [(date(2026, 1, 2), 1)]
    assert [(item.sales_date, item.order_count) for item in both] == [
        (date(2026, 1, 1), 1),
        (date(2026, 1, 2), 1),
    ]


# ------------------------------------------------------------------ 3. 리비전 변환


def _alembic(monkeypatch) -> Config:
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", SYNC_URL)
    return Config("alembic.ini")


def _order_created_at(engine: sa.Engine) -> datetime:
    with engine.connect() as connection:
        return connection.execute(
            sa.text("SELECT created_at FROM sales_orders WHERE id = 'seed-1'")
        ).scalar_one()


def _precisions(engine: sa.Engine) -> set[int]:
    with engine.connect() as connection:
        return {precision for _, _, precision in connection.execute(_DATETIME_PRECISIONS)}


def test_utc_revision_converts_kst_values_and_downgrade_restores_on_mysql(
    mysql_empty_schema, monkeypatch
):
    config = _alembic(monkeypatch)
    command.upgrade(config, _PRE_UTC_REVISION)

    engine = sa.create_engine(SYNC_URL)
    try:
        # 이전 형식: KST 벽시계, 소수 초 없음. raw SQL 로 넣어 앱 타입을 거치지 않는다.
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO sales_orders "
                    "(id, order_no, customer_email, total_amount, created_at) "
                    "VALUES ('seed-1', 'SEED-1', 'buyer@example.com', 1.00, "
                    "'2026-01-02 00:30:00')"
                )
            )
        assert _precisions(engine) == {0}

        command.upgrade(config, _UTC_REVISION)
        assert _order_created_at(engine) == datetime(2026, 1, 1, 15, 30, 0)
        assert _precisions(engine) == {6}

        command.downgrade(config, _PRE_UTC_REVISION)
        assert _order_created_at(engine) == datetime(2026, 1, 2, 0, 30, 0)
        assert _precisions(engine) == {0}
    finally:
        engine.dispose()
