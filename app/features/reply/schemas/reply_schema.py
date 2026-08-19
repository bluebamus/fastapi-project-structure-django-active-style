"""Reply 도메인 스키마 — 댓글 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReplyBase(BaseModel):
    """댓글 공통 필드."""

    content: str = Field(..., min_length=1, description="댓글 본문")
    author: str | None = Field(None, max_length=100, description="작성자(선택)")
    post_id: str | None = Field(None, max_length=36, description="대상 게시글 ID(선택)")


class ReplyCreate(ReplyBase):
    """댓글 생성 요청."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"content": "좋은 글이네요.", "author": "hong"}]}
    )


class ReplyUpdate(BaseModel):
    """댓글 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"content": "수정한 댓글"}]})

    content: str | None = Field(None, min_length=1, description="댓글 본문")
    author: str | None = Field(None, max_length=100, description="작성자")


class ReplyResponse(ReplyBase):
    """댓글 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="댓글 UUID")
    created_at: datetime = Field(description="생성 시각")
    updated_at: datetime = Field(description="수정 시각")


class ReplyListResponse(BaseModel):
    """댓글 목록 응답(페이지네이션)."""

    items: list[ReplyResponse] = Field(description="댓글 목록")
    total: int = Field(ge=0, description="전체 댓글 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
