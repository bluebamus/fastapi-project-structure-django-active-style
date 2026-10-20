"""W3 인벤토리 대조 — 실제 앱에서 뽑은 대상마다 그것을 실행한 테스트가 있는지 본다(빈 칸 0).

이 모듈은 다른 e2e 테스트가 모두 끝난 뒤에 돈다(conftest 가 맨 뒤로 옮긴다). 대조표는 산출물
``inventory.md`` 에 남는다. 해당하지 않는 칸은 사유와 함께 N/A 다 — 사유 없는 빈 칸은 실패다.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.e2e.conftest import COVERAGE, ISSUED, REPO
from tests.e2e.test_api_matrix import OPS, PUBLIC, PUBLIC_WRITE, SUPER

API_COLUMNS = [
    "정상",
    "검증 오류",
    "미인증",
    "권한 부족",
    "없음",
    "잘못된 메서드",
    "접근 정책 대조",
]
ADMIN_COLUMNS = [
    "목록",
    "상세",
    "생성",
    "수정",
    "삭제",
    "일괄 삭제",
    "내보내기",
    "날짜 필터 on",
    "날짜 필터 on_or_after",
    "날짜 필터 before",
    "날짜 필터 range(기간 UI)",
]
ADMIN_CAP = {"생성": "create", "수정": "edit", "삭제": "delete", "일괄 삭제": "delete"}
SCENARIOS = {
    "L3": [
        "1 인증 수명주기",
        "2 로그인 레이트 리밋",
        "2 로그인 IP 레이트 리밋",
        "2 가입 레이트 리밋",
        "3 소유권 blog",
        "3 소유권 sns",
        "3 소유권 reply",
        "4 사용자 변경 폐기 is_active",
        "4 사용자 변경 폐기 is_superuser",
        "4 사용자 변경 폐기 delete",
        "5 접속 로그 적재·조회",
        "5 보존 삭제 태스크",
        "6 매출 업무일 경계",
        "7 Celery 왕복·beat",
        "8 읽기/쓰기 분리",
    ],
    "admin 인증": [
        "로그인 정상·틀린 비밀번호",
        "로그인 CSRF 없음 403",
        "로그인 레이트 리밋",
        "CSRF 없는 생성·수정·삭제·로그아웃 403",
        "로그아웃 GET 405·POST 후 이전 쿠키 거부",
        "관리 화면 비활성화 → 다른 세션 폐기",
        "관리 화면 강등 → 다른 세션 폐기",
        "관리 화면 삭제 → 다른 세션 폐기",
        "세션 미사용·절대 만료",
        "ADMIN_DISABLED 재기동",
    ],
    "admin 측정": ["로그인 화면 익명 세션(R-704)", "JS 꺼진 브라우저(R-703)"],
    "L5": [
        "Redis 정지·재기동",
        "MySQL primary 정지",
        "MySQL replica 정지",
        "MySQL replica 지연",
        "Celery worker 정지·재기동",
    ],
    "L6": [
        "1 Alembic 왕복·스키마 비교",
        "2 create_superuser 생성·승격·비밀번호",
        "3 기동 거부 Redis 최소 버전 미달",
        "3 기동 거부 레거시 ADMIN 변수",
        "3 기동 거부 ADMIN_SESSION 미사용>절대",
        "3 기동 거부 ADMIN_SESSION 최소값 미만",
        "3 기동 거부 접근 정책 미선언",
        "로깅 경로별 형식·헤더·프로세스별 파일",
        "로깅 python main.py 경로",
        "로깅 앱별 레벨",
        "로깅 크기 교체·보관 삭제",
        "로깅 기동 초기 줄",
    ],
    "MySQL": ["인증 캐시가 빈 서버에 새 연결"],
}
#: Celery·kombu 가 만드는 키(브로커·결과 백엔드). 앱 코드의 접두어는 소스에서 뽑는다.
CELERY_KEYS = re.compile(r"^(celery-task-meta-|_kombu\.|unacked|celery$)")


def not_applicable(op_key: str, column: str) -> str | None:
    """API 칸이 해당하지 않으면 사유를, 해당하면 None."""
    op = OPS[op_key]
    public = op.level in (PUBLIC, PUBLIC_WRITE)
    if column == "검증 오류" and not op.bad:
        return "입력이 없다(경로 변수는 문자열이라 형식 검증 없음)"
    if column == "미인증" and public:
        return f"{op.level} — 인증 없이 쓰는 operation"
    if column == "권한 부족" and not op.owned:
        return (
            f"{op.level} — 공개" if public else "로그인만 요구, 소유권 대상 아님(본인 것만 다룬다)"
        )
    if column == "없음" and not op.missing:
        if "{" in op_key and op.level == SUPER:
            return "조회 조건 값 — 없는 값은 빈 목록(200)"
        return "경로 변수 없음"
    return None


def redis_prefixes() -> set[str]:
    """앱 코드가 만드는 Redis 키의 고정 접두어(f-string 의 첫 `{` 앞)."""
    found = set()
    for path in (REPO / "app").rglob("*.py"):
        if "tests" in path.parts:
            continue
        for match in re.finditer(
            r'f"((?:admin|auth):[a-z_:-]*)\{', path.read_text(encoding="utf-8")
        ):
            found.add(match.group(1))
    return found


def test_inventory_has_no_empty_cells(inventory, stack):
    rows: list[str] = []
    empty: list[str] = []

    def cell(group: str, item: str, column: str, reason: str | None = None) -> None:
        key = (
            f"{item} | {column}"
            if group == "API"
            else f"{group} | {item}"
            if column == ""
            else (f"{group} {item} | {column}")
        )
        tests = COVERAGE.get(key)
        if tests:
            rows.append(f"| {group} | {item} | {column} | 실행 | {len(tests)} |")
        elif reason:
            rows.append(f"| {group} | {item} | {column} | N/A — {reason} | 0 |")
        else:
            empty.append(key)
            rows.append(f"| {group} | {item} | {column} | **빈 칸** | 0 |")

    # API: 인벤토리(OpenAPI)와 매트릭스 정의가 정확히 같아야 한다
    operations = {
        f"{m.upper()} {p}" for p, ops in inventory["openapi"]["paths"].items() for m in ops
    }
    assert operations == set(OPS), (sorted(operations - set(OPS)), sorted(set(OPS) - operations))
    assert set(inventory["access"]) == operations
    for op_key in sorted(operations):
        for column in API_COLUMNS:
            cell("API", op_key, column, not_applicable(op_key, column))

    # 관리 화면: 뷰마다 동작, 막힌 동작은 거부 확인이 실행됐어야 한다
    assert len(inventory["admin_views"]) == 7
    for view in inventory["admin_views"]:
        for column in ADMIN_COLUMNS:
            cap = ADMIN_CAP.get(column)
            if cap and not view[cap]:
                cell("admin", view["identity"], f"{column}(차단)")
                rows[-1] = rows[-1].replace(
                    " | 실행 |", f" | N/A — can_{cap}=False(거부 확인 실행) |"
                )
            else:
                cell("admin", view["identity"], column)

    for task in inventory["tasks"]:
        cell("Celery", task, "")
    for prefix in sorted(redis_prefixes() | {"celery"}):
        cell("Redis", prefix, "")
    for group, items in SCENARIOS.items():
        for item in items:
            cell(group, item, "")

    (stack.artifacts / "inventory.md").write_text(
        "| 구분 | 대상 | 칸 | 결과 | 테스트 수 |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    assert not empty, f"빈 칸 {len(empty)}개: {empty[:20]}"


def test_redis_holds_only_known_key_prefixes(stack):
    known = tuple(redis_prefixes())
    unknown = sorted(
        key
        for key in stack.redis().scan_iter("*")
        if not key.startswith(known) and not CELERY_KEYS.match(key)
    )
    assert not unknown, unknown[:20]


def test_no_secret_reaches_any_log(stack):
    """실행마다 만든 비밀값·사용자 비밀번호·발급한 토큰이 앱·worker·uvicorn 로그 어디에도 없다."""
    secrets_ = {s for s in (*stack.all_secrets(), *ISSUED) if len(s) >= 8}
    assert len(secrets_) > 20, "비밀값 수집이 비었다 — 검사가 헛돈다"
    files = [p for p in Path(stack.artifacts).rglob("*") if p.is_file()]
    assert any(p.name == "app.log" for p in files) and any(p.name == "celery.log" for p in files)
    leaks: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        leaks += [f"{path.name}: {s[:6]}…" for s in secrets_ if s in text]
        if re.search(r"(mysql\+\w+|redis)://[^:\s/]+:(?!\*\*\*@)[^@\s]+@", text):
            leaks.append(f"{path.name}: DSN 원문")
    assert not leaks, leaks[:20]
