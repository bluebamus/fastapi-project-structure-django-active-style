"""관리 화면(sqladmin) 공용 필터 (security-ops-hardening ADR-004).

sqladmin 0.32 의 ``OperationColumnFilter`` 는 ``UTCDateTime``(TypeDecorator)을 날짜형으로 보지
못해 입력 문자열을 그대로 바인딩하고, ``UTCDateTime`` 이 naive·문자열을 거부해 목록이 500 이 났다.
``LocalDateFilter`` 는 업무 시간대(``TIME_ZONE``)의 날짜 하나를 UTC aware 범위로 바꿔 질의한다.

이 모듈은 sqladmin 을 import 한다 — 기능의 ``admin.py``(ADMIN_DISABLED=false 일 때만 로드)에서만
가져온다.
"""

import re
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any

from sqladmin.filters import OperationColumnFilter, get_column_obj, get_title
from sqlalchemy.sql.expression import Select

from app.utils.logs import get_logger
from config import timezone_settings

logger = get_logger("admin_filters")

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class LocalDateFilter(OperationColumnFilter):
    """``YYYY-MM-DD``(업무 시간대 기준) 날짜로 시각 컬럼을 거른다.

    연산: 같은 날(``on``) / 이후·포함(``on_or_after``) / 이전·미포함(``before``).
    잘못된 날짜·연산은 500 이 아니라 **필터 없이** 목록을 보여 주고 WARNING 을 남긴다.

    빠른 선택(오늘·최근 7일)은 두지 않는다 — sqladmin 의 연산 필터 화면은 값 입력이 필수라
    한 필터에 둘을 담을 수 없다. "최근 7일" 은 ``이후(포함)`` 에 7일 전 날짜를 넣는다.

    Args:
        column: 시각 컬럼(``UTCDateTime``).
        title: 필터 제목. 없으면 컬럼 이름 + 입력 형식.
        parameter_name: 쿼리 파라미터 이름. 없으면 컬럼 키.
        tz: 날짜 경계를 정할 시간대. 없으면 ``TIME_ZONE``(테스트가 주입한다).
    """

    OPERATIONS: tuple[tuple[str, str], ...] = (
        ("on", "같은 날"),
        ("on_or_after", "이후(포함)"),
        ("before", "이전(미포함)"),
    )

    def __init__(
        self,
        column: Any,
        title: str | None = None,
        parameter_name: str | None = None,
        tz: tzinfo | None = None,
    ) -> None:
        super().__init__(
            column,
            title=title or f"{get_title(column)} (YYYY-MM-DD)",
            parameter_name=parameter_name,
        )
        self._tz = tz

    def get_operation_options(self, column_obj: Any) -> list[tuple[str, str]]:
        return list(self.OPERATIONS)

    def day_bounds(self, value: str) -> tuple[datetime, datetime] | None:
        """지역 날짜의 [자정, 다음 자정) 을 UTC aware 로 돌려준다. 형식이 틀리면 None."""
        text = value.strip()
        if not _DATE_PATTERN.fullmatch(text):
            return None
        try:
            day = date.fromisoformat(text)
        except ValueError:
            return None
        tz = self._tz or timezone_settings.tz
        start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
        return start, end

    async def get_filtered_query(
        self, query: Select, operation: str, value: Any, model: Any
    ) -> Select:
        if not value or not operation:
            return query
        bounds = self.day_bounds(str(value))
        if bounds is None or operation not in dict(self.OPERATIONS):
            logger.warning(
                "[LocalDateFilter] 잘못된 날짜 필터 — 적용하지 않음 param=%s op=%.20s value=%.20s",
                self.parameter_name,
                operation,
                value,
            )
            return query
        column = get_column_obj(self.column, model)
        start, end = bounds
        if operation == "on":
            return query.filter(column >= start, column < end)
        if operation == "on_or_after":
            return query.filter(column >= start)
        return query.filter(column < start)
