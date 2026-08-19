"""
Reports 도메인 예외 정의

core 의 공통 예외를 상속하여 도메인 에러 코드를 부여한다.
"""

from enum import StrEnum

from app.core.exception import ValidationException


class ReportsErrorCode(StrEnum):
    """Reports 도메인 에러 코드 (네이밍: REPORTS_{대상}_{원인})."""

    DATE_RANGE_INVALID = "REPORTS_DATE_RANGE_INVALID"


class InvalidDateRangeException(ValidationException):
    """종료일이 시작일보다 빠른 경우."""

    error_code = ReportsErrorCode.DATE_RANGE_INVALID
    message = "종료일은 시작일보다 빠를 수 없습니다."
