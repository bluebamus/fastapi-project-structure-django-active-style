"""Auth 의존성 — 협력 객체 provider · 서비스 조립 · rate limit · 현재 사용자 해석.

모든 협력 객체는 여기 provider 가 만들고 `Depends` 로 생성자에 넘긴다(service-hardening C-1).
테스트는 `app.dependency_overrides` 로 provider 를 바꾼다 — Redis 는 `get_redis` 하나만
바꾸면 refresh 저장소·rate limiter 가 모두 따라온다.
"""

from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.core.exception import InvalidTokenException, TooManyRequestsException
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.redis import get_redis
from app.core.security.dependencies import (
    CurrentPrincipal,
    get_password_hasher,
    get_refresh_token_store,
    get_token_service,
)
from app.core.security.password_hasher import PasswordHasher
from app.core.security.rate_limiter import RateLimiter
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import TokenService
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from config import jwt_settings, middleware_settings

# 해시기·토큰·refresh 저장소 provider 는 user 기능도 쓰므로 core 에 있다(ADR-023).
# 여기서 다시 내보내 기존 import 경로(`...auth_dependencies import get_token_service`)를 유지한다.
__all__ = [
    "get_auth_service",
    "get_client_ip_resolver",
    "get_current_user",
    "get_password_hasher",
    "get_rate_limiter",
    "get_refresh_token_store",
    "get_token_service",
    "login_rate_limit",
    "register_rate_limit",
]


@lru_cache
def get_client_ip_resolver() -> ClientIPResolver:
    """접속 로그 미들웨어와 같은 설정(`TRUSTED_PROXY_HOPS`)으로 IP 를 판정한다."""
    return ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS)


def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    return RateLimiter(redis)


async def get_auth_service(
    session: AsyncSession = Depends(get_writer_db_session),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: TokenService = Depends(get_token_service),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
) -> AuthService:
    """AuthService 를 조립해 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다(P1-3).
    """
    return AuthService(session, hasher, tokens, refresh_store)


async def login_rate_limit(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    limiter: RateLimiter = Depends(get_rate_limiter),
    resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> str:
    """로그인 시도를 IP 기준·IP+사용자명 기준으로 센다. 초과면 429.

    IP+사용자명 키를 돌려준다 — 로그인이 성공하면 핸들러가 그 키를 초기화한다
    (정상 사용자가 오타 몇 번 뒤 성공했을 때 남은 창 동안 막히지 않게).
    폼은 핸들러와 같은 의존성이라 FastAPI 가 한 번만 파싱한다.
    """
    ip = resolver.resolve(request)
    user_key = f"auth:rl:login:{ip}:{form.username.lower()}"
    window = jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
    for key, limit in (
        (f"auth:rl:login-ip:{ip}", jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS),
        (user_key, jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS),
    ):
        result = await limiter.hit(key, limit, window)
        if not result.allowed:
            raise TooManyRequestsException(result.retry_after)
    return user_key


async def register_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
    resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> None:
    """가입 시도를 IP 기준으로 센다. 초과면 429."""
    result = await limiter.hit(
        f"auth:rl:register:{resolver.resolve(request)}",
        jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS,
        jwt_settings.AUTH_REGISTER_WINDOW_SECONDS,
    )
    if not result.allowed:
        raise TooManyRequestsException(result.retry_after)


async def get_current_user(
    principal: CurrentPrincipal,
    session: AsyncSession = Depends(get_read_only_db_session),
) -> User:
    """현재 사용자 **엔티티**를 반환한다(실패 시 401). `/me` 처럼 엔티티가 필요한 곳에서만 쓴다.

    토큰 검증은 core ``get_current_principal`` 하나를 거친다(C-8). 그 위에 DB 조회로
    삭제·비활성 사용자를 걸러 낸다 — 다른 보호 경로는 DB 를 보지 않는 주체만 쓴다(ADR-014).

    인증은 읽기 전용이므로 커밋하는 ``get_auth_service`` 를 거치지 않고 read-only 세션의
    리포지토리로 조회한다. 인증+쓰기 의존성을 함께 쓰는 엔드포인트에서 한 세션에 커밋
    주체가 둘이 되는 위험이 없고(검수 W2/REQ-009), ``DB_ROUTER_ENABLED`` 를 켜면 조회가
    replica 로 간다(P4-3).

    쓰기 의존성과 함께 쓰이는 라우트가 생기면 세션이 둘로 나뉜다(읽기용·쓰기용).
    인증 단계에서 읽은 객체를 쓰기 세션에서 수정하려 들면 다른 세션의 인스턴스라
    반영되지 않는다. 그런 라우트를 만들 때는 쓰기 세션에서 다시 조회할 것.
    """
    user = await UserRepository(session).get_by_id(principal.id)
    if user is None or not user.is_active:
        raise InvalidTokenException()
    return user
