"""refresh 토큰 회전·재사용 탐지 저장소 (service-hardening ADR-012).

키:
    auth:rt:{jti}             발급된(아직 쓰지 않은) refresh 토큰 → ``{"fam", "sub"}`` (TTL=refresh 만료)
    auth:user:{sub}:fams      사용자의 family 집합 (사용자 단위 폐기용)
    auth:fam:{fam}:revoked    폐기된 family 표시 (TTL=refresh 만료 — 그 뒤엔 토큰이 어차피 만료)

회전은 ``GETDEL`` 한 번으로 jti 를 소비한다. 같은 토큰이 동시에 두 번 와도 한쪽만 값을
받는다 — 다른 쪽은 "없음" 이 되어 재사용으로 처리된다. ``GETDEL`` 은 Redis 6.2 부터다(저장소 최소
버전은 rate limit 의 ``EXPIRE NX`` 때문에 7.0 — ``app/core/redis.py`` 의 ``REDIS_MIN_VERSION``).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import TypedDict, cast

from redis.asyncio import Redis


class RefreshRecord(TypedDict):
    fam: str
    sub: str


class RefreshTokenStore:
    """발급된 refresh 토큰과 폐기된 family 를 Redis 에 둔다."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _token_key(jti: str) -> str:
        return f"auth:rt:{jti}"

    @staticmethod
    def _user_key(sub: str) -> str:
        return f"auth:user:{sub}:fams"

    @staticmethod
    def _revoked_key(fam: str) -> str:
        return f"auth:fam:{fam}:revoked"

    async def register(self, jti: str, sub: str, fam: str) -> None:
        """새로 발급한 refresh 토큰을 기록한다."""
        record = json.dumps(RefreshRecord(fam=fam, sub=sub))
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(self._token_key(jti), record, ex=self._ttl)
            pipe.sadd(self._user_key(sub), fam)
            pipe.expire(self._user_key(sub), self._ttl)
            await pipe.execute()

    async def consume(self, jti: str) -> RefreshRecord | None:
        """jti 를 소비한다. 이미 쓰였거나 모르는 jti 면 None(= 재사용)."""
        raw = await self._redis.getdel(self._token_key(jti))
        if raw is None:
            return None
        record: RefreshRecord = json.loads(raw)
        return record

    async def revoke_family(self, fam: str) -> None:
        """family 를 폐기한다 — 그 family 의 남은 토큰은 회전할 수 없다."""
        await self._redis.set(self._revoked_key(fam), 1, ex=self._ttl)

    async def is_family_revoked(self, fam: str) -> bool:
        return bool(await self._redis.exists(self._revoked_key(fam)))

    async def revoke_user(self, sub: str) -> None:
        """사용자의 모든 family 를 폐기한다(비활성화·강등·비밀번호 해시 변경·삭제 — ``revocation_for``)."""
        # redis-py 의 SMEMBERS 반환 타입은 동기·비동기 클라이언트 합집합이라 좁혀 준다.
        families = await cast(Awaitable[set[bytes]], self._redis.smembers(self._user_key(sub)))
        async with self._redis.pipeline(transaction=True) as pipe:
            for fam in families:
                pipe.set(self._revoked_key(fam.decode()), 1, ex=self._ttl)
            pipe.delete(self._user_key(sub))
            await pipe.execute()
