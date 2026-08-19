"""일별 매출 리포트를 실제 MySQL 8.4 에 대고 검증한다 (계획서 §7, Phase 8).

기능 테스트(`app/features/reports/tests/`)는 View→Service→DTO 계약을 빠르게 못박지만
**집계 SQL 자체는 검증하지 못한다**. `DATE()`, `DATE_ADD(..., INTERVAL 1 DAY)` 는 MySQL
문법이고, SQLite 통과는 MySQL 방언의 승인 근거가 되지 못한다(RAW-REP-006).

여기서 확인하는 것:

1. 집계가 실제로 맞는가 — 일자별 묶기, 건수, 금액 합
2. **기간 경계** — 종료일의 23:59:59 주문이 포함되고 그 다음 날 00:00 주문은 빠지는가.
   `created_at <= :end_date` 로 쓰면 종료일이 통째로 빠지는데, 이 실수는 SQLite 에서도
   조용히 통과하고 운영에서 "어제 매출이 0" 으로 나타난다.
3. Raw 행이 실제 드라이버 타입(`date`/`int`/`Decimal`)으로 DTO 에 그대로 들어가는가
4. read-only 세션에서 리포트가 돌아가는가 (조회이므로 통과해야 한다)
5. SCN-RAW-002 — Raw DML 의 rowcount·commit 1회·실패 시 rollback·read-only 차단

5번의 쓰기 경로는 **운영 HTTP endpoint 를 만들지 않는다**(계획서 §7). 테스트 전용
Service/UoW 가 writer session 의 commit/rollback 을 소유하고, Repository 는 rowcount 와
예외만 돌려준다. 실패는 HTTP 응답이 아니라 예외 전파와 DB 상태 불변으로 확인한다.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.db.router import ReadOnlyRoutingError, mark_read_only
from app.core.repositories.raw_repository_base import RawRepositoryBase
from app.core.services.services_base import BaseService
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.reports.schemas.report_schema import DailySalesItem
from app.features.reports.services.report_service import ReportService

pytestmark = pytest.mark.mysql

_INSERT_ORDER = text(
    """
    INSERT INTO sales_orders (id, order_no, customer_email, total_amount, created_at)
    VALUES (:id, :order_no, :customer_email, :total_amount, :created_at)
    """
)


async def _seed(session, orders: list[tuple[str, str, datetime]]) -> None:
    """(주문번호, 금액, 주문시각) 목록을 넣는다. 이메일은 고정값이면 충분하다."""
    for index, (order_no, amount, created_at) in enumerate(orders):
        await session.execute(
            _INSERT_ORDER,
            {
                "id": f"order-{index:04d}",
                "order_no": order_no,
                "customer_email": "buyer@example.com",
                "total_amount": Decimal(amount),
                "created_at": created_at,
            },
        )
    await session.commit()


@pytest_asyncio.fixture
async def seeded(mysql_session_maker):
    """3일에 걸친 주문을 넣고 세션 팩토리를 돌려준다.

    경계 검증이 목적이라 시각을 의도적으로 극단에 둔다 — 종료일 마지막 1초와
    그 다음 날 첫 1초.
    """
    async with mysql_session_maker() as session:
        await _seed(
            session,
            [
                ("A-1", "10.10", datetime(2026, 8, 1, 0, 0, 0)),
                ("A-2", "20.20", datetime(2026, 8, 1, 12, 30, 0)),
                ("A-3", "0.70", datetime(2026, 8, 1, 23, 59, 59)),
                ("B-1", "5.00", datetime(2026, 8, 2, 9, 0, 0)),
                ("C-1", "99.00", datetime(2026, 8, 3, 0, 0, 0)),
            ],
        )
    return mysql_session_maker


# ------------------------------------------------------------------ 집계


async def test_daily_sales_groups_by_day_on_mysql(seeded):
    async with seeded() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 2)
        )

    assert [dict(row) for row in rows] == [
        {"sales_date": date(2026, 8, 1), "order_count": 3, "gross_amount": Decimal("31.00")},
        {"sales_date": date(2026, 8, 2), "order_count": 1, "gross_amount": Decimal("5.00")},
    ]


async def test_end_date_includes_the_whole_day_on_mysql(seeded):
    """종료일 하루가 통째로 포함된다 — 23:59:59 주문이 빠지면 안 된다."""
    async with seeded() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 1)
        )

    assert len(rows) == 1
    assert rows[0]["order_count"] == 3, "종료일 후반부 주문이 누락됐습니다."
    assert rows[0]["gross_amount"] == Decimal("31.00")


async def test_period_excludes_orders_outside_range_on_mysql(seeded):
    """다음 날 00:00 주문은 포함되지 않는다(반열린 구간의 반대쪽 경계)."""
    async with seeded() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_date=date(2026, 8, 2), end_date=date(2026, 8, 2)
        )

    assert [row["sales_date"] for row in rows] == [date(2026, 8, 2)]


async def test_empty_period_returns_no_rows_on_mysql(seeded):
    async with seeded() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)
        )

    assert rows == []


async def test_amount_sum_is_exact_on_mysql(seeded):
    """금액은 Decimal 로 정확히 더해진다 — float 였다면 31.000000000000004 가 된다."""
    async with seeded() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 1)
        )

    assert isinstance(rows[0]["gross_amount"], Decimal)
    assert rows[0]["gross_amount"] == Decimal("31.00")


# ------------------------------------------------------------------ DTO 경계


async def test_row_aliases_match_dto_fields_on_mysql(seeded):
    """SQL 컬럼 alias 와 DTO 필드가 실제 드라이버 타입까지 일치한다 (RAW-REP-005)."""
    async with seeded() as session:
        items = await ReportService(session).get_daily_sales(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 3)
        )

    assert [item.sales_date for item in items] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]
    assert items[0] == DailySalesItem(
        sales_date=date(2026, 8, 1), order_count=3, gross_amount=Decimal("31.00")
    )


async def test_report_runs_on_read_only_session_on_mysql(seeded):
    """리포트는 조회다 — read-only 세션에서 그대로 돌아야 한다."""
    async with seeded() as session:
        mark_read_only(session)

        items = await ReportService(session).get_daily_sales(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 3)
        )

    assert len(items) == 3


# ------------------------------------------------------------------ SCN-RAW-002


class _SalesOrderRawWriteRepository(RawRepositoryBase):
    """테스트 전용 Raw DML — 운영 코드에 쓰기 SQL 을 두지 않기 위해 여기 있다."""

    _UPDATE_AMOUNT = text(
        "UPDATE sales_orders SET total_amount = :total_amount WHERE order_no = :order_no"
    )
    _DELETE_BY_DAY = text("DELETE FROM sales_orders WHERE DATE(created_at) = :day")

    async def set_amount(self, *, order_no: str, total_amount: Decimal) -> int | None:
        return await self.execute(
            self._UPDATE_AMOUNT,
            {"order_no": order_no, "total_amount": total_amount},
            query_name="sales_order.set_amount",
        )

    async def delete_day(self, *, day: date) -> int | None:
        return await self.execute(
            self._DELETE_BY_DAY, {"day": day}, query_name="sales_order.delete_day"
        )


class _SalesOrderWriteService(BaseService):
    """테스트 전용 UoW. 트랜잭션 경계를 **여기가** 소유한다 (ADR-004).

    운영에서는 쓰기 View 가 같은 역할을 한다. Repository 는 어느 쪽에서도 commit 하지
    않는다 — 커밋 주체가 둘이 되면 실패 시 어디까지 남았는지 아무도 모른다.
    """

    def __init__(self, session) -> None:
        super().__init__(session)
        self.repository = _SalesOrderRawWriteRepository(session)

    async def correct_amount(self, *, order_no: str, total_amount: Decimal, fail: bool) -> int:
        try:
            affected = await self.repository.set_amount(
                order_no=order_no, total_amount=total_amount
            )
            if fail:
                raise RuntimeError("업무 규칙 위반")
            await self.commit()
        except Exception:
            await self.rollback()
            raise
        assert affected is not None
        return affected


async def _amount_of(session_maker, order_no: str) -> Decimal | None:
    async with session_maker() as session:
        return (
            await session.execute(
                text("SELECT total_amount FROM sales_orders WHERE order_no = :order_no"),
                {"order_no": order_no},
            )
        ).scalar_one_or_none()


async def test_raw_dml_returns_real_rowcount_on_mysql(seeded):
    async with seeded() as session:
        affected = await _SalesOrderRawWriteRepository(session).delete_day(day=date(2026, 8, 1))
        await session.rollback()

    assert affected == 3


async def test_write_service_commits_once_on_mysql(seeded):
    async with seeded() as session:
        affected = await _SalesOrderWriteService(session).correct_amount(
            order_no="A-1", total_amount=Decimal("77.77"), fail=False
        )

    assert affected == 1
    assert await _amount_of(seeded, "A-1") == Decimal("77.77")


async def test_write_service_rolls_back_and_propagates_on_mysql(seeded):
    """실패는 HTTP 응답이 아니라 예외 전파와 DB 상태 불변으로 드러난다."""
    async with seeded() as session:
        with pytest.raises(RuntimeError):
            await _SalesOrderWriteService(session).correct_amount(
                order_no="A-1", total_amount=Decimal("77.77"), fail=True
            )

    assert await _amount_of(seeded, "A-1") == Decimal("10.10"), "rollback 후에도 값이 바뀌었습니다."


async def test_raw_dml_is_blocked_on_read_only_session_on_mysql(seeded):
    """read-only 세션에서는 Raw DML 이 거부되고 DB 도 그대로다."""
    async with seeded() as session:
        mark_read_only(session)

        with pytest.raises(ReadOnlyRoutingError):
            await _SalesOrderRawWriteRepository(session).delete_day(day=date(2026, 8, 1))

        await session.rollback()

    async with seeded() as session:
        remaining = (await session.execute(text("SELECT COUNT(*) FROM sales_orders"))).scalar_one()

    assert remaining == 5
