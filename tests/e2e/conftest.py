"""전수 통합(E2E) 하네스 (integration-e2e W2).

`compose.e2e.yaml`(MySQL primary + GTID replica + Redis)이 떠 있는 상태에서 실제 프로세스를 띄운다:
Alembic upgrade → 슈퍼유저 생성(scripts/create_superuser.py) → uvicorn(main:app) → Celery worker.

- **대상 안전 검사**: 모든 접속 대상의 host 는 127.0.0.1, 포트는 계획서 §0 의 active 행이어야 한다. 아니면
  세션 전체를 즉시 멈춘다(pytest.exit) — 남의 DB·Redis 에 붙는 사고를 막는다. Redis 대상은 W0 의
  `redis_target()` 으로 명시를 강제한다.
- **`.env` 차단**: 자식 프로세스는 산출물 폴더를 cwd 로 쓰므로 저장소 `.env` 를 읽지 않는다. 환경 변수는
  여기서 전부 명시하고, 비밀값(JWT·세션 키·사용자 비밀번호)은 실행마다 새로 만든다.
- **산출물**: `E2E_ARTIFACT_DIR`(기본 `.e2e-artifacts/`) 아래 프로세스 출력·로그 파일. CI 는 실패 시 올린다.
- `-m e2e` 를 줄 때만 이 폴더를 수집한다 — 다른 실행에서는 deselect·skip 이 남지 않는다.
"""

from __future__ import annotations

import itertools
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
#: 계획서 §0 active 행. 이 값이 아니면 시작하지 않는다.
PORTS = {
    "E2E_MYSQL_PRIMARY_PORT": 13331,
    "E2E_MYSQL_REPLICA_PORT": 13332,
    "E2E_REDIS_PORT": 16392,
    "E2E_APP_PORT": 18092,
}
COMPOSE_PROJECT = "itest-active"
DATABASE = "fastapi_active_e2e"
DB_USER = "fastapi_active_e2e"
#: 테스트마다의 시간 제한(초). 관리 화면 이동이 멈춰도 세션 전체가 서지 않게 한다.
TEST_TIMEOUT = int(os.environ.get("E2E_TEST_TIMEOUT", "300"))


# ---------------------------------------------------------------------------
# 수집: -m e2e 일 때만
# ---------------------------------------------------------------------------


def _e2e_selected(config: pytest.Config) -> bool:
    expr = config.getoption("markexpr") or ""
    return "e2e" in expr and "not e2e" not in expr


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if collection_path != Path(__file__).parent and not _e2e_selected(config):
        return True
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    mine = [item for item in items if here in Path(item.path).parents]
    for item in mine:
        item.add_marker(pytest.mark.e2e)
        item.add_marker(pytest.mark.timeout(TEST_TIMEOUT))
    # 인벤토리 대조는 다른 테스트가 칸을 채운 뒤에 돈다.
    last = [item for item in mine if Path(item.path).name == "test_inventory.py"]
    items[:] = [item for item in items if item not in last] + last


# ---------------------------------------------------------------------------
# 대상 안전 검사
# ---------------------------------------------------------------------------


def _port(name: str) -> int:
    value = int(os.environ.get(name, PORTS[name]))
    if value != PORTS[name]:
        pytest.exit(
            f"{name}={value} — 계획서 §0 의 값({PORTS[name]})이 아니면 시작하지 않습니다.", 3
        )
    return value


def _reachable(port: int) -> bool:
    try:
        with socket.create_connection((HOST, port), timeout=2):
            return True
    except OSError:
        return False


@dataclass
class Stack:
    """compose.e2e.yaml 접속 정보 + 실행마다 만든 비밀값."""

    primary_port: int
    replica_port: int
    redis_port: int
    app_port: int
    db_password: str
    artifacts: Path
    secrets: dict[str, str] = field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return f"http://{HOST}:{self.app_port}"

    @property
    def redis_url(self) -> str:
        return f"redis://{HOST}:{self.redis_port}/0"

    def all_secrets(self) -> list[str]:
        return [self.db_password, *self.secrets.values()]

    def mysql(self, *, replica: bool = False, root: bool = False, **kwargs: Any) -> Any:
        import pymysql

        return pymysql.connect(
            host=HOST,
            port=self.replica_port if replica else self.primary_port,
            user="root" if root else DB_USER,
            password=self.db_password,
            database=DATABASE,
            autocommit=True,
            charset="utf8mb4",
            **kwargs,
        )

    def redis(self) -> Any:
        import redis

        return redis.Redis(host=HOST, port=self.redis_port, db=0, decode_responses=True)

    def compose(self, *args: str, timeout: int = 180) -> str:
        """이 작업의 compose 프로젝트에만 명령을 보낸다(장애 주입: stop·start)."""
        assert args[0] in {"stop", "start", "ps", "logs"}, args
        base = ["docker", "compose", "-p", COMPOSE_PROJECT]
        if os.name == "nt":  # Docker 는 WSL 안에만 있다.
            base = ["wsl", "-e", *base]
        done = subprocess.run(
            [*base, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        return done.stdout + done.stderr


@pytest.fixture(scope="session")
def stack() -> Stack:
    from tests.redis_target import redis_target

    primary, replica = _port("E2E_MYSQL_PRIMARY_PORT"), _port("E2E_MYSQL_REPLICA_PORT")
    redis_port, app_port = _port("E2E_REDIS_PORT"), _port("E2E_APP_PORT")
    host, port = redis_target()  # W0: 명시되지 않았거나 닿지 않으면 실패
    if (host, port) != (HOST, redis_port):
        pytest.exit(
            f"REDIS_HOST:REDIS_PORT={host}:{port} — e2e 는 {HOST}:{redis_port} 만 씁니다.", 3
        )
    password = os.environ.get("E2E_MYSQL_PASSWORD", "")
    if len(password) < 16:
        pytest.fail(
            "E2E_MYSQL_PASSWORD 가 없습니다 — compose 를 띄울 때 쓴 무작위 값(16~32자)을 같이 주세요.",
            pytrace=False,
        )
    for port_ in (primary, replica):
        if not _reachable(port_):
            pytest.fail(f"{HOST}:{port_} 에 MySQL 이 없습니다 — compose.e2e.yaml 을 먼저 띄우세요.")
    if _reachable(app_port):
        pytest.exit(f"{HOST}:{app_port} 가 이미 사용 중입니다 — 앱 포트를 비우세요.", 3)

    artifacts = Path(os.environ.get("E2E_ARTIFACT_DIR", REPO / ".e2e-artifacts")).resolve()
    shutil.rmtree(artifacts, ignore_errors=True)
    (artifacts / "logs").mkdir(parents=True)
    return Stack(
        primary_port=primary,
        replica_port=replica,
        redis_port=redis_port,
        app_port=app_port,
        db_password=password,
        artifacts=artifacts,
        secrets={
            "ACCESS_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "REFRESH_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "SESSION_SECRET_KEY": secrets.token_urlsafe(48),
            "SUPERUSER_PASSWORD": "Su-" + secrets.token_urlsafe(18),
        },
    )


# ---------------------------------------------------------------------------
# 자식 프로세스
# ---------------------------------------------------------------------------

#: OS 가 프로세스를 띄우는 데 필요한 변수만 물려준다. 앱 설정은 아래에서 전부 명시한다.
_PASSTHROUGH = (
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "COMSPEC",
    "PATHEXT",
    "LANG",
    "LC_ALL",
    "USERNAME",
    "USER",
    "LOGNAME",
)  # aiomysql 이 import 때 getpass.getuser() 를 부른다


def app_env(stack: Stack, **overrides: str) -> dict[str, str]:
    from tests.redis_target import child_env

    env = {k: os.environ[k] for k in _PASSTHROUGH if k in os.environ}
    env.update(
        PYTHONPATH=str(REPO),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
        PYTHONDONTWRITEBYTECODE="1",
        ENV="staging",
        DEBUG="false",
        ADMIN_DISABLED="false",
        SERVER_HOST=HOST,
        SERVER_PORT=str(stack.app_port),
        MYSQL_HOST=HOST,
        MYSQL_PORT=str(stack.primary_port),
        MYSQL_USER=DB_USER,
        MYSQL_PASSWORD=stack.db_password,
        MYSQL_DATABASE=DATABASE,
        DB_ROUTER_ENABLED="true",
        DB_REPLICATION_ENABLED="true",
        DB_READ_STICKY_AFTER_WRITE="true",
        MYSQL_REPLICA_HOSTS=json.dumps([f"{HOST}:{stack.replica_port}"]),
        CORS_ALLOW_ORIGINS=json.dumps([stack.base_url]),
        TRUSTED_PROXY_HOPS="1",
        LOG_DIR=str(stack.artifacts / "logs"),
        LOG_FILE_ENABLED="true",
        ACCESS_LOG_ENABLED="true",
        # 창이 지나면 회복되는지 보려면 창이 짧아야 한다(기본 60s·3600s).
        AUTH_LOGIN_WINDOW_SECONDS="6",
        AUTH_REGISTER_WINDOW_SECONDS="6",
        **{k: v for k, v in stack.secrets.items() if k != "SUPERUSER_PASSWORD"},
    )
    env = child_env((HOST, stack.redis_port), base=env)
    env.update(overrides)
    for key, value in env.items():  # 대상 안전 검사 — 자식이 받는 값으로 한 번 더 본다
        if key.endswith("_HOST") and key != "SERVER_HOST":
            assert value == HOST, f"{key}={value}"
    return env


def run(
    stack: Stack,
    *args: str,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """`.env` 없는 cwd(산출물 폴더)에서 저장소 파이썬으로 실행한다."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=stack.artifacts,
        env=env or app_env(stack),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


class Proc:
    """오래 도는 자식(uvicorn·Celery). 출력은 산출물 폴더의 `<이름>.out` 에 쌓는다."""

    def __init__(self, stack: Stack, name: str, args: list[str], env: dict[str, str]) -> None:
        self.name = name
        self.out_path = stack.artifacts / f"{name}.out"
        self._out = self.out_path.open("a", encoding="utf-8")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.popen = subprocess.Popen(
            [sys.executable, *args],
            cwd=stack.artifacts,
            env=env,
            stdout=self._out,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )

    def alive(self) -> bool:
        return self.popen.poll() is None

    def stop(self, timeout: float = 30) -> int:
        if self.alive():
            if os.name == "nt":
                self.popen.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.popen.send_signal(signal.SIGTERM)
            try:
                self.popen.wait(timeout)
            except subprocess.TimeoutExpired:
                self.popen.kill()
                self.popen.wait(10)
        self._out.close()
        return self.popen.returncode

    def output(self) -> str:
        self._out.flush()
        return self.out_path.read_text(encoding="utf-8", errors="replace")


def wait_until(predicate: Any, timeout: float, what: str, interval: float = 0.3) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError(f"{timeout}s 안에 {what} 이(가) 되지 않았습니다")


@dataclass
class App:
    """uvicorn(main:app) 한 개. ``restart(**env)`` 로 설정을 바꿔 다시 띄운다(같은 포트)."""

    stack: Stack
    proc: Proc | None = None
    generation: Iterator[int] = field(default_factory=itertools.count)

    def start(self, **overrides: str) -> None:
        import httpx

        name = f"uvicorn-{next(self.generation)}"
        self.proc = Proc(
            self.stack,
            name,
            ["-m", "uvicorn", "main:app", "--host", HOST, "--port", str(self.stack.app_port)],
            app_env(self.stack, **overrides),
        )

        def up() -> bool:
            assert (
                self.proc and self.proc.alive()
            ), f"uvicorn 이 죽었습니다:\n{self.proc.output()[-3000:]}"
            try:
                return httpx.get(f"{self.stack.base_url}/ready", timeout=2).status_code == 200
            except httpx.HTTPError:
                return False

        wait_until(up, 120, "uvicorn /ready 200")

    def stop(self) -> int | None:
        code = self.proc.stop() if self.proc else None
        wait_until(lambda: not _reachable(self.stack.app_port), 30, "앱 포트 해제")
        return code


@pytest.fixture(scope="session")
def migrated(stack: Stack) -> Stack:
    done = run(stack, "-m", "alembic", "-c", str(REPO / "alembic.ini"), "upgrade", "head")
    assert done.returncode == 0, done.stdout + done.stderr
    (stack.artifacts / "alembic.out").write_text(done.stdout + done.stderr, encoding="utf-8")
    return stack


@pytest.fixture(scope="session")
def superuser(migrated: Stack) -> dict[str, str]:
    username = "e2e_admin_" + secrets.token_hex(3)
    done = run(
        migrated,
        "-m",
        "scripts.create_superuser",
        "--username",
        username,
        "--email",
        f"{username}@example.com",
        "--password-stdin",
        stdin=migrated.secrets["SUPERUSER_PASSWORD"] + "\n",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return {"username": username, "password": migrated.secrets["SUPERUSER_PASSWORD"]}


@pytest.fixture(scope="session")
def app(migrated: Stack, superuser: dict[str, str]) -> Iterator[App]:
    server = App(migrated)
    server.start()
    yield server
    server.stop()


@pytest.fixture(scope="session")
def worker(migrated: Stack) -> Iterator[Proc]:
    pool = ["--pool=solo"] if os.name == "nt" else ["--pool=prefork", "--concurrency=1"]
    proc = Proc(
        migrated,
        "celery-worker",
        [
            "-m",
            "celery",
            "-A",
            "app.celery.app:celery_app",
            "worker",
            "--loglevel=INFO",
            "-n",
            "e2e@%h",
            *pool,
        ],
        app_env(migrated),
    )
    client = celery_client(migrated)
    wait_until(lambda: proc.alive() and client.control.ping(timeout=1), 120, "Celery worker ping")
    yield proc
    proc.stop()


def celery_client(stack: Stack) -> Any:
    """프로젝트를 import 하지 않는 Celery 클라이언트(같은 broker·backend)."""
    from celery import Celery

    return Celery("e2e-client", broker=stack.redis_url, backend=stack.redis_url)


# ---------------------------------------------------------------------------
# HTTP 도우미
# ---------------------------------------------------------------------------

_ips = itertools.count(1)


def fresh_ip() -> str:
    """요청마다 다른 클라이언트 IP(XFF, TRUSTED_PROXY_HOPS=1) — IP 단위 rate limit 을 테스트끼리 나누지 않는다."""
    n = next(_ips)
    return f"10.77.{n // 250}.{n % 250 + 1}"


@dataclass
class User:
    id: str
    username: str
    password: str
    access: str
    refresh: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access}"}


class Api:
    """앱에 붙는 httpx 클라이언트 + 사용자 만들기."""

    def __init__(self, stack: Stack, superuser: dict[str, str]) -> None:
        import httpx

        self.stack = stack
        self.http = httpx.Client(base_url=stack.base_url, timeout=30, follow_redirects=False)
        self._superuser = superuser

    def request(self, method: str, url: str, *, ip: str | None = None, **kwargs: Any) -> Any:
        headers = {"X-Forwarded-For": ip or fresh_ip(), **kwargs.pop("headers", {})}
        return self.http.request(method, url, headers=headers, **kwargs)

    def login(self, username: str, password: str, ip: str | None = None) -> Any:
        return self.request(
            "POST", "/api/v1/auth/login", ip=ip, data={"username": username, "password": password}
        )

    def user(self) -> User:
        username = "u_" + secrets.token_hex(5)
        password = "Pw-" + secrets.token_urlsafe(12)
        made = self.request(
            "POST",
            "/api/v1/auth/register",
            json={"username": username, "email": f"{username}@example.com", "password": password},
        )
        assert made.status_code == 201, made.text
        user_id = made.json()["id"]
        # 로그인은 replica 에서 사용자를 읽는다 — 복제가 따라올 때까지 기다린다.
        tokens = wait_until(
            lambda: (r := self.login(username, password)).status_code == 200 and r.json(),
            15,
            "가입 직후 로그인 200",
        )
        return User(user_id, username, password, tokens["access_token"], tokens["refresh_token"])

    def admin(self) -> User:
        tokens = self.login(self._superuser["username"], self._superuser["password"])
        assert tokens.status_code == 200, tokens.text
        body = tokens.json()
        me = self.request(
            "GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        ).json()
        return User(
            me["id"],
            me["username"],
            self._superuser["password"],
            body["access_token"],
            body["refresh_token"],
        )


@pytest.fixture(scope="session")
def api(app: App, superuser: dict[str, str]) -> Iterator[Api]:
    client = Api(app.stack, superuser)
    yield client
    client.http.close()


def replicated(stack: Stack, sql: str, args: tuple[Any, ...] = ()) -> None:
    """primary 에서 보이는 결과가 replica 에서도 같아질 때까지 기다린다."""

    def same() -> bool:
        with stack.mysql() as p, stack.mysql(replica=True) as r, p.cursor() as pc, r.cursor() as rc:
            pc.execute(sql, args)
            rc.execute(sql, args)
            return pc.fetchall() == rc.fetchall()

    wait_until(same, 15, "replica 따라잡기")


# ---------------------------------------------------------------------------
# 인벤토리 기록 — L2 매트릭스의 칸, L3~L6 의 항목을 실행한 테스트가 채운다
# ---------------------------------------------------------------------------

COVERAGE: dict[str, set[str]] = {}


@pytest.fixture
def cover(request: pytest.FixtureRequest) -> Any:
    """``cover("GET /api/v1/blog/posts", "정상")`` — 이 테스트가 그 칸을 실행했다고 적는다."""

    def mark(*keys: str) -> None:
        COVERAGE.setdefault(" | ".join(keys), set()).add(request.node.nodeid)

    return mark


@pytest.fixture(scope="session")
def inventory(migrated: Stack) -> dict[str, Any]:
    """실제 앱에서 뽑은 인벤토리(OpenAPI·접근 수준·관리 뷰·Celery) — inventory_probe 참고."""
    done = run(
        migrated, "-m", "tests.e2e.inventory_probe", env=app_env(migrated, LOG_FILE_ENABLED="false")
    )
    assert done.returncode == 0, done.stdout + done.stderr
    line = next(x for x in done.stdout.splitlines() if x.startswith("INVENTORY:"))
    return json.loads(line.removeprefix("INVENTORY:"))
