"""Redis 고정 창 rate limit (service-hardening ADR-013).

``INCR`` 와 첫 hit 의 ``EXPIRE NX`` 를 한 트랜잭션(MULTI)으로 보낸다 — 둘 사이에 프로세스가
죽어 TTL 없는 카운터가 남으면 그 키는 영구 차단된다.

``EXPIRE ... NX`` 는 Redis 7.0 에서 생겼다 — 이 명령이 저장소의 최소 Redis 버전을 정한다
(``app/core/redis.py`` 의 ``REDIS_MIN_VERSION``, 기동 시 확인).
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    #: 거부됐을 때 창이 끝날 때까지 남은 초. 허용이면 0.
    retry_after: int


class RateLimiter:
    """키별 요청 수를 고정 창으로 센다."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window: int) -> RateLimitResult:
        """한 번 센다. 창 안에서 ``limit`` 번째까지 허용한다."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
        if count <= limit:
            return RateLimitResult(allowed=True, retry_after=0)
        return RateLimitResult(allowed=False, retry_after=ttl if ttl > 0 else window)

    async def reset(self, key: str) -> None:
        await self._redis.delete(key)
