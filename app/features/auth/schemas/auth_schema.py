"""Auth 도메인 스키마 — 회원가입/토큰 요청·응답."""

from pydantic import BaseModel, ConfigDict, Field

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
    password: str = Field(..., min_length=8, max_length=128, description="비밀번호(8자 이상)")


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


class TokenResponse(BaseModel):
    """토큰 응답(OAuth2 bearer)."""

    access_token: str = Field(description="API 호출에 쓰는 짧은 수명 토큰")
    refresh_token: str = Field(description="access token 재발급용 토큰(별도 키로 서명)")
    token_type: str = Field(default="bearer", description="토큰 타입")


class RefreshRequest(BaseModel):
    """토큰 재발급 요청."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"refresh_token": "eyJhbGci..."}]})

    refresh_token: str = Field(..., description="유효한 Refresh Token")
