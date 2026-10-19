"""/admin 관리 세션 — Redis 서버 세션 (admin-session-hardening ADR-001·ADR-002).

쿠키에는 무작위 세션 ID(``secrets.token_urlsafe(32)``)만 있고, 내용은 Redis 에 둔다.
로그아웃·강등·비활성화·삭제 시 서버에서 즉시 지우므로 복사해 둔 쿠키도 그 순간 죽는다.

키:
    admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}   JSON ``{"data", "user_id", "created_at"}``
                                                        TTL = min(미사용 만료, 절대 만료까지 남은 시간)
    admin:user_sessions:{user_id}                       그 사용자의 세션 키 집합(SET, TTL=절대 만료)

Redis 에는 세션 ID 원문이 없다 — Redis 내용이 새도 쿠키를 만들 수 없다. ``SESSION_SECRET_KEY`` 를
바꾸면 모든 관리 세션이 무효가 된다.

``AdminSessionStore`` 는 저장·조회·삭제·사용자별 폐기를, ``RedisSessionMiddleware`` 는 쿠키↔
``scope["session"]`` 연결을 맡는다. 저장소는 미들웨어·사용자 서비스(폐기 훅)·테스트가 함께 쓴다.
이 모듈은 sqladmin 을 import 하지 않는다(사용자 서비스가 쓰므로 core 에 둔다).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection, Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logs import get_logger

logger = get_logger("admin_session")

ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_PATH = "/admin"
# 로그인 성공 등 세션 ID 를 새로 발급해야 할 때 scope 에 세우는 표시(``rotate_session``).
_ROTATE_FLAG = "admin_session.rotate"
# 이 요청의 세션 저장소 — 관리 화면 코드(예: UserAdmin 의 폐기 훅)가 ``session_store_of`` 로 꺼낸다.
_STORE_KEY = "admin_session.store"
# 요청 안의 폐기가 Redis 오류로 실패했다는 표시 — 응답을 503 으로 바꾼다(``revoke_user_sessions``).
_REVOKE_FAILED = "admin_session.revoke_failed"
STORE_UNAVAILABLE_MESSAGE = "관리 세션 저장소(Redis)를 사용할 수 없습니다. 잠시 후 다시 시도하세요."


@dataclass(frozen=True)
class SessionRecord:
    data: dict[str, Any]
    created_at: float


class AdminSessionStore:
    """관리 세션을 Redis 에 저장·조회·삭제하고, 사용자 단위로 한 번에 폐기한다.

    Args:
        redis: Redis 클라이언트.
        secret_key: ``SESSION_SECRET_KEY`` — 세션 ID 를 Redis 키로 바꾸는 HMAC 키.
        max_age: 절대 만료(초). 생성 시각부터 세고 연장하지 않는다.
        idle: 미사용 만료(초). 요청마다 TTL 을 이 값으로(절대 만료 이내) 다시 맞춘다.
        clock: 현재 epoch 초(테스트가 시계를 바꿔 넣는다).
    """

    def __init__(
        self,
        redis: Redis,
        secret_key: str,
        *,
        max_age: int,
        idle: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._secret = secret_key.encode()
        self.max_age = max_age
        self.idle = idle
        self._clock = clock

    def now(self) -> float:
        return self._clock()

    def key(self, sid: str) -> str:
        digest = hmac.new(self._secret, sid.encode(), hashlib.sha256).hexdigest()
        return f"admin:sess:{digest}"

    @staticmethod
    def user_key(user_id: object) -> str:
        return f"admin:user_sessions:{user_id}"

    def _ttl(self, created_at: float) -> int:
        """남은 절대 만료와 미사용 만료 중 짧은 쪽(정수 초, 0 이하면 만료)."""
        return min(self.idle, int(created_at + self.max_age - self._clock()))

    async def load(self, sid: str) -> SessionRecord | None:
        """세션을 읽는다. 없거나 절대 만료가 지났으면 None(지난 것은 지운다)."""
        raw = await self._redis.get(self.key(sid))
        if raw is None:
            return None
        payload = json.loads(raw)
        record = SessionRecord(data=payload["data"], created_at=float(payload["created_at"]))
        if self._ttl(record.created_at) <= 0:
            await self.delete(sid, record.data.get("user_id"))
            return None
        return record

    async def save(
        self, sid: str, data: dict[str, Any], created_at: float, *, create: bool = False
    ) -> None:
        """내용을 쓰고 TTL 을 다시 맞춘다. 로그인한 세션이면 사용자 인덱스에 올린다.

        ``create=False``(기존 세션)는 키가 아직 있을 때만 쓴다(``SET XX``) — 같은 요청 안에서
        폐기된 세션(예: 관리 화면에서 자기 자신을 강등)을 응답 끝의 저장이 되살리지 않게.
        """
        ttl = self._ttl(created_at)
        user_id = data.get("user_id")
        if ttl <= 0:
            await self.delete(sid, user_id)
            return
        key = self.key(sid)
        payload = json.dumps({"data": data, "user_id": user_id, "created_at": created_at})
        if not await self._redis.set(key, payload, ex=ttl, xx=not create):
            return
        if user_id:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.sadd(self.user_key(user_id), key)
                pipe.expire(self.user_key(user_id), self.max_age)
                await pipe.execute()

    async def touch(self, sid: str, created_at: float) -> None:
        """내용은 그대로 두고 미사용 만료만 다시 센다(절대 만료는 넘지 않는다)."""
        ttl = self._ttl(created_at)
        if ttl > 0:
            await self._redis.expire(self.key(sid), ttl)
        else:
            await self._redis.delete(self.key(sid))

    async def delete(self, sid: str, user_id: object = None) -> None:
        key = self.key(sid)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if user_id:
                pipe.srem(self.user_key(user_id), key)
            await pipe.execute()

    async def revoke_user(self, user_id: object) -> None:
        """그 사용자의 관리 세션을 모두 지운다(비활성화·강등·삭제 — 다른 브라우저 포함)."""
        user_key = self.user_key(user_id)
        # redis-py 의 SMEMBERS 반환 타입은 동기·비동기 합집합이라 좁혀 준다.
        keys = await cast(Awaitable[set[bytes]], self._redis.smembers(user_key))
        await self._redis.delete(user_key, *keys)


def session_store_of(request: Request) -> AdminSessionStore:
    """이 요청에 ``RedisSessionMiddleware`` 가 쓰는 세션 저장소(관리 하위 앱 안에서만 있다)."""
    store = request.scope.get(_STORE_KEY)
    if not isinstance(store, AdminSessionStore):
        raise RuntimeError("관리 세션 저장소가 없습니다 — /admin 하위 앱 밖에서 불렀다.")
    return store


async def revoke_user_sessions(request: Request, user_id: object) -> None:
    """관리 화면 요청 안에서 그 사용자의 세션을 모두 폐기한다(``AdminSessionStore.revoke_user``).

    Redis 오류는 다시 올리되, 먼저 이 응답을 503 으로 바꾸라고 표시한다 — sqladmin 은 모델
    훅의 예외를 삼켜 400 폼·목록 오류로 그리므로, 표시가 없으면 폐기 실패가 성공처럼 지나간다.
    """
    try:
        await session_store_of(request).revoke_user(user_id)
    except RedisError:
        request.scope[_REVOKE_FAILED] = True
        raise


def rotate_session(request: Request) -> None:
    """이 응답에서 세션 ID 를 새로 발급하고 이전 키를 지우라고 미들웨어에 알린다(세션 고정 방지)."""
    request.scope[_ROTATE_FLAG] = True


class RedisSessionMiddleware:
    """``admin_session`` 쿠키의 세션 ID 로 Redis 세션을 읽어 ``scope["session"]`` 에 dict 로 둔다.

    ``request.session`` 인터페이스는 starlette ``SessionMiddleware`` 와 같다. 응답 시작 때:

    - 세션이 비었으면(로그아웃·인증 실패) Redis 키를 지우고 쿠키를 지운다.
    - 새 세션이거나 ``rotate_session`` 이 불렸으면 새 ID 를 발급하고 이전 키를 지운다.
    - 내용이 바뀌었으면 저장, 아니면 TTL 만 갱신한다(미사용 만료).

    쿠키에 ID 가 있는데 Redis 에 없으면(만료·폐기) 빈 세션으로 다루고 쿠키를 지운다.
    Redis 오류는 삼키지 않는다 — 응답 전이면 503 으로 끝낸다(fail-closed).

    Args:
        app: 다음 ASGI 앱.
        store: 요청마다 ``AdminSessionStore`` 를 돌려주는 함수. Redis 클라이언트는 lifespan 이
            만들어서 조립 시점에는 아직 없다.
        https_only: 쿠키 Secure 플래그(staging/production).
    """

    def __init__(
        self, app: ASGIApp, *, store: Callable[[], AdminSessionStore], https_only: bool
    ) -> None:
        self.app = app
        self._store = store
        self._flags = "; httponly; samesite=strict" + ("; secure" if https_only else "")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False
        try:
            store = self._store()
            sid = HTTPConnection(scope).cookies.get(ADMIN_SESSION_COOKIE)
            record = await store.load(sid) if sid else None
            initial = dict(record.data) if record else {}
            scope["session"] = dict(initial)
            scope[_STORE_KEY] = store

            async def send_wrapper(message: Message) -> None:
                nonlocal started
                if message["type"] == "http.response.start":
                    if scope.get(_REVOKE_FAILED):
                        raise RedisError("관리 세션 폐기 실패")
                    cookie = await self._commit(scope, store, sid, record, initial)
                    if cookie:
                        MutableHeaders(scope=message).append("Set-Cookie", cookie)
                    started = True
                await send(message)

            await self.app(scope, receive, send_wrapper)
        except RedisError as exc:
            # 저장소 함수는 lifespan 전·후(클라이언트 없음)에도 RedisError 를 올린다 — 통과시키지 않는다.
            if started:
                raise
            logger.error("[AdminSession] 세션 저장소 오류 — 503: %s", type(exc).__name__)
            await PlainTextResponse(STORE_UNAVAILABLE_MESSAGE, status_code=503)(
                scope, receive, send
            )

    async def _commit(
        self,
        scope: Scope,
        store: AdminSessionStore,
        sid: str | None,
        record: SessionRecord | None,
        initial: dict[str, Any],
    ) -> str | None:
        session: dict[str, Any] = scope["session"]
        if not session:
            if record is not None and sid:
                await store.delete(sid, record.data.get("user_id"))
            return self._clear_cookie() if sid else None
        if record is None or scope.get(_ROTATE_FLAG):
            if record is not None and sid:
                await store.delete(sid, record.data.get("user_id"))
            new_sid = secrets.token_urlsafe(32)
            await store.save(new_sid, session, store.now(), create=True)
            return (
                f"{ADMIN_SESSION_COOKIE}={new_sid}; path={ADMIN_SESSION_PATH}; "
                f"Max-Age={store.max_age}{self._flags}"
            )
        assert sid is not None
        if session != initial:
            await store.save(sid, session, record.created_at)
        else:
            await store.touch(sid, record.created_at)
        return None

    def _clear_cookie(self) -> str:
        return (
            f"{ADMIN_SESSION_COOKIE}=null; path={ADMIN_SESSION_PATH}; "
            f"expires=Thu, 01 Jan 1970 00:00:00 GMT; max-age=0{self._flags}"
        )
