"""일별 매출 리포트 엔드포인트 테스트.

Raw SQL 예제 기능이다. 보는 것은 집계 숫자가 아니라 계약이다.

- 조회가 read-only Dependency 를 쓰는가 — Raw 라는 이유로 쓰기 세션을 잡지 않는가
- Raw 행이 DTO 경계에서 검증되는가 — SQL alias 가 어긋나면 200 이 아니라 실패인가
- 기간 규칙이 Service 에 있는가 (SQL 도 View 도 아닌)

**집계 SQL 자체는 여기서 검증하지 않는다.** `CONVERT_TZ()` 는 MySQL
문법이고, SQLite 통과는 MySQL 방언의 승인 근거가 되지 못한다. 그래서
MySQL 에 의존하는 **그 한 지점만** 대체한다. 운영 SQL 을 테스트 편의로 문자열 치환하지는 않는다.
"""

import inspect
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import ValidationError

from app.core.db.session import get_read_only_db_session
from app.features.reports.dependencies.report_dependencies import get_report_service_readonly
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.models.models import SalesOrder  # noqa: F401  (register table)
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.reports.schemas.report_schema import DailySalesItem
from app.features.reports.services.report_service import ReportService
from config import TimezoneSettings, timezone_settings
from tests.auth_headers import superuser_headers

KST = ZoneInfo("Asia/Seoul")

_ROWS = [
    {"sales_date": date(2026, 8, 1), "order_count": 2, "gross_amount": Decimal("30.00")},
    {"sales_date": date(2026, 8, 2), "order_count": 1, "gross_amount": Decimal("12.50")},
]


@pytest.fixture
def stub_daily_sales(monkeypatch):
    """MySQL 방언에 의존하는 한 지점만 대체한다. 호출 인자는 그대로 기록한다."""
    calls: list[dict] = []

    async def _fake(self, *, start_at, end_at, tz_offset):
        calls.append({"start_at": start_at, "end_at": end_at, "tz_offset": tz_offset})
        return list(_ROWS)

    monkeypatch.setattr(SalesReportRawRepository, "daily_sales", _fake)
    return calls


@pytest_asyncio.fixture
async def client(stub_daily_sales, make_feature_client):
    """조회 Dependency **만** 오버라이드한다.

    쓰기 Dependency 를 오버라이드하지 않는 것이 의도다 — 이 기능이 몰래 writer 를
    잡으면 실제 DB 로 새어나가 테스트가 실패한다.
    """
    client, _, _ = await make_feature_client(headers=superuser_headers(), writer=False)
    return client


# ------------------------------------------------------------------ 자동배선


# ------------------------------------------------------------------ 조회


async def test_returns_aggregated_items(client):
    response = await client.get(
        "/api/v1/reports/sales/daily",
        params={"start_date": "2026-08-01", "end_date": "2026-08-02"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"] == "2026-08-01"
    assert body["end_date"] == "2026-08-02"
    assert [item["sales_date"] for item in body["items"]] == ["2026-08-01", "2026-08-02"]
    assert Decimal(str(body["items"][0]["gross_amount"])) == Decimal("30.00")


async def test_query_params_reach_repository_as_utc_bounds(client, stub_daily_sales, monkeypatch):
    """View 가 파싱한 지역 날짜를 Service 가 UTC 반열린 구간과 오프셋으로 바꿔 넘긴다."""
    monkeypatch.setattr(timezone_settings, "TIME_ZONE", "Asia/Seoul")

    await client.get(
        "/api/v1/reports/sales/daily",
        params={"start_date": "2026-08-01", "end_date": "2026-08-07"},
    )

    assert stub_daily_sales == [
        {
            "start_at": datetime(2026, 7, 31, 15, 0, tzinfo=UTC),
            "end_at": datetime(2026, 8, 7, 15, 0, tzinfo=UTC),
            "tz_offset": "+09:00",
        }
    ]


async def test_empty_period_returns_empty_items(client, monkeypatch):
    async def _empty(self, *, start_at, end_at, tz_offset):
        return []

    monkeypatch.setattr(SalesReportRawRepository, "daily_sales", _empty)

    body = (
        await client.get(
            "/api/v1/reports/sales/daily",
            params={"start_date": "2026-08-01", "end_date": "2026-08-02"},
        )
    ).json()

    assert body["items"] == []


async def test_reversed_period_returns_422(client):
    response = await client.get(
        "/api/v1/reports/sales/daily",
        params={"start_date": "2026-08-07", "end_date": "2026-08-01"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"start_date": "not-a-date", "end_date": "2026-08-02"},
        {"start_date": "2026-08-01"},
        {},
    ],
    ids=["bad-format", "missing-end", "missing-both"],
)
async def test_invalid_query_params_return_422(client, params):
    assert (await client.get("/api/v1/reports/sales/daily", params=params)).status_code == 422


# ------------------------------------------------------------------ 계약


def test_read_endpoint_uses_read_only_session():
    """조회 Dependency 가 read-only 세션에 묶여 있다."""
    parameter = inspect.signature(get_report_service_readonly).parameters["session"]

    assert parameter.default.dependency is get_read_only_db_session


def test_reports_feature_never_requests_a_writer_session():
    """리포트에는 쓰기 Dependency 자체가 없다 — Raw 는 접근 방식이지 권한이 아니다."""
    from pathlib import Path

    feature_root = Path(__file__).resolve().parents[1]
    sources = [
        path.read_text(encoding="utf-8")
        for path in feature_root.rglob("*.py")
        if "tests" not in path.parts
    ]

    assert not any("get_writer_db_session" in source for source in sources)


async def test_service_rejects_reversed_period():
    """기간 규칙은 Service 소유다 — SQL 이 빈 결과로 삼키지 않는다."""
    service = ReportService.__new__(ReportService)

    with pytest.raises(InvalidDateRangeException):
        await service.get_daily_sales(start_date=date(2026, 8, 7), end_date=date(2026, 8, 1))


def test_dto_rejects_mismatched_sql_alias():
    """SQL alias 가 DTO 필드와 어긋나면 그 자리에서 실패한다."""
    with pytest.raises(ValidationError):
        DailySalesItem.model_validate({"date": "2026-08-01", "count": 1, "amount": "1.00"})


# ------------------------------------------------------------------ OpenAPI


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 1, 1), date(2027, 1, 2)),  # 367일
        (date(9998, 12, 1), date(9999, 12, 31)),  # end+1일 이 넘치는 날짜
        (date(1969, 12, 31), date(1970, 1, 1)),
        (date(1, 1, 1), date(1, 1, 2)),
    ],
    ids=["367-days", "overflow-end", "before-1970", "year-1"],
)
async def test_service_rejects_out_of_bounds_period(start, end):
    """과대 스캔·날짜 연산 overflow 는 SQL 까지 가기 전에 422 다."""
    service = ReportService.__new__(ReportService)

    with pytest.raises(InvalidDateRangeException) as caught:
        await service.get_daily_sales(start_date=start, end_date=end)

    assert caught.value.status_code == 422


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2024, 1, 1), date(2024, 12, 31)),  # 윤년 366일 — 상한 포함
        (date(1970, 1, 1), date(1970, 1, 1)),
        (date(9998, 12, 31), date(9998, 12, 31)),
    ],
    ids=["366-days", "min-date", "max-date"],
)
async def test_service_accepts_boundary_periods(stub_daily_sales, start, end):
    service = ReportService(session=None, timezone=TimezoneSettings(TIME_ZONE="Asia/Seoul"))

    await service.get_daily_sales(start_date=start, end_date=end)

    # 지역 시작일 00:00 ~ 종료일 다음 날 00:00 (aware 비교는 순간 비교다).
    assert stub_daily_sales == [
        {
            "start_at": datetime.combine(start, time.min, KST),
            "end_at": datetime.combine(end, time.min, KST) + timedelta(days=1),
            "tz_offset": "+09:00",
        }
    ]


@pytest.mark.parametrize(
    ("zone", "day", "start_at", "end_at", "offset"),
    [
        (
            "Asia/Seoul",
            date(2026, 1, 2),
            datetime(2026, 1, 1, 15, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
            "+09:00",
        ),
        (
            "UTC",
            date(2026, 1, 2),
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            "+00:00",
        ),
        (
            "Asia/Kolkata",
            date(2026, 1, 2),
            datetime(2026, 1, 1, 18, 30, tzinfo=UTC),
            datetime(2026, 1, 2, 18, 30, tzinfo=UTC),
            "+05:30",
        ),
        (
            "America/New_York",
            date(2026, 7, 4),
            datetime(2026, 7, 4, 4, 0, tzinfo=UTC),
            datetime(2026, 7, 5, 4, 0, tzinfo=UTC),
            "-04:00",
        ),
    ],
    ids=["seoul", "utc", "kolkata-half-hour", "new-york-dst"],
)
async def test_service_converts_local_day_to_utc_bounds(
    stub_daily_sales, zone, day, start_at, end_at, offset
):
    """지역 영업일 하루 = UTC 의 [그날 지역 00:00, 다음 날 지역 00:00). 경계는 UTC aware 다."""
    service = ReportService(session=None, timezone=TimezoneSettings(TIME_ZONE=zone))

    await service.get_daily_sales(start_date=day, end_date=day)

    (call,) = stub_daily_sales
    assert call == {"start_at": start_at, "end_at": end_at, "tz_offset": offset}
    assert call["start_at"].utcoffset() == call["end_at"].utcoffset() == UTC.utcoffset(None)


async def test_overflowing_end_date_returns_422(client):
    response = await client.get(
        "/api/v1/reports/sales/daily",
        params={"start_date": "9999-12-30", "end_date": "9999-12-31"},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "REPORTS_DATE_RANGE_INVALID"
