"""
Reply 도메인 데이터베이스 모델

댓글/답글(Reply) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import TimestampMixin, UUIDMixin
from config import timezone_settings


class Reply(Base, UUIDMixin, TimestampMixin):
    """댓글/답글.

    Attributes:
        id: UUID 기본키 (UUIDMixin)
        content: 댓글 본문
        author: 작성자(선택)
        post_id: 대상 게시글 ID(선택, FK 제약 없이 느슨하게 참조)
        created_at: 생성 시각 (TimestampMixin)
        updated_at: 수정 시각
    """

    __tablename__ = "replies"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: timezone_settings.now(),
        onupdate=lambda: timezone_settings.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Reply(id={self.id}, post_id={self.post_id})>"
