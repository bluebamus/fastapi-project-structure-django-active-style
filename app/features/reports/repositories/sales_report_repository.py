"""매출 리포트 Raw Repository.

집계 전용 ORM 모델을 만들지 않고 Raw SQL 로 계산한다 (SCN-RAW-001). 이유는
`GROUP BY` 결과가 엔티티가 아니기 때문이다 — 식별자도 수명주기도 없는 행을 ORM
모델로 만들면 매핑만 늘고 얻는 것이 없다.

## SQL 은 여기가 소유한다

문장은 모듈 상수다. 요청 값으로 SQL 을 조립하지 않으며 외부 값은 named bind 로만
들어온다 (RAW-REP-003). Service 는 기간 규칙만 알고 컬럼 alias 는 모른다.

## MySQL 방언

`DATE()`, `CONVERT_TZ()` 는 MySQL 문법이다 (RAW-REP-006). SQLite 로 이 SQL 을 검증하지
않으며, 테스트 편의를 위해 운영 SQL 을 문자열 치환하지도 않는다. 실제 검증은
`compose.test.yaml` 의 MySQL 8.4 에 대고 하는 `tests/integration/test_sales_report_mysql.py` 가
담당한다.

## 기간 경계와 시간대 (ADR-007)

`created_at` 은 UTC 로 저장된 순간이고, 리포트의 "날짜" 는 설정 `TIME_ZONE` 의 영업일이다.
그래서 Service 가 지역 날짜 범위를 UTC 순간의 반열린 구간 `[start_at, end_at)` 으로 바꿔 넘기고
(종료일 하루 전체 포함), 여기서는 `CONVERT_TZ` 로 지역 시각으로 옮긴 뒤 날짜로 묶는다.
두 경계는 `UTCDateTime` 으로 bind 되어 naive 값이 섞이면 실행 전에 거부된다.
"""

from datetime import datetime

from sqlalchemy import bindparam, text
from sqlalchemy.engine import RowMapping

from app.core.models.types import UTCDateTime
from app.core.repositories.raw_repository_base import RawRepositoryBase

# ponytail: 오프셋은 쿼리마다 하나(기간 시작 시점의 값)다. DST 가 있는 TIME_ZONE 이면 전환일 전후
# 행이 한 시간 어긋난다 — 그때는 MySQL 타임존 테이블을 적재해 `CONVERT_TZ(created_at, '+00:00',
# 'America/New_York')` 처럼 지역 이름으로 행마다 변환하거나, 날짜 경계별 오프셋을 나눠 조회한다.
_DAILY_SALES = text(
    """
    SELECT
        DATE(CONVERT_TZ(o.created_at, '+00:00', :tz_offset)) AS sales_date,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at < :end_at
    GROUP BY sales_date
    ORDER BY sales_date ASC
    """
).bindparams(
    bindparam("start_at", type_=UTCDateTime()),
    bindparam("end_at", type_=UTCDateTime()),
)


class SalesReportRawRepository(RawRepositoryBase):
    """일별 매출 집계 조회."""

    async def daily_sales(
        self, *, start_at: datetime, end_at: datetime, tz_offset: str
    ) -> list[RowMapping]:
        """`[start_at, end_at)` 의 주문을 `tz_offset` 지역 날짜별로 센다(주문 없는 날은 행이 없다).

        Args:
            start_at: 구간 시작(포함, aware).
            end_at: 구간 끝(제외, aware).
            tz_offset: 날짜를 가를 지역 오프셋(`+09:00` 형식).
        """
        rows = await self.fetch_all(
            _DAILY_SALES,
            {"start_at": start_at, "end_at": end_at, "tz_offset": tz_offset},
            query_name="sales_report.daily_sales",
        )
        return list(rows)
