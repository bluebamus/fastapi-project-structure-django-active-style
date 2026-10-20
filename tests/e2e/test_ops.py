"""L6 운영·기동 — Alembic 왕복, create_superuser, 기동 거부, 로깅(경로별 형식·앱별 레벨·프로세스별 파일·회전·보관).

비밀값 grep(L6-4)은 모든 테스트가 끝난 뒤 test_inventory.py 가 산출물 전체에 대해 한다.
"""

from __future__ import annotations

import re
import secrets
import socketserver
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.e2e.conftest import DATABASE, DB_USER, HOST, REPO, Proc, app_env, run, wait_until

V1 = "/api/v1"

#: 프로젝트 로그 형식(LOG_FILE_FORMAT 기본값) — 시각(UTC)·레벨·[app=헤더]·[모듈:클래스:함수:줄].
LINE = re.compile(
    r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC\] (DEBUG|INFO|WARNING|ERROR|CRITICAL) +"
    r"\[app=[\w.-]+\] \[[^\]]+:[^\]]+:[^\]]+:\d+\] "
)
#: 다른 형식의 줄 시작(uvicorn·Celery 기본 형식 등) — 하나라도 있으면 경로별 형식이 갈라진 것이다.
FOREIGN = re.compile(
    r"^(INFO|WARNING|ERROR|DEBUG|CRITICAL):|^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+:"
)


def log_lines(path: Any) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []


def assert_one_format(lines: list[str], where: str) -> None:
    starts = [line for line in lines if line.startswith("[20") or FOREIGN.match(line)]
    assert starts, f"{where}: 로그 줄이 없습니다"
    bad = [line for line in starts if not LINE.match(line)]
    assert not bad, f"{where}: 프로젝트 형식이 아닌 줄 {bad[:3]}"


# ---------------------------------------------------------------------------
# 1. Alembic upgrade → downgrade base → upgrade, 스키마 비교
# ---------------------------------------------------------------------------


def _schema(stack: Any, database: str) -> list[tuple[Any, ...]]:
    with stack.mysql(root=True) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY"
            " FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s ORDER BY 1, 2",
            (database,),
        )
        columns = cur.fetchall()
        cur.execute(
            "SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, NON_UNIQUE FROM information_schema.STATISTICS"
            " WHERE TABLE_SCHEMA=%s ORDER BY 1, 2, 3",
            (database,),
        )
        return [*columns, *cur.fetchall()]


def test_alembic_round_trip_reproduces_the_schema(migrated, cover):
    stack = migrated
    scratch = f"{DATABASE}_mig"
    with stack.mysql(root=True) as conn, conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{scratch}`")
        cur.execute(f"CREATE DATABASE `{scratch}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"GRANT ALL ON `{scratch}`.* TO %s@'%%'", (DB_USER,))
    env = app_env(
        stack,
        ALEMBIC_DATABASE_URL=f"mysql+pymysql://{DB_USER}:{stack.db_password}@{HOST}:"
        f"{stack.primary_port}/{scratch}",
    )
    alembic = ["-m", "alembic", "-c", str(REPO / "alembic.ini")]
    try:
        for step in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
            done = run(stack, *alembic, *step, env=env)
            assert done.returncode == 0, done.stdout + done.stderr
            if step[0] == "downgrade":
                tables = {row[0] for row in _schema(stack, scratch)}
                assert tables <= {"alembic_version"}, tables
        assert _schema(stack, scratch) == _schema(stack, DATABASE)
    finally:
        with stack.mysql(root=True) as conn, conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{scratch}`")
    cover("L6", "1 Alembic 왕복·스키마 비교")


# ---------------------------------------------------------------------------
# 2. create_superuser: 생성(하네스)·중복(승격)·--set-password
# ---------------------------------------------------------------------------


def test_create_superuser_promotes_and_sets_password(api, stack, cover):
    user = api.user()
    promoted = run(stack, "-m", "scripts.create_superuser", "--username", user.username)
    assert promoted.returncode == 0, promoted.stdout + promoted.stderr
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT is_superuser FROM users WHERE id=%s", (user.id,))
        assert cur.fetchone() == (1,)
    new_password = "Pw-" + secrets.token_urlsafe(12)
    changed = run(
        stack,
        "-m",
        "scripts.create_superuser",
        "--username",
        user.username,
        "--set-password",
        "--password-stdin",
        stdin=new_password + "\n",
    )
    assert changed.returncode == 0, changed.stdout + changed.stderr
    assert new_password not in changed.stdout + changed.stderr
    assert api.login(user.username, user.password).status_code == 401
    assert api.login(user.username, new_password).status_code == 200
    # 측정(P-002): 스크립트의 비밀번호 변경이 기존 refresh 를 끊는가 — 정책 결정 대기라 값만 남긴다.
    survived = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": user.refresh})
    (stack.artifacts / "measure-set-password-refresh.txt").write_text(
        f"create_superuser --set-password 뒤 기존 refresh: {survived.status_code}\n",
        encoding="utf-8",
    )
    cover("L6", "2 create_superuser 생성·승격·비밀번호")


# ---------------------------------------------------------------------------
# 3. 기동 거부
# ---------------------------------------------------------------------------


class _FakeRedis(socketserver.ThreadingTCPServer):
    """INFO 에 낮은 버전을 답하는 작은 RESP 서버(127.0.0.1, 빈 포트)."""

    allow_reuse_address = True
    daemon_threads = True


class _FakeRedisHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        while True:
            head = self.rfile.readline()
            if not head:
                return
            args = []
            for _ in range(int(head[1:]) if head.startswith(b"*") else 0):
                size = int(self.rfile.readline()[1:])
                args.append(self.rfile.read(size + 2)[:-2].decode())
            command = args[0].upper() if args else ""
            if command == "PING":
                self.wfile.write(b"+PONG\r\n")
            elif command == "INFO":
                body = b"# Server\r\nredis_version:6.2.14\r\n"
                self.wfile.write(b"$%d\r\n%s\r\n" % (len(body), body))
            elif command == "HELLO":
                self.wfile.write(b"-ERR unknown command 'HELLO'\r\n")
            else:
                self.wfile.write(b"+OK\r\n")


@pytest.fixture
def old_redis() -> Iterator[int]:
    server = _FakeRedis((HOST, 0), _FakeRedisHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _boot(stack: Any, **overrides: str) -> subprocess.CompletedProcess[str]:
    """포트 0 에 uvicorn 을 띄워 본다 — 거부되면 바로 끝나고, 뜨면 60초 뒤 시간 초과로 실패한다."""
    return run(
        stack,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        HOST,
        "--port",
        "0",
        env=app_env(stack, **overrides),
        timeout=60,
    )


@pytest.mark.parametrize(
    "case",
    [
        "Redis 최소 버전 미달",
        "레거시 ADMIN 변수",
        "ADMIN_SESSION 미사용>절대",
        "ADMIN_SESSION 최소값 미만",
    ],
)
def test_startup_refusals(case, migrated, old_redis, cover):
    overrides, expected = {
        "Redis 최소 버전 미달": ({"REDIS_PORT": str(old_redis)}, "6.2.14"),
        "레거시 ADMIN 변수": ({"ADMIN": "true"}, "ADMIN"),
        "ADMIN_SESSION 미사용>절대": (
            {"ADMIN_SESSION_IDLE_SECONDS": "7200", "ADMIN_SESSION_MAX_AGE_SECONDS": "3600"},
            "ADMIN_SESSION_IDLE_SECONDS",
        ),
        "ADMIN_SESSION 최소값 미만": (
            {"ADMIN_SESSION_IDLE_SECONDS": "10"},
            "ADMIN_SESSION_IDLE_SECONDS",
        ),
    }[case]
    done = _boot(migrated, **overrides)
    output = done.stdout + done.stderr
    assert done.returncode != 0, output[-2000:]
    assert expected in output, output[-2000:]
    assert migrated.db_password not in output
    cover("L6", f"3 기동 거부 {case}")


def test_startup_refuses_an_undeclared_route(migrated, cover):
    from tests.core.test_access_policy import CHILD

    done = run(migrated, "-c", CHILD)
    assert "BLOCKED True" in done.stdout, done.stdout + done.stderr
    cover("L6", "3 기동 거부 접근 정책 미선언")


# ---------------------------------------------------------------------------
# 로깅: 경로별 같은 형식·헤더, 프로세스별 파일, 앱별 레벨, 회전·보관
# ---------------------------------------------------------------------------


@pytest.fixture
def restart(app):
    def apply(**overrides: str) -> None:
        app.stop()
        app.start(**overrides)

    yield apply
    app.stop()
    app.start()


def test_every_process_writes_one_format_to_its_own_file(app, api, stack, worker, cover):
    from tests.e2e.conftest import celery_client

    api.request("GET", f"{V1}/blog/posts")
    celery_client(stack).send_task("home.aggregate_access_stats").get(timeout=60)
    logs = stack.artifacts / "logs"
    app_log, celery_log = log_lines(logs / "app.log"), log_lines(logs / "celery.log")
    assert_one_format(app_log, "app.log")
    assert_one_format(celery_log, "celery.log")
    assert_one_format(log_lines(logs / "error.log") or app_log[:1], "error.log")
    # 콘솔(프로세스 stdout)도 같은 형식이다 — uvicorn·Celery 의 기본 형식이 섞이지 않는다
    assert_one_format(app.proc.output().splitlines(), "uvicorn 콘솔")
    assert_one_format(worker.proc.output().splitlines(), "Celery 콘솔")
    assert any("[app=uvicorn]" in line for line in app_log)
    assert any("[app=celery]" in line for line in celery_log)
    assert any("home.aggregate_access_stats" in line for line in celery_log)
    assert not any("[app=uvicorn]" in line for line in celery_log)
    assert not any("Task home." in line for line in app_log)
    cover("L6", "로깅 경로별 형식·헤더·프로세스별 파일")


def test_python_main_py_uses_the_same_format(restart, app, stack, cover):
    """`python main.py` 경로 — 앱을 내리고 같은 포트로 띄워 본다."""
    import httpx

    app.stop()
    proc = Proc(stack, "python-main", [str(REPO / "main.py")], app_env(stack))
    try:
        wait_until(
            lambda: _get(httpx, f"{stack.base_url}/health") == 200, 60, "python main.py /health"
        )
    finally:
        proc.stop()
    assert_one_format(proc.output().splitlines(), "python main.py 콘솔")
    app.start()
    cover("L6", "로깅 python main.py 경로")


def _get(httpx: Any, url: str) -> int:
    try:
        return httpx.get(url, timeout=2).status_code
    except httpx.HTTPError:
        return 0


def test_log_app_levels_filter_by_header(restart, api, stack, cover):
    log = stack.artifacts / "logs" / "app.log"
    size = log.stat().st_size
    restart(LOG_APP_LEVELS="uvicorn=WARNING")
    marker = f"/health?probe={secrets.token_hex(6)}"
    api.request("GET", marker)
    api.request("GET", f"{V1}/blog/posts")
    time.sleep(1)
    tail = log.read_bytes()[size:].decode("utf-8", errors="replace")  # 바이트 위치로 자른다
    assert marker not in tail, "uvicorn=WARNING 인데 접속 INFO 줄이 남았습니다"
    assert "[app=core]" in tail  # 다른 헤더(기동 줄)는 그대로 남는다
    assert not re.search(r"INFO +\[app=uvicorn\]", tail)
    cover("L6", "로깅 앱별 레벨")


def test_size_rotation_and_retention(restart, api, stack, cover):
    logs = stack.artifacts / "logs"
    today = datetime.now(UTC).date()
    expired = logs / "app.log.2020-01-01"
    kept = logs / f"app.log.{(today - timedelta(days=1)).isoformat()}"
    for path in (expired, kept):
        path.write_text("old\n", encoding="utf-8")
    restart(LOG_MAX_SIZE_MB="1", LOG_RETENTION_DAYS="1")
    filler = "x" * 8000
    for _ in range(160):  # 접속 줄 하나 ≈ 8KB → 1MB 를 넘긴다
        api.request("GET", f"/health?fill={filler}")
    wait_until(lambda: not expired.exists(), 15, "보관 기간이 지난 파일 삭제")
    rotated = sorted(p.name for p in logs.glob(f"app.log.{today.isoformat()}*"))
    assert rotated, "크기 초과 교체 파일이 없습니다"
    assert kept.exists(), "정확히 보관 일수만큼 된 파일은 남는다"
    assert (logs / "app.log").stat().st_size < 1024 * 1024
    cover("L6", "로깅 크기 교체·보관 삭제")


# ---------------------------------------------------------------------------
# 측정 (a): 기동 초기 줄이 프로세스 파일에 남는가
# ---------------------------------------------------------------------------


def test_early_startup_lines_land_in_the_process_file(stack, worker, cover):
    """설정이 로드되자마자 찍히는 줄([database] 라우팅 구성)이 그 프로세스의 파일에 있다."""
    logs = stack.artifacts / "logs"
    console = worker.proc.output()
    early = next(line for line in console.splitlines() if "라우팅 구성" in line)
    stamp = early[:21]
    assert any(
        line.startswith(stamp) and "라우팅 구성" in line for line in log_lines(logs / "celery.log")
    ), "Celery 기동 초기 줄이 celery.log 에 없다"
    cover("L6", "로깅 기동 초기 줄")
