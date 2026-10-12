"""`RefreshTokenStore` — 등록·한 번만 소비·family 폐기·사용자 폐기 (service-hardening F1, ADR-012)."""

import pytest
from fakeredis import FakeAsyncRedis

from app.core.security.refresh_store import RefreshTokenStore

_TTL = 600


@pytest.fixture
def redis():
    return FakeAsyncRedis()


@pytest.fixture
def store(redis):
    return RefreshTokenStore(redis, _TTL)


async def test_register_then_consume_once(store, redis):
    await store.register("j1", "u1", "f1")
    assert 0 < await redis.ttl("auth:rt:j1") <= _TTL

    assert await store.consume("j1") == {"fam": "f1", "sub": "u1"}
    assert await store.consume("j1") is None  # 두 번째는 재사용


async def test_consume_unknown_jti_is_none(store):
    assert await store.consume("never-issued") is None


async def test_register_tracks_user_families(store, redis):
    await store.register("j1", "u1", "f1")
    await store.register("j2", "u1", "f2")
    assert await redis.smembers("auth:user:u1:fams") == {b"f1", b"f2"}
    assert 0 < await redis.ttl("auth:user:u1:fams") <= _TTL


async def test_revoke_family(store, redis):
    assert await store.is_family_revoked("f1") is False
    await store.revoke_family("f1")
    assert await store.is_family_revoked("f1") is True
    assert 0 < await redis.ttl("auth:fam:f1:revoked") <= _TTL


async def test_revoke_user_revokes_every_family(store):
    await store.register("j1", "u1", "f1")
    await store.register("j2", "u1", "f2")
    await store.register("j3", "u2", "f3")

    await store.revoke_user("u1")

    assert await store.is_family_revoked("f1")
    assert await store.is_family_revoked("f2")
    assert not await store.is_family_revoked("f3")


async def test_revoke_user_without_families_is_a_noop(store):
    await store.revoke_user("nobody")
