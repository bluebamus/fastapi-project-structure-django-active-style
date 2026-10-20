"""실물 Redis 가 필요한 테스트의 접속 대상은 명시돼야 한다 (integration-e2e W0).

기본값 6379 로 떨어지면 개발 머신에 떠 있는 남의 Redis 에 조용히 붙는다. 테스트가 띄운 자식
프로세스는 cwd 의 `.env` 를 읽으므로, fixture 가 확인한 대상을 env 로 넘기지 않으면 `.env` 가
접속 대상을 바꾼다. 이 파일은 네트워크에 닿지 않는다(닫힌 포트·로컬 리스너만 쓴다).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.redis_target import child_env, redis_target

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize("missing", ["REDIS_HOST", "REDIS_PORT"])
def test_unspecified_target_fails_instead_of_defaulting(monkeypatch, missing):
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "16392")
    monkeypatch.delenv(missing)

    with pytest.raises(pytest.fail.Exception, match="REDIS_HOST.*REDIS_PORT"):
        redis_target()


def test_specified_but_unreachable_target_fails(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", str(_closed_port()))

    with pytest.raises(pytest.fail.Exception, match="연결"):
        redis_target()


def test_specified_reachable_target_is_returned(monkeypatch):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
        monkeypatch.setenv("REDIS_PORT", str(port))

        assert redis_target() == ("127.0.0.1", port)


def test_child_process_ignores_a_dotenv_redis(tmp_path):
    """자식이 cwd 의 `.env`(6379)를 읽어도 fixture 가 준 대상이 이긴다."""
    (tmp_path / ".env").write_text("REDIS_HOST=localhost\nREDIS_PORT=6379\n", encoding="utf-8")
    env = child_env(("127.0.0.1", 16392), base={"PATH": os.environ.get("PATH", ""), "ENV": "test"})
    env["PYTHONPATH"] = str(_REPO_ROOT)
    env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")  # Windows 의 소켓 초기화에 필요

    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "from config import redis_settings; print(redis_settings.REDIS_URL)",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout

    assert out.strip().endswith("127.0.0.1:16392/0")
