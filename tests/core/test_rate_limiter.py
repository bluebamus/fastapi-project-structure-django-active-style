"""`RateLimiter` — 허용·거부·Retry-After·창 만료·초기화 (service-hardening F1, ADR-013)."""

import asyncio

import pytest
from fakeredis import FakeAsyncRedis

from app.core.security.rate_limiter import RateLimiter, RateLimitResult


@pytest.fixture
def redis():
    return FakeAsyncRedis()


@pytest.fixture
def limiter(redis):
    return RateLimiter(redis)


async def test_allows_up_to_limit_then_denies(limiter):
    results = [await limiter.hit("k", 3, 60) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[0] == RateLimitResult(allowed=True, retry_after=0)
    assert 0 < results[-1].retry_after <= 60


async def test_window_starts_on_first_hit_only(limiter, redis):
    """뒤따르는 hit 이 TTL 을 늘리면 창이 끝나지 않는다(EXPIRE NX)."""
    await limiter.hit("k", 10, 60)
    await redis.expire("k", 5)
    await limiter.hit("k", 10, 60)
    assert await redis.ttl("k") <= 5


async def test_keys_are_independent(limiter):
    await limiter.hit("a", 1, 60)
    assert (await limiter.hit("a", 1, 60)).allowed is False
    assert (await limiter.hit("b", 1, 60)).allowed is True


async def test_window_expiry_allows_again(limiter):
    await limiter.hit("k", 1, 1)
    assert (await limiter.hit("k", 1, 1)).allowed is False
    await asyncio.sleep(1.1)
    assert (await limiter.hit("k", 1, 1)).allowed is True


async def test_reset_clears_the_counter(limiter):
    await limiter.hit("k", 1, 60)
    await limiter.reset("k")
    assert (await limiter.hit("k", 1, 60)).allowed is True
