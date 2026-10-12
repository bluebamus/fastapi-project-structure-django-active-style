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

from app.core.db.session import READINESS_TIMEOUT_SECONDS
from app.core.exception import ServiceUnavailableException

__all__ = ["get_redis", "ping_redis"]


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
