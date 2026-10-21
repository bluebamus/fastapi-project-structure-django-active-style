"""SQLAdmin(``/admin``) 로그인 백엔드 (admin-login ADR-002~ADR-004).

``/admin`` 은 **활성 슈퍼유저**만 쓴다. 계정은 ``scripts/create_superuser.py`` 로 만든다.

- 로그인: 폼 CSRF 토큰 확인(security-ops-hardening ADR-003) → 폼 username/password → rate limit(키 접두사 ``admin:rl:`` — API 로그인과 따로 센다,
  한도 설정은 API 와 같은 ``AUTH_LOGIN_*``) → API 로그인과 같은 ``verify_credentials`` →
  슈퍼유저 확인. 성공하면 세션을 비우고 사용자 id 와 새 CSRF 토큰만 넣은 뒤 세션 ID 를 회전한다
  (세션 고정 방지 — ``rotate_session``). 실패 사유는 구분하지 않는다(계정 열거 방지).
  한도 초과는 로그인 화면을 429 + ``Retry-After`` 로.
- 인증: 매 요청 세션의 id 로 DB 를 다시 본다 — 강등·비활성화가 다음 요청부터 반영된다
  (서버 세션 즉시 폐기와 이중 방어).
- 세션: ``app/core/security/admin_session.py`` 의 Redis 서버 세션(admin-session-hardening ADR-001).
  쿠키 ``admin_session``(접속 로그가 읽는 ``SESSION_COOKIE_NAME`` 과 다르다)에는 무작위 세션 ID 만,
  ``Path=/admin``, ``SameSite=Strict``, HttpOnly, Max-Age=절대 만료, 배포 환경은 Secure.
- CSRF(synchronizer token, admin-session-hardening ADR-004): 세션에 ``secrets.token_urlsafe(32)``
  토큰 하나. 로그인 폼은 hidden 필드로 싣고 ``login`` 이 rate limit·자격 확인 **전에** 비교한다
  (없거나 다르면 403 으로 로그인 화면 재표시). 로그인 이후의 모든 상태 변경 요청(POST·PUT·PATCH·DELETE
  — 생성·수정·삭제·일괄 삭제·가져오기·로그아웃)은 ``AdminCsrfMiddleware`` 가 헤더 ``X-CSRF-Token``
  또는 폼 필드 ``csrf_token`` 을 같은 함수(``csrf_valid``)로 비교한다. 로그인 POST 는 미들웨어가
  건너뛰어 검사가 한 번만 일어난다. 토큰은 ``app/templates/admin/sqladmin/base.html`` 의 meta 와
  인라인 스크립트가 폼·fetch·XHR 에 붙인다.

이 모듈은 sqladmin 을 import 하므로 ``app/features/admin.py``(ADMIN_DISABLED=false 일 때만 로드)에서만
가져온다. 기능 패키지의 ``admin.py`` 가 아닌 이유: registry 는 그 이름을 ``admin_views`` 계약으로
읽는다.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.admin_session import (
    ADMIN_SESSION_COOKIE,
    AdminSessionStore,
    RedisSessionMiddleware,
    rotate_session,
)
from app.core.security.password_hasher import PasswordHasher
from app.core.security.rate_limiter import RateLimiter
from app.features.auth.exceptions import InvalidCredentialsException
from app.features.auth.services.auth_service import verify_credentials
from app.features.user.repositories.user_repository import UserRepository
from app.utils.logs import get_logger
from config import jwt_settings

logger = get_logger("admin_auth")

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

__all__ = ["ADMIN_SESSION_COOKIE", "AdminAuthBackend", "AdminCsrfMiddleware", "csrf_valid"]

LOGIN_TEMPLATE = "sqladmin/login.html"
THROTTLED_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."
CSRF_FAILED_MESSAGE = "요청이 만료되었습니다. 다시 시도하세요."
# 세션 키와 폼 필드 이름이 같다 — 템플릿의 hidden input name 과 맞춘다.
CSRF_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"
CSRF_REJECTED_MESSAGE = (
    "CSRF 토큰이 없거나 올바르지 않습니다. 관리 화면을 새로 고친 뒤 다시 시도하세요."
)
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")
# 로그에 싣는 사용자명 길이 상한 — 폼 값은 클라이언트 입력이라 길이를 믿지 않는다.
_LOG_USERNAME_MAX = 64
# CSRF 검사를 위해 버퍼링하는 폼 본문의 상한(e2e-policy-2 결정 7). 넘으면 413. 필드 하나의 상한(1 MiB)은
# starlette 폼 파서의 기본값(``max_part_size``)이 집행한다 — 넘으면 400.
MAX_FORM_BODY_BYTES = 10 * 1024 * 1024
BODY_TOO_LARGE_MESSAGE = "요청 본문이 너무 큽니다."
FORM_INVALID_MESSAGE = "폼을 읽을 수 없습니다(필드가 너무 크거나 형식이 잘못됐습니다)."


class AdminAuthBackend(AuthenticationBackend):
    """``/admin`` 의 로그인·로그아웃·요청별 인증.

    협력 객체는 모두 생성자로 받는다. 조립은 ``app/features/admin.py`` 가 한다.

    Args:
        session_factory: 요청 밖 세션 컨텍스트(운영은 ``background_db_session``).
        hasher: core ``PasswordHasher``.
        rate_limiter: 호출할 때마다 ``RateLimiter`` 를 돌려주는 함수. Redis 클라이언트는
            lifespan 이 만들어서(``app.state.redis``) 생성 시점에는 아직 없다.
        ip_resolver: ``TRUSTED_PROXY_HOPS`` 로 클라이언트 IP 를 고른다(API 로그인과 같다).
        session_store: 요청마다 ``AdminSessionStore`` 를 돌려주는 함수(Redis 는 lifespan 이 만든다).
        https_only: 쿠키 Secure 플래그(staging/production 에서 True).
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        hasher: PasswordHasher,
        rate_limiter: Callable[[], RateLimiter],
        ip_resolver: ClientIPResolver,
        session_store: Callable[[], AdminSessionStore],
        https_only: bool,
    ) -> None:
        # 부모 생성자는 starlette 서명 쿠키 SessionMiddleware 를 만든다 — 부르지 않고 대신
        # Redis 세션(바깥) → CSRF 검사(안쪽) 순서로 둔다. CSRF 는 세션의 토큰을 읽는다.
        self.middlewares = [
            Middleware(RedisSessionMiddleware, store=session_store, https_only=https_only),
            Middleware(AdminCsrfMiddleware),
        ]
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

    async def login(self, request: Request) -> Response | bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        ip = self._ip_resolver.resolve(request)
        log_extra = {"username": username[:_LOG_USERNAME_MAX], "client_ip": ip}

        # 레이트 리밋보다 먼저 본다 — 위조 요청이 피해자의 시도 횟수를 깎지 못하게.
        if not csrf_valid(request.session, form.get(CSRF_FIELD)):
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
        request.session[CSRF_FIELD] = secrets.token_urlsafe(32)
        rotate_session(request)
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


def csrf_valid(session: Mapping[str, Any], submitted: object) -> bool:
    """세션의 CSRF 토큰과 제출값을 상수 시간으로 비교한다(로그인·미들웨어가 함께 쓴다)."""
    expected = session.get(CSRF_FIELD)
    if not isinstance(expected, str) or not expected or not isinstance(submitted, str):
        return False
    # bytes 로 비교한다 — str 끼리는 비 ASCII 입력에서 TypeError 가 난다.
    return hmac.compare_digest(submitted.encode(), expected.encode())


class AdminCsrfMiddleware:
    """``/admin`` 의 상태 변경 요청(POST·PUT·PATCH·DELETE)에 세션의 CSRF 토큰을 요구한다.

    토큰은 헤더 ``X-CSRF-Token`` 을 먼저 보고, 없으면 폼 본문의 ``csrf_token`` 을 본다. 폼을 읽을
    때는 본문 전체를 버퍼링한 뒤 같은 바이트를 다운스트림에 다시 흘려보낸다(receive 재생) —
    sqladmin 이 폼을 한 번 더 읽어야 하기 때문이다. 버퍼링하는 본문은 10 MiB 까지다 — 넘으면 413
    (``Content-Length`` 로 먼저, 없거나 거짓이면 읽는 도중 누적 크기로). 1 MiB 를 넘는 필드나 깨진 폼은
    400 이다(e2e-policy-2 결정 7). 큰 업로드(CSV 가져오기)는 스크립트가 헤더로
    보내므로 버퍼링하지 않는다. 토큰 실패는 403 텍스트 응답(로그인 화면이 아니다 — 삭제 모달의 AJAX
    오류 처리도 텍스트를 그대로 띄운다). 로그인 POST 는 ``AdminAuthBackend.login`` 이 같은
    ``csrf_valid`` 로 직접 검사하므로 건너뛴다(한 요청에 한 번).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _UNSAFE_METHODS
            or _route_path(scope) == "/login"
        ):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        submitted: object = headers.get(CSRF_HEADER)
        if submitted is None and headers.get("content-type", "").startswith(_FORM_TYPES):
            # 먼저 Content-Length 로, 없거나 거짓이면 읽는 도중의 누적 크기로 판정한다.
            length = headers.get("content-length", "")
            body = (
                None
                if length.isdigit() and int(length) > MAX_FORM_BODY_BYTES
                else await _read_body(receive, MAX_FORM_BODY_BYTES)
            )
            if body is None:
                await _reject(scope, receive, send, 413, BODY_TOO_LARGE_MESSAGE)
                return
            receive = _replay(body, receive)
            try:
                submitted = await _form_token(scope, body)
            except (HTTPException, MultiPartException):
                await _reject(scope, receive, send, 400, FORM_INVALID_MESSAGE)
                return
        if not csrf_valid(scope.get("session") or {}, submitted):
            logger.warning(
                "[AdminCsrf] CSRF 토큰 없음·불일치 — 403",
                extra={"method": scope["method"], "path": scope["path"]},
            )
            await PlainTextResponse(CSRF_REJECTED_MESSAGE, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _route_path(scope: Scope) -> str:
    """마운트 지점(``root_path``)을 뺀 경로 — ``/admin/login`` → ``/login``."""
    path: str = scope["path"]
    root: str = scope.get("root_path", "")
    return path[len(root) :] if root and path.startswith(root) else path


async def _read_body(receive: Receive, limit: int) -> bytes | None:
    """본문을 끝까지 읽는다. 누적 크기가 ``limit`` 을 넘으면 그 자리에서 멈추고 None."""
    chunks = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


async def _reject(scope: Scope, receive: Receive, send: Send, status: int, message: str) -> None:
    logger.warning(
        "[AdminCsrf] 폼 본문 거부 — %d",
        status,
        extra={"method": scope["method"], "path": scope["path"]},
    )
    await PlainTextResponse(message, status_code=status)(scope, receive, send)


def _replay(body: bytes, receive: Receive) -> Receive:
    """버퍼링한 본문을 한 번 돌려주고, 그 뒤로는 원래 receive(연결 종료 감지)로 넘긴다."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if sent:
            return await receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return replay


async def _no_more() -> Message:
    return {"type": "http.disconnect"}


async def _form_token(scope: Scope, body: bytes) -> object:
    request = Request(scope, _replay(body, _no_more))
    # 1 MiB 를 넘는 필드·깨진 폼은 파서가 예외를 올린다 — 호출자가 400 으로 끝낸다.
    form = await request.form()
    try:
        return form.get(CSRF_FIELD)
    finally:
        await form.close()
