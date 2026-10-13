"""Redis 최소 버전 확인 (log-redaction-fixes ADR-005).

최소 버전은 코드가 보내는 명령에서 나온다 — `EXPIRE ... NX`(rate limit) 가 7.0 이라 7.0 이다.
낮은 Redis 에서는 기동은 되지만 첫 로그인 시도가 `ResponseError` 로 500 이 되므로, lifespan 이
연결 직후 `INFO server` 로 확인해 멈춘다. INFO 가 막힌 관리형 Redis 는 경고 후 계속한다.
"""

import logging
import re
from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from app.core.redis import REDIS_MIN_VERSION, RedisVersionError, check_redis_version

APP_DIR = Path(__file__).resolve().parents[2] / "app"


class _InfoRedis:
    def __init__(self, info=None, error=None):
        self._info = info
        self._error = error

    async def info(self, section):
        assert section == "server"
        if self._error is not None:
            raise self._error
        return self._info


@pytest.mark.parametrize("version", ["6.2.14", "6.0.0", "5.0.7"])
async def test_version_below_minimum_refuses_startup(version):
    with pytest.raises(RedisVersionError, match=re.escape(version)):
        await check_redis_version(_InfoRedis({"redis_version": version}))


@pytest.mark.parametrize("version", ["7.0.0", "7.4.2", "8.0.1"])
async def test_version_at_or_above_minimum_passes(version, caplog):
    with caplog.at_level(logging.INFO):
        await check_redis_version(_InfoRedis({"redis_version": version}))

    assert any(version in r.getMessage() for r in caplog.records)


async def test_info_blocked_warns_and_continues(caplog):
    """관리형 Redis 가 INFO 를 거부하면(ResponseError) 경고만 남긴다. fakeredis 도 이 경로다."""
    with caplog.at_level(logging.WARNING):
        await check_redis_version(
            _InfoRedis(error=ResponseError("NOPERM this user has no permissions"))
        )

    assert [r.levelno for r in caplog.records if "Redis 버전" in r.getMessage()] == [
        logging.WARNING
    ]


async def test_unreadable_version_warns_and_continues(caplog):
    with caplog.at_level(logging.WARNING):
        await check_redis_version(_InfoRedis({}))

    assert any("Redis 버전" in r.getMessage() for r in caplog.records)


async def test_connection_error_is_not_swallowed():
    """INFO 거부가 아닌 연결 오류는 그대로 올린다 — Redis 는 필수다."""
    with pytest.raises(RedisConnectionError):
        await check_redis_version(_InfoRedis(error=RedisConnectionError("down")))


def _app_sources() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in APP_DIR.rglob("*.py"))


def test_minimum_version_covers_the_commands_the_code_sends():
    """계약: 소스가 쓰는 명령의 도입 버전 ≤ REDIS_MIN_VERSION.

    `expire(..., nx=True)` 는 7.0, `getdel(` 은 6.2. 명령을 더했는데 상수를 안 올리면 여기서 깨진다.
    """
    source = _app_sources()
    required = [(2, 6)]
    if re.search(r"\.expire\([^)]*nx=True", source):
        required.append((7, 0))
    if ".getdel(" in source:
        required.append((6, 2))

    assert len(required) > 1, "명령 탐지가 아무것도 찾지 못했습니다 — 정규식을 확인하세요."
    assert max(required) <= REDIS_MIN_VERSION
    assert REDIS_MIN_VERSION == max(required), "최소 버전이 실제 필요보다 높습니다."
