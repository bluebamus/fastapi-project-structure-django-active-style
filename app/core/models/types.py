"""DB 컬럼 타입 — 시각은 UTC·마이크로초로 저장한다 (service-hardening ADR-007).

`DateTime(timezone=True)` 는 MySQL `DATETIME` 에 오프셋도 소수 초도 남기지 않는다. aware 값을
넣으면 벽시계 숫자만 저장되고, 읽으면 naive 로 돌아온다 — `TIME_ZONE` 을 바꾸는 순간 기존 행과
새 행의 의미가 섞인다. 그래서 정본을 UTC 로 고정한다.

- 저장: aware 값 → UTC 로 바꾼 뒤 tzinfo 를 떼어 저장한다. **naive 값은 거부한다** — 그 숫자가
  어느 지역의 벽시계인지 알 길이 없어, 조용히 받으면 9시간 어긋난 행이 쌓인다.
- 조회: DB 의 naive 값에 UTC tzinfo 를 붙여 돌려준다. 응답 JSON 은 오프셋(`Z`)을 갖는다.
- MySQL 은 `DATETIME(6)`(마이크로초). 그 밖의 방언은 `DateTime()`.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class UTCDateTime(TypeDecorator[datetime]):
    """aware datetime ↔ DB 의 UTC naive 값."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "naive datetime 은 저장할 수 없습니다 — 타임존이 있는 값(예: "
                "timezone_settings.utc_now())을 넘기세요."
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def render_alembic_type(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Alembic autogenerate 가 `UTCDateTime` 을 **밑바탕 타입**으로 적게 한다(`render_item` 훅).

    기본 렌더는 `app.core.models.types.UTCDateTime()` 을 마이그레이션에 남긴다 — 리비전이 앱
    코드를 import 하게 되어, 나중에 이 클래스를 고치면 과거 리비전의 의미가 바뀐다.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return 'sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")'
    return False
