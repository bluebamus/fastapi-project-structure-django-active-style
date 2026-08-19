"""매출 리포트 Raw Repository.

집계 전용 ORM 모델을 만들지 않고 Raw SQL 로 계산한다 (SCN-RAW-001). 이유는
`GROUP BY` 결과가 엔티티가 아니기 때문이다 — 식별자도 수명주기도 없는 행을 ORM
모델로 만들면 매핑만 늘고 얻는 것이 없다.

## SQL 은 여기가 소유한다

문장은 모듈 상수다. 요청 값으로 SQL 을 조립하지 않으며 외부 값은 named bind 로만
들어온다 (RAW-REP-003). Service 는 기간 규칙만 알고 컬럼 alias 는 모른다.

## MySQL 방언

`DATE()`, `DATE_ADD(..., INTERVAL 1 DAY)` 는 MySQL 문법이다 (RAW-REP-006). SQLite 로
이 SQL 을 검증하지 않으며, 테스트 편의를 위해 운영 SQL 을 문자열 치환하지도 않는다.
실제 검증은 `compose.test.yaml` 의 MySQL 8.4 에 대고 하는
`tests/integration/test_sales_report_mysql.py` 가 담당한다.

## 기간 경계

`created_at` 은 시각(DATETIME)이고 파라미터는 날짜다. 그래서 종료일을 `<=` 로 비교하면
그날 00:00:00 만 걸려 하루가 통째로 빠진다. `< end_date + 1일` 의 반열린 구간으로
비교해 종료일 전체를 포함시킨다.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from app.core.repositories.raw_repository_base import RawRepositoryBase

_DAILY_SALES = text(
    """
    SELECT
        DATE(o.created_at) AS sales_date,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.created_at >= :start_date
      AND o.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)
    GROUP BY DATE(o.created_at)
    ORDER BY sales_date ASC
    """
)


class SalesReportRawRepository(RawRepositoryBase):
    """일별 매출 집계 조회."""

    async def daily_sales(self, *, start_date: date, end_date: date) -> list[RowMapping]:
        """기간 내 일자별 주문 수와 총 매출을 돌려준다(주문 없는 날은 행이 없다)."""
        rows = await self.fetch_all(
            _DAILY_SALES,
            {"start_date": start_date, "end_date": end_date},
            query_name="sales_report.daily_sales",
        )
        return list(rows)
