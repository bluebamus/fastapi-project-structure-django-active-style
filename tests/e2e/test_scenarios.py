"""L3 연동 시나리오 — API 응답뿐 아니라 MySQL·Redis 상태까지 본다."""

from __future__ import annotations

import base64
import json
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tests.e2e.conftest import AdminClient, fresh_ip, wait_until

V1 = "/api/v1"


def claims(token: str) -> dict[str, Any]:
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


# ---------------------------------------------------------------------------
# 1. 가입 → 로그인 → /me → refresh 회전 → 재사용 거부(family 폐기) → logout
# ---------------------------------------------------------------------------


def test_auth_lifecycle_rotates_and_revokes_refresh_families(api, stack, cover):
    r = stack.redis()
    user = api.user()
    me = api.request("GET", f"{V1}/auth/me", headers=user.auth)
    assert me.status_code == 200 and me.json()["id"] == user.id

    first = claims(user.refresh)
    assert r.exists(f"auth:rt:{first['jti']}")
    assert first["fam"] in r.smembers(f"auth:user:{user.id}:fams")

    rotated = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": user.refresh})
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()["refresh_token"]
    assert claims(second)["fam"] == first["fam"] and claims(second)["jti"] != first["jti"]
    assert not r.exists(f"auth:rt:{first['jti']}")  # 쓴 토큰은 지워진다

    reuse = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": user.refresh})
    assert reuse.status_code == 401
    assert r.exists(f"auth:fam:{first['fam']}:revoked")  # 재사용 → family 전체 폐기
    after_reuse = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": second})
    assert after_reuse.status_code == 401  # 같은 family 의 정상 토큰도 끊긴다

    fresh = api.login(user.username, user.password).json()["refresh_token"]
    out = api.request("POST", f"{V1}/auth/logout", json={"refresh_token": fresh})
    assert out.status_code == 204
    again = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": fresh})
    assert again.status_code == 401
    cover("L3", "1 인증 수명주기")
    cover("Redis", "auth:rt:")
    cover("Redis", "auth:fam:")
    cover("Redis", "auth:user:")


# ---------------------------------------------------------------------------
# 2. 로그인·가입 레이트 리밋: 429 → 창이 지나면 회복, 키 TTL
# ---------------------------------------------------------------------------


def _window_passes(r: Any, key: str) -> None:
    ttl = r.ttl(key)
    assert 0 < ttl <= 6, f"{key} TTL={ttl} (AUTH_*_WINDOW_SECONDS=6)"
    wait_until(lambda: not r.exists(key), 15, f"{key} 만료")


def test_login_rate_limit_per_user_and_recovery(api, stack, cover):
    r = stack.redis()
    user = api.user()
    ip = fresh_ip()
    for _ in range(5):  # AUTH_LOGIN_MAX_ATTEMPTS 기본 5 — 실패만 센다
        assert api.login(user.username, "wrong-password", ip=ip).status_code == 401
    blocked = api.login(user.username, user.password, ip=ip)
    assert blocked.status_code == 429, blocked.text
    assert int(blocked.headers["retry-after"]) > 0
    key = f"auth:rl:login:{ip}:{user.username.lower()}"
    _window_passes(r, key)
    assert api.login(user.username, user.password, ip=ip).status_code == 200
    cover("L3", "2 로그인 레이트 리밋")
    cover("Redis", "auth:rl:login:")


def test_login_rate_limit_per_ip(api, stack, cover):
    r = stack.redis()
    ip = fresh_ip()
    statuses = [api.login(f"nobody_{i}", "wrong-password", ip=ip).status_code for i in range(21)]
    assert statuses[:20] == [401] * 20 and statuses[20] == 429, statuses  # IP 한도 기본 20
    _window_passes(r, f"auth:rl:login-ip:{ip}")
    cover("L3", "2 로그인 IP 레이트 리밋")
    cover("Redis", "auth:rl:login-ip:")


def test_register_rate_limit_and_recovery(api, stack, cover):
    r = stack.redis()
    ip = fresh_ip()

    def register() -> int:
        name = "rl_" + secrets.token_hex(5)
        body = {"username": name, "email": f"{name}@example.com", "password": "Pw-" + name}
        return api.request("POST", f"{V1}/auth/register", ip=ip, json=body).status_code

    statuses = [register() for _ in range(6)]
    assert statuses == [201] * 5 + [429], statuses
    _window_passes(r, f"auth:rl:register:{ip}")
    assert register() == 201
    cover("L3", "2 가입 레이트 리밋")
    cover("Redis", "auth:rl:register:")


# ---------------------------------------------------------------------------
# 3. 글·댓글 소유권: 타인 403 → 본인 수정·삭제 → 슈퍼유저 수정 가능
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,url,body,patch",
    [
        ("blog", f"{V1}/blog/posts", {"title": "t", "content": "c"}, {"title": "u"}),
        ("sns", f"{V1}/sns/posts", {"content": "c"}, {"content": "u"}),
        ("reply", f"{V1}/reply/replies", {"content": "c"}, {"content": "u"}),
    ],
)
def test_ownership_rules(kind, url, body, patch, api, cover):
    owner, other, admin = api.user(), api.user(), api.admin()
    made = api.request("POST", url, json=body, headers=owner.auth)
    assert made.status_code == 201, made.text
    item = f"{url}/{made.json()['id']}"
    assert api.request("PATCH", item, json=patch, headers=other.auth).status_code == 403
    assert api.request("DELETE", item, headers=other.auth).status_code == 403
    assert api.request("PATCH", item, json=patch, headers=owner.auth).status_code == 200
    assert api.request("PATCH", item, json=patch, headers=admin.auth).status_code == 200
    assert api.request("DELETE", item, headers=owner.auth).status_code == 204
    second = api.request("POST", url, json=body, headers=owner.auth).json()["id"]
    assert api.request("DELETE", f"{url}/{second}", headers=admin.auth).status_code == 204
    cover("L3", f"3 소유권 {kind}")


# ---------------------------------------------------------------------------
# 4. API 로 비활성화·강등·삭제 → refresh·관리 세션 폐기(이 저장소: 셋 모두 폐기)
# ---------------------------------------------------------------------------


def _superuser_with_admin_session(api: Any, stack: Any) -> tuple[Any, AdminClient]:
    admin = api.admin()
    name = "su_" + secrets.token_hex(4)
    password = "Pw-" + secrets.token_hex(8)
    made = api.request(
        "POST",
        f"{V1}/user/users",
        headers=admin.auth,
        json={
            "username": name,
            "email": f"{name}@example.com",
            "password": password,
            "is_superuser": True,
        },
    )
    assert made.status_code == 201, made.text
    browser = AdminClient(stack)
    logged = wait_until(lambda: browser.login(name, password).status_code == 302, 15, "관리 로그인")
    assert logged and browser.sid
    tokens = api.login(name, password).json()
    return {"id": made.json()["id"], "refresh": tokens["refresh_token"]}, browser


@pytest.mark.parametrize(
    "change",
    [{"is_active": False}, {"is_superuser": False}, None],
    ids=["비활성화", "강등", "삭제"],
)
def test_user_changes_revoke_refresh_and_admin_sessions(change, api, stack, cover):
    r = stack.redis()
    target, browser = _superuser_with_admin_session(api, stack)
    session_keys = r.smembers(f"admin:user_sessions:{target['id']}")
    assert len(session_keys) == 1 and all(
        k.startswith("admin:sess:") and r.exists(k) for k in session_keys
    )
    assert browser.request("GET", "/admin/").status_code == 200

    admin = api.admin()
    url = f"{V1}/user/users/{target['id']}"
    if change is None:
        assert api.request("DELETE", url, headers=admin.auth).status_code == 204
    else:
        assert api.request("PATCH", url, json=change, headers=admin.auth).status_code == 200

    refreshed = api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": target["refresh"]})
    assert refreshed.status_code == 401
    assert r.scard(f"admin:user_sessions:{target['id']}") == 0
    assert not any(r.exists(k) for k in session_keys)  # 서버 세션 자체가 지워졌다
    page = browser.request("GET", "/admin/")
    assert page.status_code in (302, 303) and "/admin/login" in page.headers["location"]
    browser.close()
    cover("L3", f"4 사용자 변경 폐기 {list(change or {'delete': 1})[0]}")
    cover("Redis", "admin:sess:")
    cover("Redis", "admin:user_sessions:")


# ---------------------------------------------------------------------------
# 5. 접속 로그: 적재(IP·XFF·사용자) → API 조회 → 관리 화면 기간 필터 → 보존 삭제 태스크(경계·배치)
# ---------------------------------------------------------------------------


def test_access_log_is_recorded_with_client_ip_and_user(api, stack, cover):
    user, admin = api.user(), api.admin()
    ip = fresh_ip()
    api.request("GET", f"{V1}/auth/me", ip=ip, headers=user.auth)

    def stored() -> dict[str, Any] | None:
        import pymysql.cursors

        with stack.mysql(cursorclass=pymysql.cursors.DictCursor) as c, c.cursor() as cur:
            cur.execute("SELECT * FROM user_access_logs WHERE ip_address=%s", (ip,))
            return cur.fetchone()

    log = wait_until(stored, 15, "접속 로그 적재")
    assert log["user_id"] == user.id
    assert log["forwarded_for"] == ip and log["request_path"] == f"{V1}/auth/me"
    assert log["response_status"] == 200

    by_ip = wait_until(
        lambda: (
            api.request("GET", f"{V1}/home/access-logs/by-ip/{ip}", headers=admin.auth)
        ).json(),
        15,
        "by-ip 조회",
    )
    assert any(item["user_id"] == user.id for item in by_ip)
    by_user = api.request("GET", f"{V1}/home/access-logs/by-user/{user.id}", headers=admin.auth)
    assert any(item["ip_address"] == ip for item in by_user.json())
    cover("L3", "5 접속 로그 적재·조회")


def _insert_logs(stack: Any, rows: list[datetime], marker: str) -> None:
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO user_access_logs (id, ip_address, is_bot, request_path, request_method,"
            " created_at) VALUES (%s, '10.99.0.1', 0, %s, 'GET', %s)",
            [(str(uuid.uuid4()), marker, at.replace(tzinfo=None)) for at in rows],
        )


def _count(stack: Any, marker: str) -> int:
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_access_logs WHERE request_path=%s", (marker,))
        return cur.fetchone()[0]


def test_retention_task_deletes_in_batches_and_keeps_the_boundary(stack, worker, cover):
    """보존 365일: 경계보다 오래된 행만, 5,000행 배치를 반복해 지운다(실제 worker 로 실행)."""
    from tests.e2e.conftest import celery_client

    now = datetime.now(UTC)
    old, kept = f"/e2e/old/{uuid.uuid4().hex}", f"/e2e/kept/{uuid.uuid4().hex}"
    _insert_logs(stack, [now - timedelta(days=400)] * 10_001, old)  # 배치 3번(5000·5000·1)
    _insert_logs(stack, [now - timedelta(days=365) + timedelta(minutes=5)] * 3, kept)
    result = celery_client(stack).send_task("home.purge_expired_access_logs").get(timeout=120)
    assert result["deleted"] >= 10_001, result
    assert _count(stack, old) == 0
    assert _count(stack, kept) == 3
    cover("L3", "5 보존 삭제 태스크")
    cover("Celery", "home.purge_expired_access_logs")


# ---------------------------------------------------------------------------
# 6. 매출 일별 조회: 업무일(TIME_ZONE=Asia/Seoul) 경계
# ---------------------------------------------------------------------------


def test_daily_sales_groups_by_local_business_day(api, stack, cover):
    admin = api.admin()
    # 실행마다 다른 날짜 — compose 를 내리지 않고 다시 돌려도 앞 실행의 주문과 섞이지 않는다.
    day = datetime(2040, 1, 1, tzinfo=UTC) + timedelta(days=secrets.randbelow(20_000))
    d0, d1 = day.date().isoformat(), (day + timedelta(days=1)).date().isoformat()
    # KST 자정 = UTC 15:00. 그날 14:59:59 UTC 는 d0(KST), 15:00:00 UTC 는 d1(KST).
    orders = [
        (day.replace(hour=14, minute=59, second=59), "10.00"),
        (day.replace(hour=15), "20.00"),
        (day.replace(hour=15, minute=1), "5.50"),
    ]
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO sales_orders (id, order_no, customer_email, total_amount, created_at)"
            " VALUES (%s, %s, 'buyer@example.com', %s, %s)",
            [
                (str(uuid.uuid4()), uuid.uuid4().hex[:20], amount, at.replace(tzinfo=None))
                for at, amount in orders
            ],
        )
    params = {"start_date": d0, "end_date": d1}
    report = wait_until(
        lambda: (
            api.request("GET", f"{V1}/reports/sales/daily", params=params, headers=admin.auth)
        ).json()["items"],
        15,
        "리포트 복제",
    )
    got = {i["sales_date"]: (i["order_count"], i["gross_amount"]) for i in report}
    assert got == {d0: (1, "10.00"), d1: (2, "25.50")}, got
    cover("L3", "6 매출 업무일 경계")


# ---------------------------------------------------------------------------
# 7. Celery: worker 를 통한 왕복, beat 스케줄 등록
# ---------------------------------------------------------------------------


def test_celery_round_trip_and_beat_schedule(stack, worker, inventory, cover):
    from tests.e2e.conftest import celery_client

    result = celery_client(stack).send_task("home.aggregate_access_stats").get(timeout=60)
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_access_logs")
        total = cur.fetchone()[0]
    assert abs(result["total"] - total) <= 50, (result, total)  # 그 사이 접속 로그가 쌓일 수 있다
    beat = inventory["beat"]["home.purge_expired_access_logs"]
    assert beat["task"] == "home.purge_expired_access_logs"
    assert "30 3 * * *" in beat["schedule"]
    cover("L3", "7 Celery 왕복·beat")
    cover("Celery", "home.aggregate_access_stats")
    cover("Redis", "celery")


# ---------------------------------------------------------------------------
# 8. 읽기/쓰기 분리: 쓰기는 primary, 이후 읽기는 replica (연결 대상으로 확인)
# ---------------------------------------------------------------------------


def test_reads_go_to_the_replica_and_writes_to_the_primary(api, stack, cover):
    user = api.user()
    with stack.mysql(root=True, replica=True) as replica, replica.cursor() as cur:
        cur.execute("STOP REPLICA SQL_THREAD")
        try:
            made = api.request(
                "POST", f"{V1}/blog/posts", json={"title": "rw", "content": "c"}, headers=user.auth
            )
            assert made.status_code == 201, made.text  # 쓰기 + 같은 요청의 응답(sticky) = primary
            post = f"{V1}/blog/posts/{made.json()['id']}"
            time.sleep(0.5)
            assert api.request("GET", post).status_code == 404  # 읽기 = 멈춘 replica
            patched = api.request("PATCH", post, json={"title": "rw2"}, headers=user.auth)
            assert patched.status_code == 200  # 쓰기 핸들러의 조회도 primary(get_writer_db_session)
        finally:
            cur.execute("START REPLICA SQL_THREAD")
    got = wait_until(
        lambda: (r := api.request("GET", post)).status_code == 200 and r, 15, "복제 재개"
    )
    assert got.json()["title"] == "rw2"
    cover("L3", "8 읽기/쓰기 분리")
