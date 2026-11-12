"""MySQL 에서만 드러나는 동작 — SQLite 통과로는 증명되지 않는 것만 둔다.

CI 의 `mysql` 잡이 MySQL 8.4 서비스 컨테이너로 돌린다. 각 테스트는 자기 DB 를 만들고 지운다
(`conftest.py`).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.models_registry import import_all_models
from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
)
from app.core.db.session import ENGINE_SAFETY_OPTIONS, Base
from app.core.exception import DuplicateException, ValidationException
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.user.repositories.user_repository import UserRepository
from config import TimezoneSettings, db_settings

KST = ZoneInfo("Asia/Seoul")


def _order(order_no: str, created_at: datetime, amount: str = "10.00") -> SalesOrder:
    return SalesOrder(
        order_no=order_no,
        customer_email=f"{order_no}@ex.com",
        total_amount=Decimal(amount),
        created_at=created_at,
    )


# ------------------------------------------------------------------ 1. 마이그레이션


def test_baseline_migration_matches_models_on_mysql_and_downgrades_clean(mysql_url, monkeypatch):
    """빈 MySQL 에 `upgrade head` → 모델과 autogenerate diff 없음 → `downgrade base` 후 테이블 없음."""
    # env.py 는 db_settings.ALEMBIC_URL 을 읽는다 — 이 필드가 대상 DB 를 정한다.
    sync = mysql_url.set(drivername="mysql+pymysql")
    monkeypatch.setattr(
        db_settings, "ALEMBIC_DATABASE_URL", sync.render_as_string(hide_password=False)
    )
    config = Config("alembic.ini")
    import_all_models()
    engine = sa.create_engine(sync, **ENGINE_SAFETY_OPTIONS)
    try:
        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert set(sa.inspect(conn).get_table_names()) >= set(Base.metadata.tables)
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"MySQL 에서 마이그레이션 결과와 모델이 다르다: {diff}"

        command.downgrade(config, "base")
        with engine.connect() as conn:
            assert set(sa.inspect(conn).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()


# ------------------------------------------------------------------ 2. 시각 컬럼


async def test_utc_datetime_round_trips_microseconds_as_utc(mysql_engine):
    """`UTCDateTime` 은 MySQL 에서 DATETIME(6) — 지역 aware 값을 넣으면 같은 순간이 UTC 로, 마이크로초까지 돌아온다."""
    written = datetime(2026, 8, 1, 23, 59, 59, 123456, tzinfo=KST)
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with maker() as session:
        session.add(_order("RT-1", written))
        await session.commit()
    async with maker() as session:
        read = await session.scalar(sa.select(SalesOrder.created_at))
        precision = await session.scalar(
            sa.text(
                "SELECT DATETIME_PRECISION FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sales_orders' "
                "AND COLUMN_NAME = 'created_at'"
            )
        )

    assert precision == 6
    assert read == written
    assert read.tzinfo is UTC
    assert read.microsecond == 123456


# ------------------------------------------------------------------ 3. 오류 번역


async def test_duplicate_key_1062_becomes_409(mysql_engine):
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with maker() as session:
        repo = UserRepository(session)
        await repo.create({"username": "alice", "email": "a@ex.com"})
        await session.commit()
        with pytest.raises(DuplicateException) as caught:
            await repo.create({"username": "alice", "email": "b@ex.com"})
    assert caught.value.status_code == 409


async def test_not_null_1048_becomes_422(mysql_engine):
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with maker() as session:
        with pytest.raises(ValidationException) as caught:
            await UserRepository(session).create({"username": "bob", "email": None})
    assert caught.value.status_code == 422


# ------------------------------------------------------------------ 4. 읽기/쓰기 라우팅


async def test_read_only_session_reads_from_reader_and_rejects_writes(mysql_engine, mysql_user):
    """reader 는 같은 서버의 **SELECT 전용 계정**이다.

    증명하는 것: 실제 aiomysql 연결에서 읽기 전용 세션의 SELECT 가 reader 엔진(그 계정)으로 가고,
    쓰기는 SQL 이 나가기 전에 `ReadOnlyRoutingError` 로 막혀 행이 남지 않는다. 앱 가드를 지나
    reader 로 새더라도 DB 권한이 마지막에 거부한다는 것도 같은 계정으로 확인한다.
    증명하지 못하는 것: 복제 지연·replica 장애 전환(서버가 하나라서).
    """
    reader = create_async_engine(mysql_user("SELECT"), **ENGINE_SAFETY_OPTIONS)
    maker = create_routing_sessionmaker(DatabaseRouter(writer=mysql_engine, readers=[reader]))
    try:
        async with maker() as session:
            mark_read_only(session)
            who = await session.scalar(sa.text("SELECT CURRENT_USER()"))
            assert who.startswith(reader.url.username + "@")
            session.add(_order("RO-1", datetime.now(UTC)))
            with pytest.raises(ReadOnlyRoutingError):
                await session.flush()

        async with reader.connect() as conn:
            with pytest.raises(sa.exc.DBAPIError) as denied:
                await conn.execute(sa.text("DELETE FROM sales_orders"))
            assert denied.value.orig.args[0] == 1142  # ER_TABLEACCESS_DENIED_ERROR

        async with maker() as session:
            assert await session.scalar(sa.select(sa.func.count()).select_from(SalesOrder)) == 0
            session.add(_order("RW-1", datetime.now(UTC)))
            await session.commit()  # 표시 없는 세션의 쓰기는 writer 로 간다
        async with maker() as session:
            assert await session.scalar(sa.select(sa.func.count()).select_from(SalesOrder)) == 1
    finally:
        await reader.dispose()


# ------------------------------------------------------------------ 5. CONVERT_TZ 집계


async def test_daily_sales_groups_by_local_date_with_convert_tz(mysql_engine):
    """운영 SQL 그대로 — UTC 저장 시각을 `+09:00` 영업일로 묶고, 반열린 구간 끝은 제외한다.

    오프셋 표기(`+00:00` → `+09:00`)만 쓰므로 MySQL 타임존 테이블이 없어도 된다.
    """
    tz = TimezoneSettings(TIME_ZONE="Asia/Seoul")
    start_at, end_at = tz.local_dates_to_utc(date(2026, 8, 1), date(2026, 8, 2))
    rows = [
        _order("D0", start_at - timedelta(microseconds=1)),  # 7/31 23:59:59.999999 KST — 제외
        _order("D1-a", start_at, "10.00"),  # 8/1 00:00 KST (UTC 로는 7/31)
        _order("D1-b", datetime(2026, 8, 1, 14, 59, 59, tzinfo=UTC), "2.50"),  # 8/1 23:59:59 KST
        _order("D2", datetime(2026, 8, 1, 15, 0, tzinfo=UTC), "7.25"),  # 8/2 00:00 KST
        _order("D3", end_at, "99.00"),  # 8/3 00:00 KST — 구간 끝, 제외
    ]
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(rows)
        await session.commit()
    async with maker() as session:
        result = await SalesReportRawRepository(session).daily_sales(
            start_at=start_at, end_at=end_at, tz_offset=tz.utc_offset(start_at)
        )

    assert [dict(row) for row in result] == [
        {"sales_date": date(2026, 8, 1), "order_count": 2, "gross_amount": Decimal("12.50")},
        {"sales_date": date(2026, 8, 2), "order_count": 1, "gross_amount": Decimal("7.25")},
    ]


# ------------------------------------------------------------------ 6. 기본 인증


async def test_app_driver_authenticates_with_caching_sha2_password_without_tls(
    mysql_server_url, mysql_user
):
    """MySQL 8 기본 인증으로 만든 새 계정에 aiomysql 이 TLS 없이 접속한다.

    새 계정은 서버 인증 캐시가 비어 있어 전체 인증(RSA 로 비밀번호 암호화)을 거친다 —
    `aiomysql[rsa]`(cryptography) 가 빠지면 여기서 실패한다.
    """
    url = mysql_user("SELECT")
    admin = create_async_engine(mysql_server_url, **ENGINE_SAFETY_OPTIONS)
    engine = create_async_engine(url, **ENGINE_SAFETY_OPTIONS)
    try:
        async with admin.connect() as conn:
            plugin = await conn.scalar(
                sa.text("SELECT plugin FROM mysql.user WHERE user = :u"), {"u": url.username}
            )
            await conn.exec_driver_sql("FLUSH PRIVILEGES")  # 인증 캐시를 비운다
        assert plugin == "caching_sha2_password"

        async with engine.connect() as conn:
            assert await conn.scalar(sa.text("SELECT 1")) == 1
            cipher = (await conn.execute(sa.text("SHOW SESSION STATUS LIKE 'Ssl_cipher'"))).one()
        assert cipher[1] == "", "TLS 로 붙으면 RSA 전체 인증 경로를 지나지 않는다"
    finally:
        await engine.dispose()
        await admin.dispose()
