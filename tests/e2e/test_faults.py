"""L5 장애 주입 — 이 작업의 compose 프로젝트(itest-active)에만 주입한다.

- Redis: 컨테이너 stop → start(실제 정지).
- MySQL primary: 데이터가 tmpfs 라 컨테이너를 멈추면 스키마가 사라진다 — ``offline_mode=ON`` 으로 앱 계정의
  기존 연결을 끊고 새 연결을 거부시킨다(정지된 서버와 같은 즉시 실패). 끝나면 OFF.
- MySQL replica: 컨테이너 stop → start(실제 정지). 다시 뜰 때 primary binlog 를 GTID 로 처음부터 받아 복구한다.
- 지연: replica ``STOP REPLICA SQL_THREAD``.
- Celery worker: 프로세스 정지 → 새 worker.

기대값은 사용자 결정(2026-10-20)을 따른다: Redis 장애 → 503(연결 유지·traceback 한 번), replica 연결 오류 →
primary 로 한 번 재시도 + WARNING, `/ready` 는 writer·Redis 만 본다.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import AdminClient, celery_client, fresh_ip, wait_until

V1 = "/api/v1"
#: 오류 응답에 나오면 안 되는 내부 정보.
LEAKS = re.compile(
    r"Traceback|OperationalError|pymysql|aiomysql|redis\.|ConnectionError|"
    r"127\.0\.0\.1|1333[12]|16392|SELECT |INSERT ",
    re.I,
)


def no_leak(stack: Any, response: Any) -> None:
    text = response.text
    assert not LEAKS.search(text), text[:500]
    for secret in stack.all_secrets():
        assert secret not in text


def tracebacks(app: Any) -> int:
    """traceback 을 가진 로그 레코드 수 — 원인 사슬(``from e``)의 두 번째 Traceback 은 같은 레코드다."""
    pattern = r"^\[20[^\n]*\nTraceback \(most recent call last\)"
    return len(re.findall(pattern, app.proc.output(), re.M))


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------


def test_redis_outage_fails_closed_with_503_and_recovers(app, api, stack, superuser, cover):
    user = api.user()
    admin_client = AdminClient(stack)
    wait_until(
        lambda: admin_client.login(superuser["username"], superuser["password"]).status_code == 302,
        15,
        "관리 로그인",
    )
    target = api.user()
    stack.compose("stop", "redis")
    try:
        with httpx.Client(base_url=stack.base_url, timeout=30) as http:

            def call(method: str, url: str, **kwargs: Any) -> Any:
                headers = {"X-Forwarded-For": fresh_ip(), **kwargs.pop("headers", {})}
                return http.request(method, url, headers=headers, **kwargs)

            before = tracebacks(app)
            outcomes = {
                "login": call(
                    "POST",
                    f"{V1}/auth/login",
                    data={"username": user.username, "password": user.password},
                ),
                "refresh": call("POST", f"{V1}/auth/refresh", json={"refresh_token": user.refresh}),
                "register": call(
                    "POST",
                    f"{V1}/auth/register",
                    json={
                        "username": "r_" + secrets.token_hex(4),
                        "email": "r@example.com",
                        "password": "Pw-12345678",
                    },
                ),
                "logout": call("POST", f"{V1}/auth/logout", json={"refresh_token": user.refresh}),
            }
            for name, response in outcomes.items():
                assert response.status_code == 503, (name, response.status_code, response.text)
                assert response.json()["error_code"] == "SERVICE_UNAVAILABLE", response.text
                assert response.headers.get("connection", "").lower() != "close", name
                no_leak(stack, response)
            assert tracebacks(app) - before <= len(outcomes), "요청마다 traceback 은 한 번"
            # 같은 keep-alive 연결로 다음 요청이 그대로 된다
            assert call("GET", "/health").status_code == 200
            assert call("GET", "/ready").status_code == 503
            assert call("GET", f"{V1}/blog/posts").status_code == 200  # Redis 를 안 쓰는 읽기
            # 관리 화면: fail-closed 503, 사용자 변경은 저장되지 않는다
            assert admin_client.request("GET", "/admin/").status_code == 503
            # 쿠키 없는 첫 요청 — 응답 직전의 새 세션 저장이 실패해도 503(e2e-policy-2 결정 6)
            first = call("GET", "/admin/login")
            assert first.status_code == 503, first.text
            no_leak(stack, first)
            changed = admin_client.request(
                "POST", f"/admin/user/edit/{target.id}", data={"is_active": ""}
            )
            assert changed.status_code == 503
            no_leak(stack, changed)
        with stack.mysql() as conn, conn.cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE id=%s", (target.id,))
            assert cur.fetchone() == (1,)
    finally:
        stack.compose("start", "redis")
        wait_until(lambda: api.request("GET", "/ready").status_code == 200, 60, "Redis 회복 /ready")
    assert api.login(user.username, user.password).status_code == 200
    again = AdminClient(stack)
    assert again.login(superuser["username"], superuser["password"]).status_code == 302
    cover("L5", "Redis 정지·재기동")


# ---------------------------------------------------------------------------
# MySQL primary
# ---------------------------------------------------------------------------


def test_primary_outage_ready_503_health_200_no_leak(app, api, stack, cover):
    user = api.user()
    with stack.mysql(root=True) as root, root.cursor() as cur:
        cur.execute("SET GLOBAL offline_mode = ON")
        try:
            assert api.request("GET", "/ready").status_code == 503
            assert api.request("GET", "/health").status_code == 200
            failed = api.request(
                "POST", f"{V1}/blog/posts", json={"title": "t", "content": "c"}, headers=user.auth
            )
            assert 500 <= failed.status_code < 600, failed.status_code
            assert failed.json()["error_code"], failed.text
            no_leak(stack, failed)
            # 처리되지 않은 예외(e2e-policy-2 결정 2): 로그인의 사용자 조회는 저장소가 번역하지 않는 읽기라
            # OperationalError 가 그대로 올라간다 — 500 한 번, traceback 은 핸들러의 한 레코드, 연결은 유지.
            log_before = len(app.proc.output())
            with httpx.Client(base_url=stack.base_url, timeout=30) as http:
                unhandled = http.post(
                    f"{V1}/auth/login",
                    data={"username": user.username, "password": user.password},
                    headers={"X-Forwarded-For": fresh_ip()},
                )
                assert unhandled.status_code == 500, unhandled.text
                assert unhandled.json() == {
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "message": "내부 서버 오류가 발생했습니다.",
                    "detail": None,
                }
                assert unhandled.headers.get("connection", "").lower() != "close"
                no_leak(stack, unhandled)
                assert http.get("/health").status_code == 200  # 같은 keep-alive 연결
            tail = app.proc.output()[log_before:]
            assert "Exception in ASGI application" not in tail, tail[-3000:]
            assert tail.count("[UnhandledException]") == 1, tail[-3000:]
        finally:
            cur.execute("SET GLOBAL offline_mode = OFF")
    wait_until(lambda: api.request("GET", "/ready").status_code == 200, 30, "primary 회복")
    made = api.request(
        "POST", f"{V1}/blog/posts", json={"title": "t", "content": "c"}, headers=user.auth
    )
    assert made.status_code == 201
    cover("L5", "MySQL primary 정지")


# ---------------------------------------------------------------------------
# MySQL replica
# ---------------------------------------------------------------------------


def test_replica_outage_falls_back_to_primary(app, api, stack, cover):
    user = api.user()
    stack.compose("stop", "mysql-replica")
    try:
        log_before = len(app.proc.output())
        made = api.request(
            "POST", f"{V1}/blog/posts", json={"title": "fb", "content": "c"}, headers=user.auth
        )
        assert made.status_code == 201
        got = api.request("GET", f"{V1}/blog/posts/{made.json()['id']}")
        assert got.status_code == 200, got.text  # 읽기가 primary 로 한 번 다시 간다
        assert api.request("GET", f"{V1}/auth/me", headers=user.auth).status_code == 200
        assert api.request("GET", "/ready").status_code == 200  # /ready 는 replica 를 보지 않는다
        tail = app.proc.output()[log_before:]
        assert re.search(r"WARNING .*replica", tail), tail[-2000:]
        for secret in stack.all_secrets():
            assert secret not in tail
    finally:
        stack.compose("start", "mysql-replica")
        wait_until(
            lambda: "(healthy)" in stack.compose("ps", "--format", "{{.Status}}", "mysql-replica"),
            180,
            "replica 재초기화",
        )
        # healthy 는 복제 스레드가 돈다는 뜻일 뿐이다 — tmpfs 라 처음부터 binlog 를 다시 받는 중이다.
        # 다음 테스트가 지연을 장애로 오해하지 않게 primary 의 GTID 집합까지 따라잡을 때까지 기다린다.
        with stack.mysql(root=True) as primary, primary.cursor() as cur:
            cur.execute("SELECT @@GLOBAL.gtid_executed")
            (gtids,) = cur.fetchone()
        with stack.mysql(root=True, replica=True) as replica, replica.cursor() as cur:
            cur.execute("SELECT WAIT_FOR_EXECUTED_GTID_SET(%s, 600)", (gtids,))
            assert cur.fetchone() == (0,), "replica 가 primary 를 따라잡지 못했습니다"
    cover("L5", "MySQL replica 정지")


def test_replica_lag_keeps_read_after_write_on_primary(app, api, stack, cover):
    user = api.user()
    with stack.mysql(root=True, replica=True) as replica, replica.cursor() as cur:
        cur.execute("STOP REPLICA SQL_THREAD")
        try:
            made = api.request(
                "POST", f"{V1}/sns/posts", json={"content": "lag"}, headers=user.auth
            )
            assert made.status_code == 201 and made.json()["content"] == "lag"
            item = f"{V1}/sns/posts/{made.json()['id']}"
            assert (
                api.request("PATCH", item, json={"content": "lag2"}, headers=user.auth).status_code
                == 200
            )
            assert (
                api.request("GET", item).status_code == 404
            )  # 지연은 연결 오류가 아니다 — 재시도 없음
            # 인증 사용자 조회는 primary(e2e-policy-2 결정 5): replica 에 아직 없는 새 사용자도 /me 200
            # (api.user() 가 /me 를 부른다), primary 의 비활성화는 replica 를 기다리지 않고 401.
            fresh = api.user()
            with stack.mysql() as conn, conn.cursor() as primary:
                primary.execute("UPDATE users SET is_active=0 WHERE id=%s", (user.id,))
                conn.commit()
            me = api.request("GET", f"{V1}/auth/me", headers=user.auth)
            assert me.status_code == 401, me.text
            assert api.request("GET", f"{V1}/auth/me", headers=fresh.auth).status_code == 200
        finally:
            cur.execute("START REPLICA SQL_THREAD")
    got = wait_until(lambda: (r := api.request("GET", item)).status_code == 200 and r, 15, "복제")
    assert got.json()["content"] == "lag2"
    cover("L5", "MySQL replica 지연")


# ---------------------------------------------------------------------------
# Celery worker
# ---------------------------------------------------------------------------


def test_worker_outage_does_not_affect_api_and_queue_drains(app, api, stack, worker, cover):
    worker.stop()
    try:
        user = api.user()
        assert (
            api.request(
                "POST", f"{V1}/blog/posts", json={"title": "w", "content": "c"}, headers=user.auth
            ).status_code
            == 201
        )
        pending = celery_client(stack).send_task("home.aggregate_access_stats")
        with pytest.raises(Exception):  # noqa: B017 - 처리할 worker 가 없다
            pending.get(timeout=3)
    finally:
        worker.start()
    assert "total" in pending.get(timeout=60)
    cover("L5", "Celery worker 정지·재기동")
