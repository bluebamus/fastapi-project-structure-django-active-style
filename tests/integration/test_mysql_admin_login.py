"""MySQL 8.4 — 실제 ``python -m scripts.create_superuser`` 로 만든 계정으로 /admin 로그인 (admin-login).

스크립트는 별도 프로세스로 돌려 운영과 같은 경로(설정 로드 → ``background_db_session`` → Argon2)를
지난다. 사용자명은 실행마다 임의로 만든다. 관리 앱은 ``tests/test_admin_login.py`` 와 같은 조립에
MySQL 세션 팩토리만 넣는다.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)
from tests.test_admin_login import PASSWORD, build_admin_app, csrf_token

pytestmark = pytest.mark.mysql

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_superuser(username: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ENV": "test",
        "MYSQL_HOST": MYSQL_HOST,
        "MYSQL_PORT": str(MYSQL_PORT),
        "MYSQL_USER": MYSQL_USER,
        "MYSQL_PASSWORD": MYSQL_PASSWORD,
        "MYSQL_DATABASE": MYSQL_DATABASE,
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.create_superuser",
            "--username",
            username,
            "--email",
            f"{username}@example.com",
            "--password-stdin",
        ],
        input=PASSWORD + "\n",
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


async def test_cli_superuser_can_log_in_to_admin_on_mysql(mysql_session_maker):
    username = f"adm_{uuid.uuid4().hex[:10]}"
    completed = await asyncio.to_thread(_create_superuser, username)
    assert completed.returncode == 0, completed.stderr[-2000:]

    @asynccontextmanager
    async def session_factory() -> AsyncIterator[AsyncSession]:
        async with mysql_session_maker() as session:
            yield session

    engine = mysql_session_maker.kw["bind"]
    app = build_admin_app(engine, session_factory, FakeAsyncRedis())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/admin/")
        assert first.status_code == 302 and first.headers["location"].endswith("/admin/login")
        token = await csrf_token(client)
        wrong = await client.post(
            "/admin/login",
            data={"username": username, "password": "wrong-password-1", "csrf_token": token},
        )
        assert wrong.status_code == 400
        ok = await client.post(
            "/admin/login",
            data={"username": username, "password": PASSWORD, "csrf_token": token},
        )
        assert ok.status_code == 302
        assert (await client.get("/admin/")).status_code == 200
        assert (await client.get("/admin/logout")).status_code == 302
        assert (await client.get("/admin/")).status_code == 302
