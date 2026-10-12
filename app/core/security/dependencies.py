"""인증·인가 provider — 모든 기능이 core 하나만 의존해 같은 규칙을 쓴다 (ADR-014).

라우트는 이렇게 보호한다:

    async def create(principal: CurrentPrincipal, ...)          # 로그인 필요(401)
    async def purge(admin: SuperuserPrincipal, ...)             # 슈퍼유저 전용(401/403)
    @router.post(..., dependencies=[Depends(require_superuser)]) # 주체를 쓰지 않는 관리 경로

소유권(소유자 또는 슈퍼유저)은 서비스가 ``OwnershipPolicy`` 를 생성자로 받아 판정한다.
테스트는 ``app.dependency_overrides`` 로 provider 를 바꾼다(C-1).
"""

from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from app.core.exception import ErrorResponse, ForbiddenException, UnauthorizedException
from app.core.redis import get_redis
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.password_hasher import PasswordHasher
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import ACCESS, TokenService
from config import jwt_settings

# 로그인 엔드포인트(auth 기능)에서 access token 을 발급받는다. 경로 문자열만 알 뿐
# auth 기능을 import 하지 않는다(C-2). auto_error=False — 토큰이 없을 때도 FastAPI 기본
# HTTPException 대신 이 저장소의 오류 형식(UnauthorizedException)으로 401 을 낸다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# OpenAPI 문서용 응답 묶음 — 보호 라우트의 ``responses=`` 에 합친다.
UNAUTHORIZED_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 필요(토큰 없음·만료·위조)"}
}
FORBIDDEN_RESPONSES: dict[int | str, dict[str, Any]] = {
    **UNAUTHORIZED_RESPONSES,
    403: {"model": ErrorResponse, "description": "권한 없음(소유자·슈퍼유저 아님)"},
}


@lru_cache
def get_password_hasher() -> PasswordHasher:
    """프로세스 단일 해시기 — 생성 시 더미 해시를 한 번 계산한다."""
    return PasswordHasher()


@lru_cache
def get_token_service() -> TokenService:
    return TokenService(jwt_settings)


@lru_cache
def get_ownership_policy() -> OwnershipPolicy:
    return OwnershipPolicy()


def get_refresh_token_store(
    redis: Redis = Depends(get_redis),
    tokens: TokenService = Depends(get_token_service),
) -> RefreshTokenStore:
    return RefreshTokenStore(redis, int(tokens.refresh_ttl.total_seconds()))


async def get_current_principal(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    tokens: TokenService = Depends(get_token_service),
) -> Principal:
    """Bearer access 토큰을 검증해 주체를 만든다(DB 조회 없음). 실패는 401.

    토큰 없음은 ``UNAUTHORIZED``, 토큰이 있으나 무효면 ``AUTH_INVALID_TOKEN`` 이다.

    성공하면 ``request.state.user_id`` 를 남긴다 — 접속 로그 미들웨어가 응답 뒤에 읽는다.
    """
    if not token:
        raise UnauthorizedException()
    claims = tokens.decode(token, ACCESS)
    principal = Principal(id=claims["sub"], username=claims["username"], is_superuser=claims["su"])
    request.state.user_id = principal.id
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


async def require_superuser(principal: CurrentPrincipal) -> Principal:
    """슈퍼유저가 아니면 403."""
    if not principal.is_superuser:
        raise ForbiddenException()
    return principal


SuperuserPrincipal = Annotated[Principal, Depends(require_superuser)]
