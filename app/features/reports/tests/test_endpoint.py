"""일별 매출 리포트 엔드포인트 테스트 (Phase 8).

이 기능은 Phase 6 의 Raw Base 를 **실전에 처음 적용한** 자리다. 그래서 보는 것은
집계 숫자가 아니라 계약이다.

- `main.py` 를 고치지 않고 자동 발견·마운트되는가 (C-1)
- 조회가 read-only Dependency 를 쓰는가 — Raw 라는 이유로 쓰기 세션을 잡지 않는가
- Raw 행이 DTO 경계에서 검증되는가 — SQL alias 가 어긋나면 200 이 아니라 실패인가
- 기간 규칙이 Service 에 있는가 (SQL 도 View 도 아닌)

**집계 SQL 자체는 여기서 검증하지 않는다.** `DATE_ADD(..., INTERVAL 1 DAY)` 는 MySQL
문법이고, SQLite 통과는 MySQL 방언의 승인 근거가 되지 못한다(RAW-REP-006). 그래서
MySQL 에 의존하는 **그 한 지점만** 대체하고, 실제 SQL 은
`tests/integration/test_sales_report_mysql.py` 가 MySQL 8.4 에 대고 확인한다.
운영 SQL 을 테스트 편의로 문자열 치환하지는 않는다.
"""

import inspect
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session
from app.features.reports.dependencies.report_dependencies import get_report_service_readonly
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.models.models import SalesOrder  # noqa: F401  (register table)
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository
from app.features.reports.schemas.report_schema import DailySalesItem
from app.features.reports.services.report_service import ReportService
from main import app

_ROWS = [
    {"sales_date": date(2026, 8, 1), "order_count": 2, "gross_amount": Decimal("30.00")},
    {"sales_date": date(2026, 8, 2), "order_count": 1, "gross_amount": Decimal("12.50")},
]


@pytest.fixture
def stub_daily_sales(monkeypatch):
    """MySQL 방언에 의존하는 한 지점만 대체한다. 호출 인자는 그대로 기록한다."""
    calls: list[dict] = []

    async def _fake(self, *, start_date, end_date):
        calls.append({"start_date": start_date, "end_date": end_date})
        return list(_ROWS)

    monkeypatch.setattr(SalesReportRawRepository, "daily_sales", _fake)
    return calls


@pytest_asyncio.fixture
async def client(stub_daily_sales):
    """조회 Dependency **만** 오버라이드한다.

    쓰기 Dependency 를 오버라이드하지 않는 것이 의도다 — 이 기능이 몰래 writer 를
    잡으면 실제 DB 로 새어나가 테스트가 실패한다.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_read_only_db_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


# ------------------------------------------------------------------ 자동배선


def test_reports_is_auto_registered():
    """디렉터리 컨벤션만으로 리포트 라우터가 발견·마운트된다 (C-1)."""
    assert "/api/v1/reports/sales/daily" in app.openapi()["paths"]


def test_main_has_no_reports_reference():
    """중앙 파일을 고치지 않았다 — 이 기능은 디렉터리 존재로만 등록된다."""
    from pathlib import Path

    main_source = (
        Path(__file__).resolve().parents[4].joinpath("main.py").read_text(encoding="utf-8")
    )

    assert "reports" not in main_source


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


async def test_query_params_reach_repository_as_dates(client, stub_daily_sales):
    """View 가 문자열을 date 로 파싱해 Service 를 거쳐 그대로 전달한다."""
    await client.get(
        "/api/v1/reports/sales/daily",
        params={"start_date": "2026-08-01", "end_date": "2026-08-07"},
    )

    assert stub_daily_sales == [{"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 7)}]


async def test_empty_period_returns_empty_items(client, monkeypatch):
    async def _empty(self, *, start_date, end_date):
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
    """SQL alias 가 DTO 필드와 어긋나면 그 자리에서 실패한다 (RAW-REP-005)."""
    with pytest.raises(ValidationError):
        DailySalesItem.model_validate({"date": "2026-08-01", "count": 1, "amount": "1.00"})


def test_dto_does_not_rely_on_from_attributes():
    """Raw 결과는 ORM 객체가 아니다 — 속성 접근으로 통과시키지 않는다."""
    assert DailySalesItem.model_config.get("from_attributes") is not True


# ------------------------------------------------------------------ OpenAPI


def test_openapi_documents_the_report_operation():
    operation = app.openapi()["paths"]["/api/v1/reports/sales/daily"]["get"]

    assert operation["operationId"] == "getDailySalesReport"
    assert operation["tags"] == ["Reports"]
    assert operation["summary"]
    assert operation["description"]
    assert {parameter["name"] for parameter in operation["parameters"]} == {
        "start_date",
        "end_date",
    }


def test_openapi_exposes_the_raw_result_schema():
    """Raw 응답도 ORM 응답과 같은 문서 품질을 갖는다 (VIEW-002)."""
    schemas = app.openapi()["components"]["schemas"]

    assert "DailySalesReportResponse" in schemas
    assert "DailySalesItem" in schemas
    assert "RowMapping" not in " ".join(schemas)
