"""
User 도메인 예외 정의

core 의 공통 예외(NotFoundException, DuplicateException 등)를 상속하여
도메인 에러 코드를 부여한다.
"""

from enum import StrEnum

from app.core.exception import DuplicateException, ForbiddenException, NotFoundException


class UserErrorCode(StrEnum):
    """User 도메인 에러 코드 (네이밍: USER_{대상}_{원인})."""

    USER_NOT_FOUND = "USER_NOT_FOUND"
    USERNAME_DUPLICATE = "USER_USERNAME_DUPLICATE"
    PRIVILEGED_FIELD = "USER_PRIVILEGED_FIELD"


class UserNotFoundException(NotFoundException):
    """사용자를 찾을 수 없는 경우."""

    error_code = UserErrorCode.USER_NOT_FOUND
    message = "사용자를 찾을 수 없습니다."


class UsernameDuplicateException(DuplicateException):
    """사용자명이 이미 존재하는 경우."""

    error_code = UserErrorCode.USERNAME_DUPLICATE
    message = "이미 존재하는 사용자명입니다."


class PrivilegedFieldException(ForbiddenException):
    """슈퍼유저가 아닌 주체가 is_active·is_superuser 를 바꾸려는 경우(403)."""

    error_code = UserErrorCode.PRIVILEGED_FIELD
    message = "활성 여부·슈퍼유저 여부는 슈퍼유저만 바꿀 수 있습니다."
