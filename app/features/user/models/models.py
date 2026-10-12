"""
User 도메인 데이터베이스 모델

사용자(User) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from sqlalchemy import Boolean, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class User(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """사용자.

    Attributes:
        id: UUID 기본키
        username: 사용자명(고유)
        email: 이메일
        is_active: 활성 여부
        is_superuser: 슈퍼유저 여부(관리 경로 접근·타인 리소스 수정 — ADR-016)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # 인증(auth 도메인)용 비밀번호 해시(Argon2, 옛 행은 bcrypt). 비밀번호 없이 생성된 기존 사용자를 위해 nullable.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # server_default 는 리비전이 기존 행을 채우는 값과 같다 — 기존 사용자는 모두 일반 사용자다.
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r})>"
