"""SQLAdmin(``/admin``) 로그인 백엔드 (admin-login ADR-002~ADR-004).

``/admin`` 은 **활성 슈퍼유저**만 쓴다. 계정은 ``scripts/create_superuser.py`` 로 만든다.

- 로그인: 폼 CSRF 토큰 확인(security-ops-hardening ADR-003) → 폼 username/password → rate limit(키 접두사 ``admin:rl:`` — API 로그인과 따로 센다,
  한도 설정은 API 와 같은 ``AUTH_LOGIN_*``) → API 로그인과 같은 ``verify_credentials`` →
  슈퍼유저 확인. 성공하면 세션을 비우고 사용자 id 만 넣는다(세션 고정 방지).
  실패 사유는 구분하지 않는다(계정 열거 방지). 한도 초과는 로그인 화면을 429 + ``Retry-After`` 로.
- 인증: 매 요청 세션의 id 로 DB 를 다시 본다 — 강등·비활성화가 다음 요청부터 반영된다.
- 세션 쿠키: ``admin_session``(접속 로그가 읽는 ``SESSION_COOKIE_NAME`` 과 다르다),
  ``Path=/admin``, ``SameSite=Strict``, HttpOnly, 8시간, 배포 환경은 Secure.
  서명 키는 ``SESSION_SECRET_KEY``.
- CSRF(synchronizer token): 로그인 화면을 그릴 때 세션에 ``secrets.token_urlsafe(32)`` 토큰을 두고
  폼 hidden 필드로 싣는다. POST 는 rate limit·자격 확인 **전에** 두 값을 상수 시간으로 비교하고,
  없거나 다르면 403 으로 로그인 화면을 다시 그린다. 로그인 성공 시 ``session.clear()`` 로 회전된다.
  로그인 이후 sqladmin 이 그리는 생성·수정·삭제 폼과 GET 로그아웃은 대상이 아니다
  (``SameSite=Strict``·``Path=/admin`` 이 1차 방어 — residual-risk).

이 모듈은 sqladmin 을 import 하므로 ``app/features/admin.py``(ADMIN_DISABLED=false 일 때만 로드)에서만
가져온다. 기능 패키지의 ``admin.py`` 가 아닌 이유: registry 는 그 이름을 ``admin_views`` 계약으로
읽는다.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response

from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.password_hasher import PasswordHasher
from app.core.security.rate_limiter import RateLimiter
from app.features.auth.exceptions import InvalidCredentialsException
from app.features.auth.services.auth_service import verify_credentials
from app.features.user.repositories.user_repository import UserRepository
from app.utils.logs import get_logger
from config import jwt_settings

logger = get_logger("admin_auth")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_PATH = "/admin"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60
LOGIN_TEMPLATE = "sqladmin/login.html"
THROTTLED_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
CSRF_FAILED_MESSAGE = "요청이 만료되었습니다. 다시 시도하세요."
# 세션 키와 폼 필드 이름이 같다 — 템플릿의 hidden input name 과 맞춘다.
CSRF_FIELD = "csrf_token"
# 로그에 싣는 사용자명 길이 상한 — 폼 값은 클라이언트 입력이라 길이를 믿지 않는다.
_LOG_USERNAME_MAX = 64


class AdminAuthBackend(AuthenticationBackend):
    """``/admin`` 의 로그인·로그아웃·요청별 인증.

    협력 객체는 모두 생성자로 받는다. 조립은 ``app/features/admin.py`` 가 한다.

    Args:
        session_factory: 요청 밖 세션 컨텍스트(운영은 ``background_db_session``).
        hasher: core ``PasswordHasher``.
        rate_limiter: 호출할 때마다 ``RateLimiter`` 를 돌려주는 함수. Redis 클라이언트는
            lifespan 이 만들어서(``app.state.redis``) 생성 시점에는 아직 없다.
        ip_resolver: ``TRUSTED_PROXY_HOPS`` 로 클라이언트 IP 를 고른다(API 로그인과 같다).
        secret_key: 세션 쿠키 서명 키.
        https_only: 쿠키 Secure 플래그(staging/production 에서 True).
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        hasher: PasswordHasher,
        rate_limiter: Callable[[], RateLimiter],
        ip_resolver: ClientIPResolver,
        secret_key: str,
        https_only: bool,
    ) -> None:
        super().__init__(
            secret_key,
            session_cookie=ADMIN_SESSION_COOKIE,
            path=ADMIN_SESSION_PATH,
            same_site="strict",
            https_only=https_only,
            max_age=ADMIN_SESSION_MAX_AGE,
        )
        self._session_factory = session_factory
        self._hasher = hasher
        self._rate_limiter = rate_limiter
        self._ip_resolver = ip_resolver
        # 로그인 화면을 그릴 sqladmin 템플릿 엔진. Admin 이 만든 뒤 조립부가 넣는다.
        self.templates: Any = None

    def csrf_token(self, request: Request) -> str:
        """세션의 CSRF 토큰을 돌려준다. 없으면 만들어 넣는다(로그인 템플릿의 전역 함수)."""
        token = request.session.get(CSRF_FIELD)
        if not isinstance(token, str) or not token:
            token = secrets.token_urlsafe(32)
            request.session[CSRF_FIELD] = token
        return token

    @staticmethod
    def _csrf_valid(request: Request, submitted: object) -> bool:
        expected = request.session.get(CSRF_FIELD)
        if not isinstance(expected, str) or not expected or not isinstance(submitted, str):
            return False
        # bytes 로 비교한다 — str 끼리는 비 ASCII 입력에서 TypeError 가 난다.
        return hmac.compare_digest(submitted.encode(), expected.encode())

    async def login(self, request: Request) -> Response | bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        ip = self._ip_resolver.resolve(request)
        log_extra = {"username": username[:_LOG_USERNAME_MAX], "client_ip": ip}

        # 레이트 리밋보다 먼저 본다 — 위조 요청이 피해자의 시도 횟수를 깎지 못하게.
        if not self._csrf_valid(request, form.get(CSRF_FIELD)):
            logger.warning("[AdminLogin] CSRF 토큰 불일치", extra=log_extra)
            return await self._render(request, CSRF_FAILED_MESSAGE, 403)

        limiter = self._rate_limiter()
        user_key = f"admin:rl:login:{ip}:{username.lower()}"
        window = jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
        for key, limit in (
            (f"admin:rl:login-ip:{ip}", jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS),
            (user_key, jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS),
        ):
            result = await limiter.hit(key, limit, window)
            if not result.allowed:
                logger.warning("[AdminLogin] 시도 횟수 초과", extra=log_extra)
                response = await self._render(request, THROTTLED_MESSAGE, 429)
                response.headers["Retry-After"] = str(result.retry_after)
                return response

        async with self._session_factory() as session:
            try:
                user = await verify_credentials(
                    UserRepository(session), self._hasher, username, password
                )
            except InvalidCredentialsException:
                user = None
            if user is None or not user.is_superuser:
                logger.warning("[AdminLogin] 로그인 실패", extra=log_extra)
                return await self._render(request, InvalidCredentialsException.message, 400)
            # 옛 형식 해시를 새 해시로 바꿨다면 그 UPDATE 를 확정한다.
            await session.commit()
            user_id = user.id

        await limiter.reset(user_key)
        request.session.clear()
        request.session["user_id"] = user_id
        logger.info("[AdminLogin] 로그인 성공", extra={**log_extra, "user_id": user_id})
        return True

    async def authenticate(self, request: Request) -> bool:
        user_id = request.session.get("user_id")
        if not user_id:
            return False
        async with self._session_factory() as session:
            user = await UserRepository(session).get_by_id(user_id)
        if user is None or not user.is_active or not user.is_superuser:
            request.session.clear()
            return False
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def _render(self, request: Request, error: str, status_code: int) -> Response:
        response: Response = await self.templates.TemplateResponse(
            request, LOGIN_TEMPLATE, {"error": error}, status_code=status_code
        )
        return response
