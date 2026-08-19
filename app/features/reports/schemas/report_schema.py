"""Reports API 스키마.

Raw 결과는 ORM 객체가 아니라 `RowMapping` 이다. 그래서 `from_attributes=True` 에
기대지 않고 `dict(row)` 를 명시적으로 검증한다 — SQL 의 컬럼 alias 와 DTO 필드 이름이
어긋나면 그 자리에서 실패해야 한다. alias 를 조용히 흘려보내면 응답에 필드가 빠진
채로 200 이 나간다 (RAW-REP-005).
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    """일자 하나의 매출 집계.

    필드 이름이 곧 Raw SQL 의 컬럼 alias 다. 한쪽만 바꾸면 검증에서 걸린다.
    """

    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="해당 일자의 주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="해당 일자의 총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    """일별 매출 리포트 응답.

    주문이 없는 날은 항목에 나타나지 않는다(집계 SQL 이 GROUP BY 결과만 돌려준다).
    빈 날짜를 0 으로 채우는 것은 표현 계층의 선택이라 API 계약에 넣지 않는다.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date = Field(description="조회 시작일(포함)")
    end_date: date = Field(description="조회 종료일(포함)")
    items: list[DailySalesItem] = Field(description="일자별 집계 목록(오름차순)")
