"""관리 화면(sqladmin) 공용 필터 (security-ops-hardening ADR-004).

sqladmin 0.32 의 ``OperationColumnFilter`` 는 ``UTCDateTime``(TypeDecorator)을 날짜형으로 보지
못해 입력 문자열을 그대로 바인딩하고, ``UTCDateTime`` 이 naive·문자열을 거부해 목록이 500 이 났다.
``LocalDateFilter`` 는 업무 시간대(``TIME_ZONE``)의 날짜 하나 또는 기간(시작일~종료일, 양 끝 포함)을
UTC aware 범위로 바꿔 질의한다(기간 연산: admin-session-hardening ADR-005).

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

    연산: 같은 날(``on``) / 이후·포함(``on_or_after``) / 이전·미포함(``before``) /
    기간(``range``, 값 ``YYYY-MM-DD~YYYY-MM-DD`` — 시작일 00:00 ≤ t < 종료일 다음날 00:00, 양 끝 포함).
    기간은 한쪽을 비우면 열린 구간이다(``2026-10-01~`` = 그날 이후, ``~2026-10-19`` = 그날까지).
    잘못된 날짜·연산·역순 기간은 500 이 아니라 **필터 없이** 목록을 보여 주고 WARNING 을 남긴다.

    sqladmin 연산 필터는 값 하나만 넘기므로, 전용 템플릿(``template``)이 날짜 입력 두 개를 ``~`` 로
    합쳐 보낸다. 빠른 선택(오늘·최근 7일·30일)은 기간 연산 링크다(``quick_ranges``).

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
        ("range", "기간(양 끝 포함)"),
    )
    RANGE = "range"
    RANGE_SEPARATOR = "~"
    # sqladmin 은 필터 객체의 ``template`` 을 include 한다 — app/templates/admin 아래 파일.
    template = "sqladmin/filters/local_date_filter.html"

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

    @property
    def tz(self) -> tzinfo:
        return self._tz or timezone_settings.tz

    @staticmethod
    def _parse_day(text: str) -> date | None:
        text = text.strip()
        if not _DATE_PATTERN.fullmatch(text):
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    def _midnight(self, day: date) -> datetime:
        return datetime.combine(day, time.min, tzinfo=self.tz).astimezone(UTC)

    def day_bounds(self, value: str) -> tuple[datetime, datetime] | None:
        """지역 날짜의 [자정, 다음 자정) 을 UTC aware 로 돌려준다. 형식이 틀리면 None."""
        day = self._parse_day(value)
        if day is None:
            return None
        return self._midnight(day), self._midnight(day + timedelta(days=1))

    def range_bounds(self, value: str) -> tuple[datetime | None, datetime | None] | None:
        """``시작일~종료일`` 을 [시작일 자정, 종료일 다음 자정) UTC 로. 한쪽이 비면 그쪽은 None.

        둘 다 비었거나, 형식이 틀리거나, 시작일 > 종료일이면 None(필터 미적용).
        """
        if value.count(self.RANGE_SEPARATOR) != 1:
            return None
        first, last = (part.strip() for part in value.split(self.RANGE_SEPARATOR))
        start_day = self._parse_day(first) if first else None
        end_day = self._parse_day(last) if last else None
        if (first and start_day is None) or (last and end_day is None):
            return None
        if start_day is None and end_day is None:
            return None
        if start_day and end_day and start_day > end_day:
            return None
        start = self._midnight(start_day) if start_day else None
        end = self._midnight(end_day + timedelta(days=1)) if end_day else None
        return start, end

    def quick_ranges(self) -> list[tuple[str, str]]:
        """빠른 선택 — (이름, 기간 값). 오늘은 업무 시간대 기준."""
        today = datetime.now(self.tz).date()
        sep = self.RANGE_SEPARATOR
        return [
            ("오늘", f"{today}{sep}{today}"),
            ("최근 7일", f"{today - timedelta(days=6)}{sep}{today}"),
            ("최근 30일", f"{today - timedelta(days=29)}{sep}{today}"),
        ]

    async def get_filtered_query(
        self, query: Select, operation: str, value: Any, model: Any
    ) -> Select:
        if not value or not operation:
            return query
        column = get_column_obj(self.column, model)
        if operation == self.RANGE:
            span = self.range_bounds(str(value))
            if span is None:
                return self._ignored(query, operation, value)
            lower, upper = span
            if lower is not None:
                query = query.filter(column >= lower)
            if upper is not None:
                query = query.filter(column < upper)
            return query
        bounds = self.day_bounds(str(value))
        if bounds is None or operation not in dict(self.OPERATIONS):
            return self._ignored(query, operation, value)
        start, end = bounds
        if operation == "on":
            return query.filter(column >= start, column < end)
        if operation == "on_or_after":
            return query.filter(column >= start)
        return query.filter(column < start)

    def _ignored(self, query: Select, operation: str, value: Any) -> Select:
        logger.warning(
            "[LocalDateFilter] 잘못된 날짜 필터 — 적용하지 않음 param=%s op=%.20s value=%.30s",
            self.parameter_name,
            operation,
            value,
        )
        return query
