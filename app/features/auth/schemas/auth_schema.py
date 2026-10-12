"""Auth 도메인 스키마 — 회원가입/토큰 요청·응답."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.security.password_hasher import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.utils.validators import EMAIL_PATTERN


class RegisterRequest(BaseModel):
    """회원가입 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"username": "hong", "email": "hong@example.com", "password": "s3cret-pass"}
            ]
        }
    )

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="비밀번호(8자 이상)",
    )


class AuthUserResponse(BaseModel):
    """인증 흐름이 돌려주는 사용자 표현(민감 정보 제외).

    `user` 도메인의 `UserResponse` 와 **이름이 겹치면 안 된다**. 겹치면 FastAPI 가
    OpenAPI component key 에 모듈 경로를 합성해
    `app__features__auth__schemas__auth_schema__UserResponse` 같은 이름을 만든다.
    클라이언트 생성기가 그 이름을 그대로 타입명으로 쓰므로 공개 계약이 내부
    디렉터리 구조에 묶인다 — 파일을 옮기면 클라이언트가 깨진다 (F-004).

    두 DTO 는 필드도 다르다. 이쪽은 인증에 필요한 최소 정보만 담고 시각 정보를
    노출하지 않는다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="사용자 UUID")
    username: str = Field(description="사용자명")
    email: str = Field(description="이메일")
    is_active: bool = Field(description="활성 여부")
    is_superuser: bool = Field(description="슈퍼유저 여부")


class TokenResponse(BaseModel):
    """토큰 응답(OAuth2 bearer)."""

    access_token: str = Field(description="API 호출에 쓰는 짧은 수명 토큰")
    refresh_token: str = Field(
        description="access token 재발급용 토큰(별도 키로 서명, 한 번 쓰면 회전된다)"
    )
    token_type: str = Field(default="bearer", description="토큰 타입")
    expires_in: int = Field(description="access token 만료까지 남은 시간(초)")


class RefreshRequest(BaseModel):
    """refresh token 을 담은 요청 — 재발급(`/refresh`)과 로그아웃(`/logout`)이 함께 쓴다."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"refresh_token": "eyJhbGci..."}]})

    refresh_token: str = Field(..., description="로그인·재발급으로 받은 Refresh Token")
