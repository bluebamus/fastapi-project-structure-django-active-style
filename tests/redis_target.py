"""실물 Redis 를 쓰는 테스트의 접속 대상 (integration-e2e W0).

대상은 반드시 환경 변수로 **명시**한다. 기본값(6379)으로 떨어지면 개발 머신에 떠 있는 남의
Redis 에 조용히 붙는다 — 실제로 그런 사고가 있었다. 테스트가 띄우는 자식 프로세스에는
``child_env`` 로 같은 대상을 넘겨, 자식이 읽는 `.env` 가 대상을 바꾸지 못하게 한다.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping

import pytest

_HOW = (
    "실물 Redis 가 필요한 테스트입니다. 접속 대상을 REDIS_HOST·REDIS_PORT 로 둘 다 명시하세요 "
    "(예: REDIS_HOST=127.0.0.1 REDIS_PORT=16392). 기본값 6379 는 다른 프로젝트의 Redis 일 수 "
    "있어 쓰지 않습니다."
)


def redis_target() -> tuple[str, int]:
    """명시된 Redis 대상을 돌려준다. 없거나 닿지 않으면 테스트를 실패시킨다(skip 아님)."""
    host = os.environ.get("REDIS_HOST")
    port = os.environ.get("REDIS_PORT")
    if not host or not port:
        pytest.fail(_HOW, pytrace=False)
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            pass
    except OSError as exc:
        pytest.fail(f"명시된 Redis {host}:{port} 에 연결할 수 없습니다: {exc}", pytrace=False)
    return host, int(port)


def child_env(target: tuple[str, int], base: Mapping[str, str] | None = None) -> dict[str, str]:
    """자식 프로세스 env — fixture 가 확인한 대상을 명시해 `.env` 를 덮는다."""
    env = dict(os.environ if base is None else base)
    env["REDIS_HOST"], env["REDIS_PORT"] = target[0], str(target[1])
    return env
