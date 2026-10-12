"""Redis 주입 provider `get_redis` (service-hardening 단계 E, ADR-008).

클라이언트는 lifespan 이 소유하고, 요청 쪽은 provider 하나로 받는다. 클라이언트가
없으면(기동 전·종료 후) 조용히 None 을 건네지 않고 503 이다 — Redis 는 필수다(C-4).
"""

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.exception import ServiceUnavailableException
from app.core.redis import get_redis


def _request_with(redis):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))


def test_get_redis_returns_the_lifespan_client():
    client = object()

    assert get_redis(_request_with(client)) is client


@pytest.mark.parametrize("state", [SimpleNamespace(redis=None), SimpleNamespace()])
def test_get_redis_raises_503_when_client_is_missing(state):
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    with pytest.raises(ServiceUnavailableException) as caught:
        get_redis(request)

    assert caught.value.status_code == 503


def test_get_redis_is_injectable_and_overridable():
    """라우트는 `Depends(get_redis)` 로 받고, 테스트는 override 로 가짜를 넣는다."""
    app = FastAPI()
    fake = SimpleNamespace(name="fake-redis")

    @app.get("/probe")
    async def probe(redis=Depends(get_redis)):
        return {"name": redis.name}

    app.dependency_overrides[get_redis] = lambda: fake

    assert TestClient(app).get("/probe").json() == {"name": "fake-redis"}
