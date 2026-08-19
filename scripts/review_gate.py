"""검증 게이트 — 로컬과 CI 가 **같은 파일**로 실행하는 단일 진입점 (계획서 §10 Phase 9).

## 왜 스크립트 하나인가

게이트가 CI YAML 안에만 있으면 로컬에서 재현할 방법이 없고, 로컬 문서에만 있으면
아무도 실행하지 않는다. 둘로 나뉘는 순간 "CI 에서만 되는" 상태와 "내 컴퓨터에서만
되는" 상태가 동시에 생긴다. 그래서 명령 목록과 판정 규칙을 이 파일이 소유하고,
CI 는 이 파일을 부르기만 한다.

## 규칙은 순수 함수다

공급망·문서 검사는 전부 `문자열 -> 문제 목록` 함수로 두었다. 그래야
`tests/scripts/test_review_gate.py` 가 **일부러 취약한 입력**을 먹여 검출력 자체를
검증할 수 있다. 통과만 보는 게이트는 고장나도 초록이라, 규칙이 실제로 잡는지를
증명하지 않으면 게이트가 아니라 장식이다.

## UTF-8

출력은 항상 UTF-8 로 쓴다. Windows 한국어 콘솔(cp949)에서 인코딩 불가 문자를 만나
게이트 자체가 죽은 적이 있다 — 게이트가 죽으면 종료 코드가 검사 결과가 아니라
콘솔 설정을 반영하게 된다 (F-028).

사용:
    python -m scripts.review_gate              # 전체
    python -m scripts.review_gate --group supply docs
    python -m scripts.review_gate --list
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess  # nosec B404 - 검증 도구를 고정된 인자 목록으로만 실행한다
import sys
from collections.abc import Iterable

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 공급망 규칙
# ---------------------------------------------------------------------------

# `uses: owner/repo@ref` 에서 ref 를 뽑는다. 로컬 액션(`./.github/...`)과 docker
# 액션은 태그 개념이 없으므로 대상이 아니다.
_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")

_IMAGE = re.compile(r"^\s*image:\s*([^\s#]+)", re.MULTILINE)
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def check_action_pins(workflow_text: str) -> list[str]:
    """GitHub Action 은 태그가 아니라 commit SHA 로 고정해야 한다.

    태그는 움직인다. `@v4` 는 저자가 언제든 다른 커밋을 가리키게 만들 수 있고,
    그 커밋은 우리 CI 안에서 저장소 내용과 토큰에 접근한다. 검토한 커밋에
    못박아야 "검토했다" 는 말이 의미를 갖는다.
    """
    problems = []
    for reference in _USES.findall(workflow_text):
        if reference.startswith(("./", "docker://")):
            continue
        _, separator, ref = reference.partition("@")
        if not separator:
            problems.append(f"{reference}: 버전 지정이 없습니다")
        elif not _COMMIT_SHA.match(ref):
            problems.append(f"{reference}: 태그가 아니라 40자리 commit SHA 로 고정하세요")
    return problems


def check_image_digests(compose_text: str) -> list[str]:
    """컨테이너 이미지는 digest 로 고정해야 한다.

    `mysql:8.4` 는 재빌드될 때마다 다른 바이트를 가리킬 수 있다. 테스트가 무엇에
    대고 통과했는지 특정할 수 없으면 그 초록은 재현 가능한 근거가 아니다.
    """
    return [
        f"{image}: tag 가 아니라 @sha256:<digest> 로 고정하세요"
        for image in _IMAGE.findall(compose_text)
        if not _DIGEST.search(image)
    ]


# 값이 실제로 들어 있는 형태만 잡는다. 이름만 나열한 문서·예시는 대상이 아니다.
_SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    (
        "hardcoded secret literal",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret)
            \s*[=:]\s*
            ["'][A-Za-z0-9/+_-]{20,}["']
            """
        ),
    ),
]


# 이 표기가 있는 **줄**은 검사에서 제외한다. 스캐너의 검출력을 증명하려면 진짜처럼
# 생긴 값이 저장소 안에 있어야 하는데(테스트 fixture), 그 값 때문에 게이트가 영원히
# 빨간불이면 아무도 게이트를 켜두지 않는다. 파일 단위 제외가 아니라 줄 단위인 이유는,
# 파일을 통째로 빼면 그 파일에 들어온 **진짜** 비밀도 함께 빠지기 때문이다.
SECRET_ALLOW_PRAGMA = "gate-allow-secret"


def scan_secrets(text: str) -> list[str]:
    """소스·문서·CI artifact 에 실제 비밀값이 들어갔는지 본다.

    placeholder 는 통과시킨다. `change-this-...` 같은 자리표시자까지 막으면
    개발자가 규칙을 끄게 되고, 그러면 진짜 비밀도 함께 통과한다.
    """
    text = "\n".join(line for line in text.splitlines() if SECRET_ALLOW_PRAGMA not in line)
    if "change-this" in text or "your-" in text:
        text = re.sub(r"['\"](?:change-this|your-)[^'\"]*['\"]", '"<placeholder>"', text)
    return [
        f"{label} 로 보이는 값이 있습니다"
        for label, pattern in _SECRET_PATTERNS
        if pattern.search(text)
    ]


# ---------------------------------------------------------------------------
# 문서 규칙
# ---------------------------------------------------------------------------

# 경로만 검사한다. 슬래시 없는 맨 파일명은 위치가 아니라 **명명 규칙**을 가리키는
# 경우가 많고(README 의 "쓰지 말 것" 반례 표), 그걸 존재 검사에 넣으면 규칙이
# 문서를 거짓으로 고발한다.
_DOC_PATH = re.compile(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+\.(?:py|ya?ml|toml|json|ini|cfg|txt))`")

# 환경변수는 **대입 형태**로만 인식한다. 백틱 안의 대문자 토큰을 전부 환경변수로
# 보면 `WITH`(SQL), `POST`(HTTP), `HS256`(알고리즘)까지 잡혀 규칙이 무의미해진다.
_DOC_ENV = re.compile(r"\b([A-Z][A-Z0-9_]{3,})=")


def check_doc_paths(
    doc_text: str, known_paths: Iterable[str], allowed_missing: set[str]
) -> list[str]:
    """문서가 언급하는 파일이 실제로 존재하는지 본다.

    문서는 `db/session.py` 처럼 앞을 생략해 쓰는 일이 많아 저장소 루트 기준
    존재 검사로는 오탐이 쏟아진다. 그래서 **접미사 일치**로 판정한다 — 실제
    파일 경로의 끝과 맞으면 통과다.

    `allowed_missing` 은 아직 만들지 않은 것을 가리키는 의도적 전방 참조다
    (예: 이월된 결함이 예고하는 파일). 목록에 두어 "빠뜨린 것" 과 구분한다.
    """
    known = list(known_paths)
    problems = []
    for reference in sorted(set(_DOC_PATH.findall(doc_text))):
        if reference in allowed_missing:
            continue
        needle = reference.replace("\\", "/")
        if not any(path.endswith(needle) for path in known):
            problems.append(f"{reference}: 저장소에 없는 경로입니다")
    return problems


# Phase 2 가 정식화한 Dependency 이름과 그 이전의 별칭. 문서가 별칭을 가르치면
# 사람이 그대로 따라 쓰고, 특히 `get_session` 은 **쓰기용이 아니라 동적 라우팅**이라
# 따라 한 사람의 쓰기가 승인되지 않은 경로로 나간다. 생성기 템플릿에서 같은 일이
# 실제로 일어났다(F-025) — 코드 스캔 범위 밖이라 문서에서도 따로 막는다.
DEPRECATED_SESSION_ALIASES = {
    "get_session": "get_routed_db_session (쓰기에는 get_writer_db_session)",
    "get_read_session": "get_read_only_db_session",
    "get_write_session": "get_writer_db_session",
    "get_background_session": "get_background_db_session",
    "background_session": "background_db_session",
}


def check_doc_deprecated_names(doc_text: str) -> list[str]:
    """문서가 폐기된 Dependency 별칭을 가르치지 않는지 본다."""
    problems = []
    for alias, canonical in DEPRECATED_SESSION_ALIASES.items():
        # 정식 이름이 별칭을 부분 문자열로 포함하지 않도록 경계를 건다.
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", doc_text):
            problems.append(f"폐기된 별칭 `{alias}` 을 가르칩니다 — `{canonical}` 을 쓰세요")
    return problems


def check_doc_env_vars(
    doc_text: str, known_env: Iterable[str], allowed_missing: set[str]
) -> list[str]:
    """문서가 언급하는 환경변수가 설정 계층에 실제로 존재하는지 본다."""
    known = set(known_env)
    return [
        f"{name}: 설정에 없는 환경변수입니다"
        for name in sorted(set(_DOC_ENV.findall(doc_text)))
        if name not in known and name not in allowed_missing
    ]


# ---------------------------------------------------------------------------
# pytest 요약 판정
# ---------------------------------------------------------------------------

_BAD_OUTCOMES = ("skipped", "xfailed", "xpassed")


def judge_pytest_summary(log: str, *, allow_deselected: bool) -> list[str]:
    """전체 suite 는 조용한 SKIP 을 허용하지 않는다.

    통과 개수만 보면 비활성화된 테스트가 초록 뒤에 숨는다. `deselected` 는
    marker 필터가 만드는 정상 결과라 marker 실행에서만 허용하고, 전체 suite 에서는
    거부한다 — 전체를 돌린다면서 일부를 골라내면 그 결과는 전체가 아니다.
    """
    outcomes = _BAD_OUTCOMES if allow_deselected else (*_BAD_OUTCOMES, "deselected")
    return [
        f"pytest 요약에 '{outcome}' 가 있습니다"
        for outcome in outcomes
        if re.search(rf"\b[1-9][0-9]* {outcome}\b", log)
    ]


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

_PY = [sys.executable, "-m"]

COMMAND_GROUPS: dict[str, list[list[str]]] = {
    "static": [
        [*_PY, "ruff", "check", "."],
        [*_PY, "ruff", "format", "--check", "."],
        [*_PY, "mypy", "."],
        [*_PY, "bandit", "-ll", "-q", "-r", "app", "main.py", "config.py"],
    ],
    "tests": [
        [*_PY, "pytest", "-q", "-rsxX"],
        [*_PY, "pytest", "--collect-only", "-q"],
    ],
    "structure": [
        [*_PY, "alembic", "heads"],
    ],
}


def _run(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(  # nosec B603 - 인자 목록 고정, shell 미사용
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode, completed.stdout + completed.stderr


def _config_env_names() -> set[str]:
    """설정 계층이 아는 환경변수 이름."""
    sys.path.insert(0, str(REPO_ROOT))
    import config  # noqa: PLC0415  (게이트 실행 시점에만 필요하다)

    names: set[str] = set()
    for attribute in vars(config).values():
        # 인스턴스 접근은 Pydantic 2.11 에서 폐기됐다 — 클래스에서 읽는다.
        fields = getattr(type(attribute), "model_fields", None)
        if fields:
            names.update(fields)
    return names


def _repo_files() -> list[str]:
    ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
    return [
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in REPO_ROOT.rglob("*")
        if path.is_file() and not ignored & set(path.parts)
    ]


# 의도적 전방 참조 — 이월된 결함이 예고하는 산출물이다. 만들어지면 여기서 지운다.
DOC_ALLOWED_MISSING_PATHS = {"app/core/resources.py"}
DOC_ALLOWED_MISSING_ENV = {
    "LOG_SQL_ECHO_ENABLED",  # F-018 이 예고하는 설정(Phase 1-R2)
}

# 앱이 정의하지 않지만 문서가 정당하게 언급하는 외부 환경변수. 인터프리터·도구·CI 가
# 소유하며, 설정 계층에 없다고 해서 오타가 아니다.
EXTERNAL_ENV = {
    "PYTHONPATH",
    "PYTHONIOENCODING",
    "PYTHONDONTWRITEBYTECODE",
    "PATH",
    "TZ",
    "CI",
    "GITHUB_TOKEN",
    "MYSQL_TEST_PORT",
    "ALEMBIC_DATABASE_URL",
}


def check_supply_chain() -> list[str]:
    problems: list[str] = []
    for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        problems += [f"{workflow.name}: {issue}" for issue in check_action_pins(text)]
    for compose in sorted(REPO_ROOT.glob("compose*.y*ml")):
        text = compose.read_text(encoding="utf-8")
        problems += [f"{compose.name}: {issue}" for issue in check_image_digests(text)]
    for path in _repo_files():
        if not path.endswith((".py", ".md", ".yml", ".yaml", ".toml", ".env", ".example")):
            continue
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        problems += [f"{path}: {issue}" for issue in scan_secrets(text)]
    return problems


def check_docs() -> list[str]:
    known_paths = _repo_files()
    known_env = _config_env_names() | EXTERNAL_ENV
    targets = sorted((REPO_ROOT / "docs" / "crp").rglob("*.md"))
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        targets.append(readme)

    problems: list[str] = []
    for doc in targets:
        text = doc.read_text(encoding="utf-8")
        name = str(doc.relative_to(REPO_ROOT)).replace("\\", "/")
        problems += [
            f"{name}: {issue}"
            for issue in check_doc_paths(text, known_paths, DOC_ALLOWED_MISSING_PATHS)
        ]
        problems += [
            f"{name}: {issue}"
            for issue in check_doc_env_vars(text, known_env, DOC_ALLOWED_MISSING_ENV)
        ]
        # 별칭 검사는 **가르치는 문서**에만 적용한다. `docs/crp/` 는 무슨 일이
        # 있었는지에 대한 기록이라 옛 이름을 그대로 불러야 한다 — 기록에까지
        # 규칙을 걸면 사실을 쓸 수 없게 된다.
        if not name.startswith("docs/crp/"):
            problems += [f"{name}: {issue}" for issue in check_doc_deprecated_names(text)]
    return problems


def check_dependencies() -> list[str]:
    code, output = _run([*_PY, "pip_audit", "--strict", "--progress-spinner", "off"])
    if code != 0:
        return [f"pip-audit 실패:\n{output.strip()}"]
    return []


ANALYSIS_GROUPS = {
    "supply": check_supply_chain,
    "docs": check_docs,
    "deps": check_dependencies,
}

ALL_GROUPS = [*COMMAND_GROUPS, *ANALYSIS_GROUPS]


def run_group(name: str) -> list[str]:
    """그룹 하나를 실행하고 문제 목록을 돌려준다(빈 목록이면 통과)."""
    if name in ANALYSIS_GROUPS:
        return ANALYSIS_GROUPS[name]()

    problems: list[str] = []
    for command in COMMAND_GROUPS[name]:
        label = " ".join(command[2:]) or command[0]
        code, output = _run(command)
        if code != 0:
            problems.append(f"{label} 실패 (exit {code}):\n{output.strip()[-2000:]}")
            continue
        if command[2:3] == ["pytest"] and "--collect-only" not in command:
            problems += [
                f"{label}: {issue}"
                for issue in judge_pytest_summary(output, allow_deselected=False)
            ]
    return problems


def main(argv: list[str] | None = None) -> int:
    # 게이트가 콘솔 인코딩 때문에 죽으면 종료 코드가 검사 결과를 뜻하지 않게 된다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="로컬/CI 공용 검증 게이트")
    parser.add_argument("--group", nargs="*", choices=ALL_GROUPS, help="실행할 그룹(기본: 전체)")
    parser.add_argument("--list", action="store_true", help="그룹 목록만 출력한다")
    args = parser.parse_args(argv)

    if args.list:
        print(" ".join(ALL_GROUPS))
        return 0

    failures: dict[str, list[str]] = {}
    for name in args.group or ALL_GROUPS:
        print(f"[{name}] 실행")
        problems = run_group(name)
        if problems:
            failures[name] = problems
        print(f"[{name}] {'실패' if problems else '통과'}")

    if not failures:
        print("\n검증 게이트 통과")
        return 0

    print("\n검증 게이트 실패")
    for name, problems in failures.items():
        print(f"\n## {name}")
        for problem in problems:
            print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
