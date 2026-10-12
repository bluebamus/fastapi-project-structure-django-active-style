"""User 도메인 스키마 — 사용자 CRUD 요청/응답 모델 (Pydantic v2)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.schemas import PatchSchema
from app.core.security.password_hasher import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.utils.validators import EMAIL_PATTERN


class UserBase(BaseModel):
    """사용자 공통 필드."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")


class UserCreate(UserBase):
    """사용자 생성 요청(슈퍼유저 전용). 로그인할 수 없는 계정을 만들지 않도록 비밀번호가 필수다."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "hong",
                    "email": "hong@example.com",
                    "password": "s3cret-pass",
                    "is_superuser": False,
                }
            ]
        }
    )

    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="비밀번호(8자 이상) — Argon2 해시로만 저장된다",
    )
    is_superuser: bool = Field(False, description="슈퍼유저로 만들지 여부")


class UserUpdate(PatchSchema):
    """사용자 수정 요청 — 전달된 필드만 부분 수정한다.

    ``is_active``·``is_superuser`` 는 슈퍼유저만 바꿀 수 있다(본인 요청이면 403).
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{"is_active": False}]})

    email: str | None = Field(None, max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    is_active: bool | None = Field(None, description="활성 여부(슈퍼유저 전용)")
    is_superuser: bool | None = Field(None, description="슈퍼유저 여부(슈퍼유저 전용)")


class UserResponse(UserBase):
    """사용자 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="사용자 UUID")
    is_active: bool = Field(description="활성 여부")
    is_superuser: bool = Field(description="슈퍼유저 여부")
    created_at: datetime = Field(description="생성 시각(UTC, 오프셋 포함 ISO 8601)")
    updated_at: datetime = Field(description="수정 시각(UTC, 오프셋 포함 ISO 8601)")


class UserListResponse(BaseModel):
    """사용자 목록 응답(페이지네이션)."""

    items: list[UserResponse] = Field(description="사용자 목록")
    total: int = Field(ge=0, description="전체 사용자 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
