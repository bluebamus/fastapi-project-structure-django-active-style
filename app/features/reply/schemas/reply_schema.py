"""Reply 도메인 스키마 — 댓글 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema


class ReplyBase(BaseModel):
    """댓글 공통 필드."""

    content: str = Field(..., min_length=1, description="댓글 본문")
    post_id: str | None = Field(None, max_length=36, description="대상 게시글 ID(선택)")


class ReplyCreate(ReplyBase):
    """댓글 생성 요청. 작성자는 서버가 인증 주체에서 채운다 — 본문의 author 는 무시된다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"content": "좋은 글이네요."}]})


class ReplyUpdate(PatchSchema):
    """댓글 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"content": "수정한 댓글"}]})

    content: str | None = Field(None, min_length=1, description="댓글 본문")


class ReplyResponse(ReplyBase):
    """댓글 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="댓글 UUID")
    author: str | None = Field(
        description="작성자 표시 이름(서버가 로그인 주체의 username 으로 채운다)"
    )
    author_id: str | None = Field(
        description="작성자 사용자 ID — 수정·삭제 권한의 기준. 작성자 컬럼 도입 전의 글은 null"
    )
    created_at: datetime = Field(description="생성 시각(UTC, 오프셋 포함 ISO 8601)")
    updated_at: datetime = Field(description="수정 시각(UTC, 오프셋 포함 ISO 8601)")


class ReplyListResponse(BaseModel):
    """댓글 목록 응답(페이지네이션)."""

    items: list[ReplyResponse] = Field(description="댓글 목록")
    total: int = Field(ge=0, description="전체 댓글 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
