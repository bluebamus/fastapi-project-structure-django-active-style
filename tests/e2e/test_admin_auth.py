"""L4 관리 화면 인증·세션 — 로그인, CSRF(브라우저 밖 직접 요청), 로그아웃, 레이트 리밋, 다른 세션 폐기,
세션 만료(설정을 줄여 재기동), ADMIN_DISABLED 재기동, 그리고 측정 항목(익명 세션·JS 꺼짐)."""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

import pytest

from tests.e2e.conftest import AdminClient, fresh_ip, login, wait_until

V1 = "/api/v1"


def make_superuser(api: Any) -> dict[str, str]:
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
    return {"id": made.json()["id"], "username": name, "password": password}


def logged_in(stack: Any, who: dict[str, str]) -> AdminClient:
    client = AdminClient(stack)
    wait_until(
        lambda: client.login(who["username"], who["password"]).status_code == 302, 15, "관리 로그인"
    )
    return client


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------


def test_browser_login_success_and_wrong_password(new_page, superuser, app, cover):
    page = login(new_page(), superuser["username"], "wrong-password")
    assert "/admin/login" in page.url
    assert page.locator("input[name=password]").count() == 1
    page = login(new_page(), superuser["username"], superuser["password"])
    assert page.url.endswith("/admin/")
    cover("admin 인증", "로그인 정상·틀린 비밀번호")


def test_login_without_csrf_token_is_403(stack, superuser, app, cover):
    client = AdminClient(stack)
    client.csrf()  # 세션은 있지만 토큰을 싣지 않는다
    refused = client.login(superuser["username"], superuser["password"], csrf=False)
    assert refused.status_code == 403
    assert client.request("GET", "/admin/").status_code in (302, 303)
    cover("admin 인증", "로그인 CSRF 없음 403")


def test_admin_login_rate_limit(stack, superuser, app, cover):
    r = stack.redis()
    client = AdminClient(stack)
    for _ in range(5):
        assert client.login(superuser["username"], "wrong-password").status_code == 400
    blocked = client.login(superuser["username"], superuser["password"])
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    key = f"admin:rl:login:{client.ip}:{superuser['username'].lower()}"
    assert 0 < r.ttl(key) <= 6
    wait_until(lambda: not r.exists(key), 15, "관리 로그인 창 만료")
    assert client.login(superuser["username"], superuser["password"]).status_code == 302
    assert r.exists(f"admin:rl:login-ip:{client.ip}")
    cover("admin 인증", "로그인 레이트 리밋")
    cover("Redis", "admin:rl:login:")
    cover("Redis", "admin:rl:login-ip:")


# ---------------------------------------------------------------------------
# CSRF — 브라우저 밖에서 토큰 없이
# ---------------------------------------------------------------------------


def test_state_changes_without_csrf_are_403(stack, api, superuser, app, cover):
    client = logged_in(stack, superuser)
    owner = api.user()
    post = api.request(
        "POST", f"{V1}/blog/posts", json={"title": "x", "content": "y"}, headers=owner.auth
    ).json()["id"]
    attempts = {
        "생성": ("POST", "/admin/post/create", {"data": {"title": "t", "content": "c"}}),
        "수정": ("POST", f"/admin/post/edit/{post}", {"data": {"title": "t", "content": "c"}}),
        "삭제": ("DELETE", f"/admin/post/delete?pks={post}", {}),
        "로그아웃": ("POST", "/admin/logout", {}),
    }
    for name, (method, url, kwargs) in attempts.items():
        response = client.request(method, url, **kwargs)
        assert response.status_code == 403, (name, response.status_code)
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.execute("SELECT title FROM blog_posts WHERE id=%s", (post,))
        assert cur.fetchone() == ("x",)  # 아무것도 바뀌지 않았다
    token = client.csrf("/admin/")
    ok = client.request("DELETE", f"/admin/post/delete?pks={post}", headers={"X-CSRF-Token": token})
    assert ok.status_code == 200  # 토큰을 실으면 같은 요청이 통과한다
    cover("admin 인증", "CSRF 없는 생성·수정·삭제·로그아웃 403")


# ---------------------------------------------------------------------------
# 로그아웃
# ---------------------------------------------------------------------------


def test_logout_is_post_only_and_kills_the_old_cookie(stack, api, app, cover):
    r = stack.redis()
    who = make_superuser(api)
    client = logged_in(stack, who)
    old = client.sid
    (session_key,) = r.smembers(f"admin:user_sessions:{who['id']}")
    assert client.request("GET", "/admin/logout").status_code == 405
    token = client.csrf("/admin/")
    out = client.request("POST", "/admin/logout", data={"csrf_token": token})
    assert out.status_code in (302, 303)
    assert not r.exists(session_key)  # 서버 세션이 지워졌다
    replay = AdminClient(stack)
    replay.sid = old
    page = replay.request("GET", "/admin/")
    assert page.status_code in (302, 303) and "/admin/login" in page.headers["location"]
    cover("admin 인증", "로그아웃 GET 405·POST 후 이전 쿠키 거부")


# ---------------------------------------------------------------------------
# 관리 화면에서 비활성화·강등·삭제 → 그 사용자의 다른 브라우저 세션 폐기
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("change", ["비활성화", "강등", "삭제"])
def test_admin_ui_user_change_revokes_other_sessions(change, admin_page, stack, api, cover):
    victim = make_superuser(api)
    victim_client = logged_in(stack, victim)
    refresh = api.login(victim["username"], victim["password"]).json()["refresh_token"]
    assert victim_client.request("GET", "/admin/").status_code == 200
    page = admin_page
    if change == "삭제":
        wait_until(
            lambda: page.goto(f"/admin/user/details/{victim['id']}").status == 200, 15, "복제"
        )
        page.goto(f"/admin/user/list?search={victim['username']}")
        page.click(f"a[data-pk='{victim['id']}'][data-bs-target='#modal-delete']")
        page.locator("#modal-delete-button").wait_for(state="visible")
        with page.expect_response(lambda resp: resp.request.method == "DELETE") as deleted:
            page.click("#modal-delete-button")
        assert deleted.value.status == 200
        page.wait_for_url("**/admin/user/list**")
    else:
        field = "is_active" if change == "비활성화" else "is_superuser"
        wait_until(lambda: page.goto(f"/admin/user/edit/{victim['id']}").status == 200, 15, "복제")
        page.uncheck(f"[name={field}]")
        with page.expect_navigation():
            page.click("input[type=submit][value=Save]")
    after = victim_client.request("GET", "/admin/")
    assert after.status_code in (302, 303) and "/admin/login" in after.headers["location"]
    assert (
        api.request("POST", f"{V1}/auth/refresh", json={"refresh_token": refresh}).status_code
        == 401
    )
    cover("admin 인증", f"관리 화면 {change} → 다른 세션 폐기")


# ---------------------------------------------------------------------------
# 측정: 로그인 화면 GET 마다 익명 세션(R-704) · JS 꺼진 브라우저(R-703)
# ---------------------------------------------------------------------------


def test_measure_anonymous_sessions_from_login_page(stack, app, cover):
    """설계상 수용 항목 — 차단하지 않고 측정해 산출물에 남긴다."""
    r = stack.redis()
    before = sum(1 for _ in r.scan_iter("admin:sess:*"))
    for _ in range(50):
        AdminClient(stack).request("GET", "/admin/login")
    keys = list(r.scan_iter("admin:sess:*"))
    ttls = sorted({r.ttl(k) for k in keys if r.ttl(k) > 0})
    measured = {
        "GET /admin/login 50회 전 키": before,
        "후 키": len(keys),
        "증가": len(keys) - before,
        "TTL 범위(초)": [ttls[0], ttls[-1]] if ttls else [],
    }
    (stack.artifacts / "measure-anonymous-sessions.json").write_text(
        json.dumps(measured, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    assert 0 <= len(keys) - before <= 50
    assert not ttls or ttls[-1] <= 1800  # ADMIN_SESSION_IDLE_SECONDS 기본값을 넘지 않는다
    cover("admin 측정", "로그인 화면 익명 세션(R-704)")


def test_measure_javascript_disabled_browser(chromium, stack, superuser, app, cover):
    """JS 가 꺼지면 CSRF 토큰을 붙이는 스크립트가 돌지 않는다 — 상태 변경이 403 이 되는지만 확인한다."""
    ctx = chromium.new_context(
        base_url=stack.base_url,
        java_script_enabled=False,
        extra_http_headers={"X-Forwarded-For": fresh_ip()},
    )
    ctx.set_default_timeout(15_000)
    try:
        page = login(ctx.new_page(), superuser["username"], superuser["password"])
        assert page.url.endswith("/admin/")  # 로그인 폼은 hidden 필드라 JS 없이도 된다
        page.goto("/admin/post/create")
        page.fill("[name=title]", "nojs")
        page.fill("[name=content]", "nojs")
        with page.expect_navigation() as nav:
            page.click("input[type=submit][value=Save]")
        status = nav.value.status if nav.value else None
        (stack.artifacts / "measure-js-disabled.json").write_text(
            json.dumps({"JS 꺼짐 생성 응답": status}), encoding="utf-8"
        )
        assert status == 403
    finally:
        ctx.close()
    cover("admin 측정", "JS 꺼진 브라우저(R-703)")


# ---------------------------------------------------------------------------
# 재기동이 필요한 것: 세션 만료(설정을 줄여서), ADMIN_DISABLED
# ---------------------------------------------------------------------------


@pytest.fixture
def restart(app):
    """설정을 바꿔 앱을 다시 띄우고, 테스트가 끝나면 기본 설정으로 되돌린다."""

    def apply(**overrides: str) -> None:
        app.stop()
        app.start(**overrides)

    yield apply
    app.stop()
    app.start()


def test_admin_session_idle_and_absolute_expiry(restart, stack, superuser, cover):
    restart(ADMIN_SESSION_IDLE_SECONDS="60", ADMIN_SESSION_MAX_AGE_SECONDS="80")
    idle, busy = logged_in(stack, superuser), logged_in(stack, superuser)
    started = time.monotonic()

    def elapsed() -> float:
        return time.monotonic() - started

    while elapsed() < 62:  # busy 는 15초마다 쓴다, idle 은 가만히 둔다
        assert busy.request("GET", "/admin/").status_code == 200, f"{elapsed():.0f}s"
        time.sleep(max(0.0, min(15.0, 62 - elapsed())))
    gone = idle.request("GET", "/admin/")
    assert gone.status_code in (302, 303), "미사용 만료(60s)가 지나도 세션이 살아 있다"
    assert busy.request("GET", "/admin/").status_code == 200
    time.sleep(max(0.0, 85 - elapsed()))
    absolute = busy.request("GET", "/admin/")
    assert absolute.status_code in (302, 303), "절대 만료(80s)가 지나도 세션이 살아 있다"
    cover("admin 인증", "세션 미사용·절대 만료")


def test_admin_disabled_removes_the_admin_surface(restart, stack, api, cover):
    restart(ADMIN_DISABLED="true")
    import httpx

    with httpx.Client(base_url=stack.base_url, timeout=10) as client:
        for path in ("/admin", "/admin/", "/admin/login", "/admin/post/list"):
            assert client.get(path).status_code == 404, path
        assert client.post("/admin/login", data={}).status_code == 404
        for path in ("/", "/health", "/ready"):
            assert "/admin" not in client.get(path).text, path
    assert api.request("GET", f"{V1}/blog/posts").status_code == 200  # API 는 그대로
    cover("admin 인증", "ADMIN_DISABLED 재기동")


# ---------------------------------------------------------------------------
# CSRF 본문 버퍼링 상한 (integration-e2e ADR-012)
# ---------------------------------------------------------------------------

_MiB = 1024 * 1024
_FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _rss(pid: int) -> int:
    """프로세스 RSS(바이트) — Linux 는 /proc, Windows 는 그 프로세스와 자식의 working set 합.

    Windows 의 venv ``python.exe`` 는 실제 인터프리터를 자식으로 띄우는 런처라 자식까지 더한다.
    """
    import os
    import subprocess

    if os.name != "nt":
        with open(f"/proc/{pid}/status", encoding="ascii") as status:
            line = next(x for x in status if x.startswith("VmRSS:"))
        return int(line.split()[1]) * 1024
    query = (
        "(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -eq "
        f"{pid} -or $_.ParentProcessId -eq {pid}"
        " } | Measure-Object -Property WorkingSetSize -Sum).Sum"
    )
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command", query], capture_output=True, text=True, check=True
    )
    return int(done.stdout.strip())


def _declared_too_large(stack: Any) -> bytes:
    """Content-Length 만 11 MiB 로 밝히고 본문은 보내지 않는다 — 앱은 읽기 전에 413 으로 답해야 한다."""
    import socket

    with socket.create_connection(("127.0.0.1", stack.app_port), timeout=30) as sock:
        sock.sendall(
            b"POST /admin/post/create HTTP/1.1\r\nHost: e2e\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            + f"Content-Length: {11 * _MiB}\r\n\r\n".encode()
        )
        return sock.recv(4096)


def test_csrf_form_body_limits(stack, superuser, app, cover):
    client = logged_in(stack, superuser)
    token = client.csrf("/admin/")
    rss_before = _rss(app.proc.popen.pid)
    log_before = len(app.proc.output())

    head = _declared_too_large(stack)
    assert head.startswith(b"HTTP/1.1 413"), head[:200]

    def chunks():  # Content-Length 없이(chunked) 10 MiB 를 넘긴다 — 누적 크기로 판정
        yield f"csrf_token={token}&title=t&pad=".encode()
        for _ in range(10):
            yield b"a" * _MiB

    for _ in range(5):
        chunked = client.request("POST", "/admin/post/create", content=chunks(), headers=_FORM)
        assert chunked.status_code == 413, chunked.text[:200]

    field = f"csrf_token={token}&title=t&content=c&pad=".encode() + b"a" * (2 * _MiB)
    too_big_field = client.request("POST", "/admin/post/create", content=field, headers=_FORM)
    assert too_big_field.status_code == 400, too_big_field.text[:200]
    assert too_big_field.headers.get("connection", "").lower() != "close"
    assert client.request("GET", "/admin/").status_code == 200  # 같은 클라이언트로 계속 쓴다

    rss_after = _rss(app.proc.popen.pid)
    (stack.artifacts / "measure-csrf-body-limit-rss.txt").write_text(
        f"413(Content-Length 11 MiB) 1회 + 413(chunked 10 MiB 초과) 5회 + 400(필드 2 MiB) 1회\n"
        f"uvicorn RSS before={rss_before} after={rss_after} delta={rss_after - rss_before}\n",
        encoding="utf-8",
    )
    assert "Traceback" not in app.proc.output()[log_before:]  # 500·처리되지 않은 예외 없음
    cover("admin 인증", "CSRF 본문 상한 413·필드 400")
