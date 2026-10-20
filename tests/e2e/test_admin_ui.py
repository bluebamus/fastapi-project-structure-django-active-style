"""L4 관리 화면 — 실제 Chromium + 실제 MySQL·Redis.

뷰마다(인벤토리의 7 뷰) 목록·상세·생성·수정·삭제·일괄 삭제·내보내기·날짜 필터 4종(같은 날·이후·이전·기간 UI)을
브라우저로 돌리고, 결과를 primary DB 에서 확인한다. 뷰가 막아 둔 동작(can_* = False)은 화면이 거부하는지만 본다.

삭제는 sqladmin 이 AJAX DELETE 뒤 목록으로 이동한다 — 그 응답과 목록 URL 이동을 기다린 다음에야 다음 동작을
한다(이동 중 goto·close 는 ERR_ABORTED 나 정지로 이어진다).
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytest

from tests.e2e.conftest import wait_until

KST = timedelta(hours=9)


# ---------------------------------------------------------------------------
# 뷰 정의: 시드(SQL, created_at 지정)·생성 폼·수정 필드·표시 열
# ---------------------------------------------------------------------------


@dataclass
class View:
    identity: str
    table: str
    marker: str  # 목록·상세·내보내기에서 찾는 열(값에 표식을 넣는다)
    seed: str  # INSERT ... VALUES (%(id)s, %(m)s, %(at)s ...)
    create: dict[str, str] | None = None
    edit: str | None = None


VIEWS = [
    View(
        "post",
        "blog_posts",
        "title",
        "INSERT INTO blog_posts (id,title,content,created_at,updated_at)"
        " VALUES (%(id)s,%(m)s,'c',%(at)s,%(at)s)",
        create={"title": "{m}", "content": "c"},
        edit="title",
    ),
    View(
        "sns-post",
        "sns_posts",
        "content",
        "INSERT INTO sns_posts (id,content,like_count,created_at,updated_at)"
        " VALUES (%(id)s,%(m)s,0,%(at)s,%(at)s)",
        create={"content": "{m}"},
        edit="content",
    ),
    View(
        "reply",
        "replies",
        "content",
        "INSERT INTO replies (id,content,created_at,updated_at) VALUES (%(id)s,%(m)s,%(at)s,%(at)s)",
        create={"content": "{m}"},
        edit="content",
    ),
    View(
        "product",
        "catalog_products",
        "name",
        "INSERT INTO catalog_products (id,name,price,is_active,created_at,updated_at)"
        " VALUES (%(id)s,%(m)s,1.00,1,%(at)s,%(at)s)",
        create={"name": "{m}", "price": "4.20"},
        edit="name",
    ),
    View(
        "user-access-log",
        "user_access_logs",
        "request_path",
        "INSERT INTO user_access_logs (id,ip_address,is_bot,request_path,request_method,created_at)"
        " VALUES (%(id)s,'10.98.0.1',0,%(m)s,'GET',%(at)s)",
    ),
    View(
        "sales-order",
        "sales_orders",
        "order_no",
        "INSERT INTO sales_orders (id,order_no,customer_email,total_amount,created_at)"
        " VALUES (%(id)s,%(m)s,'b@example.com',1.00,%(at)s)",
    ),
    View(
        "user",
        "users",
        "username",
        "INSERT INTO users (id,username,email,is_active,is_superuser,created_at,updated_at)"
        " VALUES (%(id)s,%(m)s,'s@example.com',1,0,%(at)s,%(at)s)",
        edit="email",
    ),
]


@dataclass
class Seeded:
    day: str  # 가운데 날짜(KST)
    prev: tuple[str, str]  # (id, 표식) — day-1
    mid: tuple[str, str]
    next: tuple[str, str]  # day+1


def seed(stack: Any, view: View) -> Seeded:
    """KST 기준 연속 사흘의 정오에 한 행씩. 날짜는 실행마다 먼 미래의 임의 날 — 다른 데이터와 겹치지 않는다."""
    day = datetime(2070, 1, 1) + timedelta(days=secrets.randbelow(10_000))
    rows = []
    with stack.mysql() as conn, conn.cursor() as cur:
        for offset in (-1, 0, 1):
            local_noon = day + timedelta(days=offset, hours=12)
            marker = f"e2e{uuid.uuid4().hex[:12]}"
            row_id = str(uuid.uuid4())
            cur.execute(view.seed, {"id": row_id, "m": marker, "at": local_noon - KST})
            rows.append((row_id, marker))
    return Seeded(day.date().isoformat(), *rows)


def db_value(stack: Any, view: View, row_id: str) -> Any:
    with stack.mysql() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT `{view.marker}` FROM `{view.table}` WHERE id=%s", (row_id,))  # noqa: S608
        found = cur.fetchone()
        return found[0] if found else None


def visible(page: Any, *markers: str) -> dict[str, bool]:
    text = page.content()
    return {m: m in text for m in markers}


def wait_replica(page: Any, url: str, marker: str) -> None:
    """관리 화면 목록은 replica 를 읽는다 — 시드가 복제될 때까지 다시 연다."""
    wait_until(lambda: page.goto(url) and marker in page.content(), 15, f"{url} 에 {marker}")


# ---------------------------------------------------------------------------
# 뷰별 전 흐름
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("view", VIEWS, ids=[v.identity for v in VIEWS])
def test_admin_view_end_to_end(view, admin_page, stack, inventory, cover):
    caps = next(v for v in inventory["admin_views"] if v["identity"] == view.identity)
    assert caps["actions"] == [], "등록된 @action 은 GET 이라 CSRF 밖이다 — 0 이어야 한다"
    page = admin_page
    base = f"/admin/{view.identity}"
    s = seed(stack, view)
    # 목록·필터는 행 id 로 본다(링크에 실린다) — 본문 열은 목록에서 빠진 뷰가 있다.
    ids = (s.prev[0], s.mid[0], s.next[0])

    # 목록(기간 빠른 확인으로 복제 대기) ------------------------------------------------
    listed = page.goto(f"{base}/list")
    assert listed.status == 200
    wait_replica(page, f"{base}/list?created_at={s.day}&created_at_op=on", s.mid[0])
    cover(f"admin {view.identity}", "목록")

    # 날짜 필터 4종 — 화면의 폼으로 -----------------------------------------------------
    page.goto(f"{base}/list?pageSize=100")
    expected = {
        "on": (False, True, False),
        "on_or_after": (False, True, True),
        "before": (True, False, False),
    }
    for op, want in expected.items():
        page.goto(f"{base}/list?pageSize=100")
        form = page.locator("form:has(select[name=created_at_op])")
        form.locator("select[name=created_at_op]").select_option(op)
        form.locator("input[name=created_at]").fill(s.day)
        with page.expect_navigation():
            form.locator("button[type=submit]").click()
        assert f"created_at_op={op}" in page.url
        got = visible(page, *ids)
        assert tuple(got.values()) == want, (op, got)
        cover(f"admin {view.identity}", f"날짜 필터 {op}")
    page.goto(f"{base}/list?pageSize=100")
    span = page.locator("form[data-local-date-range]")
    span.locator("[data-range-start]").fill(s.day)
    span.locator("[data-range-end]").fill(
        (datetime.fromisoformat(s.day) + timedelta(days=1)).date().isoformat()
    )
    with page.expect_navigation():
        span.locator("button[type=submit]").click()
    assert "created_at_op=range" in page.url
    assert tuple(visible(page, *ids).values()) == (False, True, True)
    cover(f"admin {view.identity}", "날짜 필터 range(기간 UI)")

    # 상세 ------------------------------------------------------------------------------
    details = page.goto(f"{base}/details/{s.mid[0]}")
    assert details.status == 200 and s.mid[1] in page.content()
    cover(f"admin {view.identity}", "상세")

    # 내보내기 --------------------------------------------------------------------------
    page.goto(f"{base}/list")
    with page.expect_download() as download:
        page.click("#dropdownMenuButton1")  # Export
        page.click(f"a[href$='{base}/export/csv']")
    exported = open(download.value.path(), encoding="utf-8").read()
    assert s.mid[0] in exported or s.mid[1] in exported  # 내보내기 열 = 목록 열
    cover(f"admin {view.identity}", "내보내기")

    # 생성 ------------------------------------------------------------------------------
    if caps["create"]:
        marker = f"e2e{uuid.uuid4().hex[:12]}"
        page.goto(f"{base}/create")
        for name, value in view.create.items():
            page.fill(f"[name={name}]", value.format(m=marker))
        with page.expect_navigation():
            page.click("input[type=submit][value=Save]")
        with stack.mysql() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM `{view.table}` WHERE `{view.marker}`=%s", (marker,))  # noqa: S608
            assert cur.fetchone()[0] == 1
        cover(f"admin {view.identity}", "생성")
    else:
        refused = page.goto(f"{base}/create")
        assert refused.status in (403, 404), refused.status
        cover(f"admin {view.identity}", "생성(차단)")

    # 수정 ------------------------------------------------------------------------------
    if caps["edit"]:
        page.goto(f"{base}/edit/{s.prev[0]}")
        new_value = f"e2e{uuid.uuid4().hex[:8]}" + ("@example.com" if view.edit == "email" else "")
        page.fill(f"[name={view.edit}]", new_value)
        with page.expect_navigation():
            page.click("input[type=submit][value=Save]")
        with stack.mysql() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT `{view.edit}` FROM `{view.table}` WHERE id=%s", (s.prev[0],))  # noqa: S608
            assert cur.fetchone()[0] == new_value
        cover(f"admin {view.identity}", "수정")
    else:
        refused = page.goto(f"{base}/edit/{s.prev[0]}")
        assert refused.status in (403, 404), refused.status
        cover(f"admin {view.identity}", "수정(차단)")

    # 삭제(행 하나) → 일괄 삭제(나머지 둘) ---------------------------------------------
    if caps["delete"]:
        page.goto(f"{base}/list?created_at={s.day}&created_at_op=on")
        page.click(f"a[data-pk='{s.mid[0]}'][data-bs-target='#modal-delete']")
        page.locator("#modal-delete-button").wait_for(state="visible")
        with page.expect_response(lambda r: r.request.method == "DELETE") as deleted:
            page.click("#modal-delete-button")
        assert deleted.value.status == 200
        page.wait_for_url(f"**{base}/list**")
        page.wait_for_load_state()
        assert db_value(stack, view, s.mid[0]) is None
        cover(f"admin {view.identity}", "삭제")

        end = (datetime.fromisoformat(s.day) + timedelta(days=1)).date().isoformat()
        prev_day = (datetime.fromisoformat(s.day) - timedelta(days=1)).date().isoformat()
        wait_until(
            lambda: page.goto(f"{base}/list?created_at={prev_day}~{end}&created_at_op=range")
            and page.locator("input.select-box").count() == 2,
            15,
            "남은 두 행",
        )
        page.click("#select-all")
        page.click("#dropdownMenuButton")  # Actions
        page.click("#action-delete")
        page.locator("#modal-delete-button").wait_for(state="visible")
        with page.expect_response(lambda r: r.request.method == "DELETE") as bulk:
            page.click("#modal-delete-button")
        assert bulk.value.status == 200, bulk.value.url
        page.wait_for_url(f"**{base}/list**")
        page.wait_for_load_state()
        assert db_value(stack, view, s.prev[0]) is None and db_value(stack, view, s.next[0]) is None
        cover(f"admin {view.identity}", "일괄 삭제")
    else:
        page.goto(f"{base}/list?created_at={s.day}&created_at_op=on")
        assert page.locator("a[data-bs-target='#modal-delete']").count() == 0
        token = page.locator("meta[name=csrf-token]").get_attribute("content")
        refused = page.request.delete(
            f"{base}/delete?pks={s.mid[0]}", headers={"X-CSRF-Token": token}
        )
        assert refused.status in (403, 404, 405), refused.status
        assert db_value(stack, view, s.mid[0]) == s.mid[1]
        cover(f"admin {view.identity}", "삭제(차단)")
        cover(f"admin {view.identity}", "일괄 삭제(차단)")
