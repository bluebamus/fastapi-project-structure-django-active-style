"""User 도메인 스키마 — 사용자 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.utils.validators import EMAIL_PATTERN


class UserBase(BaseModel):
    """사용자 공통 필드."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")


class UserCreate(UserBase):
    """사용자 생성 요청."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"username": "hong", "email": "hong@example.com"}]}
    )


class UserUpdate(BaseModel):
    """사용자 수정 요청 — 전달된 필드만 부분 수정한다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"is_active": False}]})

    email: str | None = Field(None, max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    is_active: bool | None = Field(None, description="활성 여부")


class UserResponse(UserBase):
    """사용자 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="사용자 UUID")
    is_active: bool = Field(description="활성 여부")
    created_at: datetime = Field(description="생성 시각")
    updated_at: datetime = Field(description="수정 시각")


class UserListResponse(BaseModel):
    """사용자 목록 응답(페이지네이션)."""

    items: list[UserResponse] = Field(description="사용자 목록")
    total: int = Field(ge=0, description="전체 사용자 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
