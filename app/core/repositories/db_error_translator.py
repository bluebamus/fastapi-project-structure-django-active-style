"""DB 예외 → 애플리케이션 예외 변환 (한 곳).

드라이버 오류 코드로 원인을 가른다. 모든 무결성 오류를 "중복(409)" 으로 응답하면
NOT NULL 위반·없는 참조 같은 **클라이언트 입력 오류**가 "충돌" 로 보이고, 실제 원인을
응답만 보고는 알 수 없다.

응답 메시지·detail 에는 예외 원문(SQL 조각·바인딩 값)을 싣지 않는다(C-5) — 모델 이름만 남긴다.
"""

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exception import (
    AppException,
    ConflictException,
    DatabaseException,
    DuplicateException,
    ValidationException,
)

# MySQL 서버 오류 코드 (https://dev.mysql.com/doc/mysql-errors/8.4/en/server-error-reference.html)
ER_DUP_ENTRY = 1062
ER_BAD_NULL_ERROR = 1048
ER_NO_DEFAULT_FOR_FIELD = 1364
ER_ROW_IS_REFERENCED_2 = 1451
ER_NO_REFERENCED_ROW_2 = 1452

_FAILURE_MESSAGES = {
    "CREATE": "데이터 생성 중 오류가 발생했습니다.",
    "UPDATE": "데이터 업데이트 중 오류가 발생했습니다.",
    "DELETE": "데이터 삭제 중 오류가 발생했습니다.",
}


class DBErrorTranslator:
    """SQLAlchemy 예외를 상태 코드가 정해진 `AppException` 으로 바꾼다."""

    @staticmethod
    def _mysql_code(error: SQLAlchemyError) -> int | None:
        # pymysql/aiomysql 의 DBAPI 예외는 args[0] 에 서버 오류 코드(int)를 싣는다.
        args = getattr(getattr(error, "orig", None), "args", ())
        return args[0] if args and isinstance(args[0], int) else None

    @classmethod
    def translate(cls, error: SQLAlchemyError, *, model: str, operation: str) -> AppException:
        detail = {"model": model}
        code = cls._mysql_code(error)
        # SQLite 는 코드 대신 메시지로만 구분된다(대문자 제약 이름이 고정 문구다).
        message = str(getattr(error, "orig", "")) if isinstance(error, IntegrityError) else ""

        if code == ER_DUP_ENTRY or "UNIQUE constraint failed" in message:
            return DuplicateException(message="이미 존재하는 데이터입니다.", detail=detail)
        if code in (ER_BAD_NULL_ERROR, ER_NO_DEFAULT_FOR_FIELD) or (
            "NOT NULL constraint failed" in message
        ):
            return ValidationException(message="필수 값이 비어 있습니다.", detail=detail)
        # SQLite 는 참조 대상 없음(1452)과 참조 중(1451)을 같은 문구로 낸다 — 연산으로 가른다.
        sqlite_fk = "FOREIGN KEY constraint failed" in message
        if code == ER_ROW_IS_REFERENCED_2 or (sqlite_fk and operation == "DELETE"):
            return ConflictException(
                message="다른 데이터에서 참조 중이어서 처리할 수 없습니다.", detail=detail
            )
        if code == ER_NO_REFERENCED_ROW_2 or sqlite_fk:
            return ValidationException(message="참조하는 데이터가 없습니다.", detail=detail)
        return DatabaseException(
            message=_FAILURE_MESSAGES.get(operation, "데이터베이스 오류가 발생했습니다."),
            detail=detail,
        )
