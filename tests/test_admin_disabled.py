"""ADMIN_DISABLED=true — 관리 화면의 흔적이 앱 어디에도 없다 (admin-login ADR-007).

깨끗한 서브프로세스에서 ``ADMIN_DISABLED=true``·``DEBUG=true``(문서 노출) 로 ``main`` 을 띄우고,
알려진 공개 경로를 돌며 상태·본문·헤더를 모은다. 같은 프로세스는 이미 관리 화면을 켠 ``main`` 을
import 했으므로 판별할 수 없다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

PROBES = [
    ("GET", "/admin"),
    ("GET", "/admin/"),
    ("GET", "/admin/login"),
    ("POST", "/admin/login"),
    ("GET", "/admin/logout"),
    ("GET", "/admin/statics/css/main.css"),
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/ready"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/does-not-exist"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/me"),
]

CHILD = textwrap.dedent(
    """
    import asyncio, json, sys

    import main
    from httpx import ASGITransport, AsyncClient

    PROBES = json.loads(sys.argv[1])

    async def probe():
        out = []
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for method, path in PROBES:
                r = await client.request(method, path)
                out.append({
                    "probe": f"{method} {path}",
                    "status": r.status_code,
                    "body": r.text,
                    "headers": [f"{k}: {v}" for k, v in r.headers.items()],
                })
        return out

    result = {
        "responses": asyncio.run(probe()),
        "sqladmin_loaded": any(n == "sqladmin" or n.startswith("sqladmin.") for n in sys.modules),
        "auth_backend_loaded": "app.features.auth.admin_auth" in sys.modules,
        "middlewares": [m.cls.__name__ for m in main.app.user_middleware],
        "admin_attr": hasattr(main, "admin"),
    }
    print("RESULT:" + json.dumps(result))
    """
)


def _run_child(*args: str) -> str:
    env = {**os.environ, "ADMIN_DISABLED": "true", "DEBUG": "true", "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(
        [sys.executable, "-c", *args],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    return completed.stdout + completed.stderr


@pytest.fixture(scope="module")
def disabled_app() -> dict:
    output = _run_child(CHILD, json.dumps(PROBES))
    result_line = next(line for line in output.splitlines() if line.startswith("RESULT:"))
    return json.loads(result_line[len("RESULT:") :])


def test_admin_paths_are_not_mounted(disabled_app):
    statuses = {r["probe"]: r["status"] for r in disabled_app["responses"]}
    for probe in [f"{m} {p}" for m, p in PROBES if p.startswith("/admin")]:
        # 마운트가 없으니 라우터 단계의 404(POST 도 405 가 아니라 404)다.
        assert statuses[probe] == 404, probe


def test_no_response_mentions_the_admin_path(disabled_app):
    offenders = [
        r["probe"]
        for r in disabled_app["responses"]
        if "/admin" in r["body"] or any("/admin" in header for header in r["headers"])
    ]
    assert offenders == []
    # 대조군 — 검사가 실제 문서·스키마를 보고 있다(빈 본문으로 헛통과하지 않게).
    bodies = {r["probe"]: r["body"] for r in disabled_app["responses"]}
    assert "/api/v1/auth/login" in bodies["GET /openapi.json"]
    assert "<" in bodies["GET /docs"]


def test_startup_log_does_not_mention_the_admin_path():
    # 요청 로그는 요청 경로를 그대로 싣는다 — 기동만 따로 띄워 본다.
    logs = _run_child("import main")
    assert "ADMIN_DISABLED=true" in logs
    assert "/admin" not in logs


def test_no_admin_session_middleware_or_backend_is_built(disabled_app):
    assert disabled_app["sqladmin_loaded"] is False
    assert disabled_app["auth_backend_loaded"] is False
    assert "SessionMiddleware" not in disabled_app["middlewares"]
    assert disabled_app["admin_attr"] is False
