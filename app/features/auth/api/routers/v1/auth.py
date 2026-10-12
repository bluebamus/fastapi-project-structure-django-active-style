"""Auth v1 API — 회원가입 / 로그인 / 토큰 재발급 / 로그아웃 / 현재 사용자.

뷰는 HTTP 역할만: 입력 수신 → 주입된 AuthService 호출 → 응답 변환.
rate limit 은 라우트 의존성(`register_rate_limit`·`login_rate_limit`)이 핸들러 전에 건다.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exception import ErrorResponse
from app.core.security.rate_limiter import RateLimiter
from app.features.auth.dependencies.auth_dependencies import (
    get_auth_service,
    get_current_user,
    get_rate_limiter,
    login_rate_limit,
    register_rate_limit,
)
from app.features.auth.schemas.auth_schema import (
    AuthUserResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User

router = APIRouter()

_UNAUTH: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 실패"}
}
_THROTTLED: dict[int | str, dict[str, Any]] = {
    429: {"model": ErrorResponse, "description": "시도 횟수 초과(`Retry-After` 헤더 참고)"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "사용자명 중복"}
}


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="사용자명·이메일·비밀번호로 사용자를 생성합니다. IP 별 시도 횟수가 제한됩니다.",
    operation_id="authRegister",
    responses={**_CONFLICT, **_THROTTLED},
    dependencies=[Depends(register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthUserResponse:
    user = await service.register(payload)
    # DTO 검증이 commit **앞**이다 — 뒤에 두면 검증이 터졌을 때 사용자는 500 을 받는데
    # 행은 이미 저장돼 있다. `tests/test_dto_before_commit.py` 가 이 순서를 고정한다.
    response = AuthUserResponse.model_validate(user)
    await service.commit()
    return response


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인(OAuth2 password)",
    description=(
        "username/password(form)로 access·refresh 토큰을 발급합니다. "
        "IP 별·IP+사용자명 별 시도 횟수가 제한됩니다."
    ),
    operation_id="authLogin",
    responses={**_UNAUTH, **_THROTTLED},
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    throttle_key: str = Depends(login_rate_limit),
    limiter: RateLimiter = Depends(get_rate_limiter),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = await service.authenticate(form.username, form.password)
    tokens = await service.issue_tokens(user)
    # 옛 형식 해시를 새 해시로 바꿨다면 그 UPDATE 를 확정한다(바꾸지 않았으면 빈 커밋).
    await service.commit()
    await limiter.reset(throttle_key)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 재발급(회전)",
    description=(
        "Refresh Token 으로 새 access·refresh 토큰을 발급합니다. 쓴 refresh 토큰은 소비되며, "
        "같은 토큰이 다시 오면 그 로그인 세션(family) 전체가 폐기됩니다."
    ),
    operation_id="authRefresh",
    responses=_UNAUTH,
)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.rotate(payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="로그아웃",
    description=(
        "Refresh Token 의 로그인 세션(family)을 폐기합니다. 이미 쓰였거나 폐기된 토큰이어도 "
        "204 입니다. access token 은 만료(기본 15분)까지 유효합니다."
    ),
    operation_id="authLogout",
    responses=_UNAUTH,
)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=AuthUserResponse,
    summary="현재 사용자",
    description="Bearer access token 으로 현재 로그인 사용자를 반환합니다(보호 엔드포인트).",
    operation_id="authMe",
    responses=_UNAUTH,
)
async def me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(current_user)
