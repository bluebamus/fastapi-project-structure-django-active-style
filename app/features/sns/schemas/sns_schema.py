"""SNS 도메인 스키마 — 피드 게시물 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SnsPostBase(BaseModel):
    """피드 게시물 공통 필드."""

    content: str = Field(..., min_length=1, max_length=500, description="게시물 본문")
    author: str | None = Field(None, max_length=100, description="작성자(선택)")


class SnsPostCreate(SnsPostBase):
    """피드 게시물 생성 요청."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"content": "오늘의 피드", "author": "hong"}]}
    )


class SnsPostUpdate(BaseModel):
    """피드 게시물 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"content": "수정한 피드"}]})

    content: str | None = Field(None, min_length=1, max_length=500, description="본문")
    author: str | None = Field(None, max_length=100, description="작성자")


class SnsPostResponse(SnsPostBase):
    """피드 게시물 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="게시물 UUID")
    like_count: int = Field(ge=0, description="좋아요 수")
    created_at: datetime = Field(description="생성 시각")
    updated_at: datetime = Field(description="수정 시각")


class SnsPostListResponse(BaseModel):
    """피드 게시물 목록 응답(페이지네이션)."""

    items: list[SnsPostResponse] = Field(description="게시물 목록")
    total: int = Field(ge=0, description="전체 게시물 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
