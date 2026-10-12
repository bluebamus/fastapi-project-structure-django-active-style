"""
Reply 도메인 데이터베이스 모델

댓글/답글(Reply) 엔티티를 정의한다. 최소 CRUD 동작을 위한 기본 컬럼만 둔다.
"""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import (
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)


class Reply(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """댓글/답글.

    Attributes:
        id: UUID 기본키
        content: 댓글 본문
        author: 작성자 표시 이름(서버가 주체의 username 으로 채운다)
        author_id: 작성자 사용자 id(소유권 판정 기준)
        post_id: 대상 게시글 ID(선택, FK 제약 없이 느슨하게 참조)
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "replies"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 작성자 사용자 id — 서버가 인증 주체에서 채운다(ADR-015). 작성자 컬럼 도입 전의 행은 NULL 이고
    # 슈퍼유저만 수정한다. 사용자 삭제 뒤에도 글은 남기므로 FK 를 걸지 않는다.
    author_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    post_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<Reply(id={self.id}, post_id={self.post_id})>"
