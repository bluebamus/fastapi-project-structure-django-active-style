"""L3-8 읽기/쓰기 분리 + MySQL 접속 (실제 GTID 복제 위)."""

from __future__ import annotations

import secrets

from tests.e2e.conftest import DB_USER


def test_reads_survive_an_empty_auth_cache(stack, app, api, cover):
    """서버 인증 캐시가 비어도(재기동·복제로 받은 계정) 앱이 TLS 없이 붙는다 — F-001.

    primary 에서 비밀번호를 다시 지정하면(같은 값) 그 사용자의 caching_sha2 캐시가 primary·replica
    모두에서 비워진다(복제로 넘어간다). 그다음 replica 를 읽는 목록·primary 를 읽는 /me(integration-e2e ADR-011)와
    primary 에 쓰는 가입이 200·200·201 이어야 한다.
    """
    user = api.user()
    with stack.mysql(root=True) as conn, conn.cursor() as cur:
        cur.execute("ALTER USER %s@'%%' IDENTIFIED BY %s", (DB_USER, stack.db_password))
        cur.execute("SELECT @@GLOBAL.gtid_executed")
        (gtids,) = cur.fetchone()
    with stack.mysql(root=True, replica=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT WAIT_FOR_EXECUTED_GTID_SET(%s, 15)", (gtids,))
        assert cur.fetchone() == (0,), "replica 가 ALTER USER 를 적용하지 못했습니다"
    # 풀에 남은 연결이 아니라 새 연결로 인증하게 앱을 다시 띄운다(기동은 writer 만 ping — 그것도 새 연결이다).
    app.stop()
    app.start()
    fresh = "u_" + secrets.token_hex(5)
    made = api.request(
        "POST",
        "/api/v1/auth/register",
        json={"username": fresh, "email": f"{fresh}@example.com", "password": "Pw-" + fresh},
    )
    assert made.status_code == 201, made.text
    me = api.request("GET", "/api/v1/auth/me", headers=user.auth)
    assert me.status_code == 200, me.text
    listed = api.request("GET", "/api/v1/blog/posts")
    assert listed.status_code == 200, listed.text
    cover("MySQL", "인증 캐시가 빈 서버에 새 연결")
