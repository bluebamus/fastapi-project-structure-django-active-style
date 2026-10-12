"""Blog 도메인 스키마 — 게시글 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema


class PostBase(BaseModel):
    """게시글 공통 필드."""

    title: str = Field(..., min_length=1, max_length=200, description="제목")
    content: str = Field(..., min_length=1, description="본문")


class PostCreate(PostBase):
    """게시글 생성 요청. 작성자는 서버가 인증 주체에서 채운다 — 본문의 author 는 무시된다."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"title": "첫 글", "content": "본문입니다."}]}
    )


class PostUpdate(PatchSchema):
    """게시글 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"title": "수정한 제목"}]})

    title: str | None = Field(None, min_length=1, max_length=200, description="제목")
    content: str | None = Field(None, min_length=1, description="본문")


class PostResponse(PostBase):
    """게시글 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="게시글 UUID")
    author: str | None = Field(
        description="작성자 표시 이름(서버가 로그인 주체의 username 으로 채운다)"
    )
    author_id: str | None = Field(
        description="작성자 사용자 ID — 수정·삭제 권한의 기준. 작성자 컬럼 도입 전의 글은 null"
    )
    created_at: datetime = Field(description="생성 시각(UTC, 오프셋 포함 ISO 8601)")
    updated_at: datetime = Field(description="수정 시각(UTC, 오프셋 포함 ISO 8601)")


class PostListResponse(BaseModel):
    """게시글 목록 응답(페이지네이션)."""

    items: list[PostResponse] = Field(description="게시글 목록")
    total: int = Field(ge=0, description="전체 게시글 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
