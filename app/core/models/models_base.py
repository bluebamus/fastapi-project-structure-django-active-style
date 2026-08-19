"""
SQLAlchemy Base 클래스와 공통 컬럼 mixin

모든 ORM 모델의 기반이 되는 Base 와, 모델이 조합해 쓰는 작은 mixin 들을 정의한다.

사용법:
    from app.core.models.models_base import (
        Base,
        CreatedAtMixin,
        UUIDPrimaryKeyMixin,
        UpdatedAtMixin,
    )

    class MyModel(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
        __tablename__ = "my_table"
        ...

mixin 은 **작게 쪼개 둔다**. 갱신 시각이 필요 없는 모델(예: 접속 로그)이
updated_at 을 억지로 갖게 되면 스키마가 사실과 달라지기 때문이다.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import timezone_settings


class Base(DeclarativeBase):
    """
    SQLAlchemy Declarative Base

    모든 모델이 상속받는 기본 클래스입니다.
    """

    if TYPE_CHECKING:
        # 제네릭 코드(BaseRepository)가 PK 컬럼에 접근할 수 있도록 선언만 둔다.
        # 타입을 str 로 못박지 않는 이유는 PK 타입이 모델마다 다를 수 있기 때문이다
        # (BaseRepository[ModelT, PrimaryKeyT] 가 실제 타입을 책임진다).
        # TYPE_CHECKING 가드라 런타임 매핑에는 영향이 없다.
        id: Mapped[Any]

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }

    def to_dict(self) -> dict[str, Any]:
        """모델을 딕셔너리로 변환합니다."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class UUIDPrimaryKeyMixin:
    """UUID 문자열 기본키(`id`).

    `String(36)` 이라 MySQL·PostgreSQL·SQLite 어디서나 같은 모양으로 동작한다.
    """

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )


class CreatedAtMixin:
    """생성 시각(`created_at`). 설정된 타임존(기본 Asia/Seoul)을 따른다."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        nullable=False,
    )


class UpdatedAtMixin:
    """수정 시각(`updated_at`). UPDATE 시 자동 갱신된다.

    갱신 개념이 없는 모델(append-only 로그 등)은 이 mixin 을 상속하지 않는다.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        onupdate=lambda: timezone_settings.now(),
        nullable=False,
    )


# =============================================================================
# deprecated alias — 기존 import 호환용
# =============================================================================
# 정식 이름은 위쪽이다. 같은 객체를 가리키는 별칭이라 `issubclass` 검사와
# 기존 import 가 모두 그대로 동작한다. 신규 코드는 정식 이름을 쓴다.
UUIDMixin = UUIDPrimaryKeyMixin
TimestampMixin = CreatedAtMixin
