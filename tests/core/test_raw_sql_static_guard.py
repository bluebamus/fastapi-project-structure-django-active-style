"""`text()` 에 조립한 SQL 이 들어가지 못하게 막는 정적 가드 (지침서 §6, RAW-REP-003).

주입은 리뷰로 막는 종류의 결함이 아니다. 한 번만 놓쳐도 되고, 놓친 자리는 대개
"급해서 잠깐" 이라 리뷰가 가장 느슨한 시점에 들어온다. 그래서 코드가 코드를 검사한다.

Phase 6 은 Base 계약(named parameter, multi-statement 거부)을 세웠고, Phase 8 에서
**기능이 실제 SQL 을 소유하기 시작**했다. 이 시점부터 이 가드가 의미를 가진다.

## 무엇을 거부하는가

    text(f"SELECT ... {value}")        f-string
    text("SELECT ... " + value)        문자열 연결
    text("SELECT ... %s" % value)      포맷 연산
    text("SELECT ...".format(value))   format 호출
    text(statement)                    다른 곳에서 조립된 변수

허용은 리터럴 상수 하나뿐이다. 식별자 선택이 필요하면 `ensure_identifier()` 로
코드가 소유한 allowlist 를 통과시킨다.

## 검사 범위

`app/`, `main.py`, `scripts/`, `migrations/` — 운영에 나가는 표면 전부다.
`scripts/` 를 넣는 이유는 Phase 7 의 F-025 때문이다: 생성기 템플릿이 스캔 범위 밖이라
폐기된 패턴을 계속 가르치고 있었다. 생성기는 코드를 **찍어내므로** 오히려 더 넓게
퍼진다.

테스트 디렉터리는 제외한다 — 거부 동작 자체를 검증하려면 나쁜 SQL 을 일부러
만들어야 한다.
"""

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = ["app", "scripts", "migrations"]


def _python_files() -> list[Path]:
    files = [_REPO_ROOT / "main.py"]
    for root in _SCAN_ROOTS:
        files.extend(
            path
            for path in (_REPO_ROOT / root).rglob("*.py")
            if "tests" not in path.parts and "__pycache__" not in path.parts
        )
    return sorted(files)


def _is_text_call(node: ast.AST) -> bool:
    """`text(...)` 호출인가. `read_text(...)`/`write_text(...)` 는 아니다."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "text"
    return isinstance(func, ast.Attribute) and func.attr == "text"


def _offenders(source: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not _is_text_call(node) or not node.args:
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            continue
        found.append((node.lineno, type(argument).__name__))
    return found


def test_scan_actually_covers_the_repository():
    """범위가 비면 이 파일은 아무것도 검증하지 않는 초록이 된다."""
    files = _python_files()

    assert len(files) > 50
    assert any(path.name == "sales_report_repository.py" for path in files)
    assert any(path.name == "new_app.py" for path in files)


def test_text_receives_only_literal_sql():
    offenders = {
        str(path.relative_to(_REPO_ROOT)): found
        for path in _python_files()
        if (found := _offenders(path.read_text(encoding="utf-8")))
    }

    assert not offenders, (
        f"조립된 SQL 이 text() 로 들어갑니다: {offenders}. "
        "SQL 은 리터럴 상수로 두고 값은 named bind, 식별자는 allowlist 로 넘기세요."
    )


@pytest.mark.parametrize(
    "source",
    [
        'text(f"SELECT * FROM t WHERE id = {user_id}")',
        'text("SELECT * FROM " + table)',
        'text("SELECT * FROM t WHERE id = %s" % user_id)',
        'text("SELECT {}".format(column))',
        "text(statement)",
    ],
    ids=["f-string", "concat", "percent", "format", "variable"],
)
def test_guard_detects_assembled_sql(source):
    """가드가 실제로 잡는지 확인한다 — 통과만 보는 검사는 고장나도 초록이다."""
    assert _offenders(source)


def test_guard_allows_literal_sql():
    assert not _offenders('text("SELECT * FROM t WHERE id = :id")')


def test_guard_ignores_path_read_text():
    """`Path.read_text()` 는 SQL 이 아니다 — 이름이 비슷하다고 잡으면 안 된다."""
    assert not _offenders("path.read_text(encoding=encoding)")
