"""Redis 클라이언트 주입 provider (ADR-008).

Redis 는 필수 자원이다. 클라이언트는 lifespan(`manage_application_resources`)이 만들고
닫으며 `app.state.redis` 에 둔다. 요청 쪽은 이 모듈의 `get_redis` 하나로 받는다 —
기능 코드가 `app.state` 를 직접 뒤지면 "클라이언트가 아직 없거나 이미 닫힌 상태" 를
처리하는 방식이 호출처마다 갈라진다.

테스트는 `app.dependency_overrides[get_redis]` 로 가짜(fakeredis 등)를 넣거나,
`app.state.redis` 에 가짜 클라이언트를 둔다.
"""

from __future__ import annotations

import asyncio

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.db.session import READINESS_TIMEOUT_SECONDS
from app.core.exception import ServiceUnavailableException
from app.utils.logs import get_logger

__all__ = [
    "REDIS_MIN_VERSION",
    "RedisVersionError",
    "check_redis_version",
    "get_redis",
    "ping_redis",
]

logger = get_logger("redis")

# 지원하는 최소 Redis 버전 = 코드가 보내는 명령 중 가장 늦게 생긴 것의 버전.
#   SET key value EX ttl            2.6.12  refresh_store.register·revoke_family
#   SADD·SMEMBERS·DEL·INCR·TTL       ≤ 2.6   refresh_store·rate_limiter
#   GETDEL                           6.2     refresh_store.consume
#   EXPIRE key ttl NX                7.0     rate_limiter.hit          ← 최댓값
# 명령을 더하거나 빼면 이 표와 상수를 같이 고친다. tests/core/test_redis_version.py 가
# 소스의 `expire(..., nx=True)`·`getdel(` 사용과 이 상수를 대조한다.
REDIS_MIN_VERSION: tuple[int, int] = (7, 0)


class RedisVersionError(RuntimeError):
    """연결된 Redis 가 ``REDIS_MIN_VERSION`` 보다 낮다 — 기동을 멈춘다."""


async def check_redis_version(redis: Redis) -> None:
    """``INFO server`` 의 ``redis_version`` 이 최소 버전 이상인지 본다(lifespan 이 연결 직후 부른다).

    낮으면 기동을 멈춘다 — Redis 는 필수 자원이고(C-4), 낮은 버전에서는 기동은 되지만
    로그인 rate limit(`EXPIRE NX`)이 첫 요청에서 ``ResponseError`` 로 500 이 된다.
    관리형 Redis 처럼 INFO 가 막혀 있으면(명령 거부·이름 변경) 확인할 방법이 없으므로
    WARNING 만 남기고 계속한다. 연결 오류 등 그 밖의 예외는 그대로 올린다.

    Raises:
        RedisVersionError: 보고된 버전이 ``REDIS_MIN_VERSION`` 미만이다.
    """
    required = ".".join(map(str, REDIS_MIN_VERSION))
    try:
        info = await redis.info("server")
    except ResponseError as exc:
        logger.warning(
            "[Startup] Redis 버전 확인 불가(INFO 거부: %s) — %s 이상이라고 가정하고 계속합니다.",
            type(exc).__name__,
            required,
        )
        return
    reported = str(info.get("redis_version", ""))
    try:
        version = tuple(int(part) for part in reported.split(".")[:2])
    except ValueError:
        version = ()
    if len(version) < 2:
        logger.warning(
            "[Startup] Redis 버전을 읽지 못했습니다(redis_version=%r) — %s 이상이라고 가정하고 계속합니다.",
            reported,
            required,
        )
        return
    if version < REDIS_MIN_VERSION:
        raise RedisVersionError(
            f"Redis {reported} 은(는) 지원하지 않습니다 — {required} 이상이 필요합니다"
            " (rate limit 의 EXPIRE ... NX)."
        )
    logger.info("[Startup] Redis 버전 확인 완료: %s (최소 %s)", reported, required)


def get_redis(request: Request) -> Redis:
    """lifespan 이 소유한 Redis 클라이언트를 돌려준다.

    없으면(기동 전·종료 후, lifespan 없이 띄운 앱) 503 이다. Redis 는 필수라
    "없으면 건너뛴다" 는 경로를 만들지 않는다(C-4).

    Raises:
        ServiceUnavailableException: 클라이언트가 준비되지 않았다.
    """
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise ServiceUnavailableException("Redis 가 준비되지 않았습니다.")
    return redis


async def ping_redis(request: Request, timeout: float = READINESS_TIMEOUT_SECONDS) -> None:
    """readiness 용 Redis 왕복 1회. DB 점검과 같은 상한을 쓴다.

    Raises:
        ServiceUnavailableException: 클라이언트가 준비되지 않았다.
        TimeoutError: ``timeout`` 안에 응답하지 못했다.
        Exception: 연결 실패 등 드라이버 예외. 호출자는 응답에 원문을 싣지 않는다.
    """
    redis = get_redis(request)
    async with asyncio.timeout(timeout):
        await redis.ping()
