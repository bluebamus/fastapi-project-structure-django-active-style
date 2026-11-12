"""검증 게이트 규칙의 **검출력**을 증명한다.

게이트를 통과했다는 사실만으로는 게이트가 동작한다는 증거가 되지 않는다. 규칙이
아무것도 잡지 못하도록 망가져 있어도 결과는 똑같이 초록이기 때문이다. 그래서
각 규칙에 **일부러 취약한 입력**을 먹여 실제로 잡는지 확인하고, 정상 입력에서
오탐이 없는지도 함께 고정한다.

정상 입력 검사가 같이 있어야 하는 이유는, 오탐이 쌓이면 사람이 규칙을 끄기
때문이다. 꺼진 규칙은 없는 규칙과 같다.

게이트가 실제 저장소를 어떻게 판정하는지(현재 통과 상태)는 별도로 확인한다 —
규칙이 맞아도 배선이 틀리면 아무 파일도 검사하지 않는 초록이 나온다.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.review_gate import (
    _repo_files,
    check_action_pins,
    check_doc_env_vars,
    check_doc_paths,
    check_docs,
    find_empty_python_files,
    judge_pytest_summary,
    main,
    scan_secrets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ Action SHA


@pytest.mark.parametrize(
    "reference",
    ["actions/checkout@v4", "actions/checkout@main", "astral-sh/setup-uv@v5.1.2"],
    ids=["major-tag", "branch", "semver-tag"],
)
def test_moving_action_references_are_rejected(reference):
    """태그·브랜치는 움직인다 — 우리 CI 안에서 도는 코드가 바뀔 수 있다."""
    assert check_action_pins(f"      - uses: {reference}\n")


def test_action_without_version_is_rejected():
    assert check_action_pins("      - uses: actions/checkout\n")


def test_sha_pinned_action_passes():
    pinned = "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262  # v4\n"

    assert check_action_pins(pinned) == []


def test_local_action_is_not_subject_to_pinning():
    """저장소 안의 액션은 우리 코드다 — 고정할 외부 참조가 없다."""
    assert check_action_pins("      - uses: ./.github/actions/setup\n") == []


# ------------------------------------------------------------------ 파일 목록


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_repo_files_lists_only_tracked_files(tmp_path, monkeypatch):
    """추적되지 않은 파일(로컬 `.env`·로컬 전용 문서)은 게이트 목록에 없다.

    작업 트리를 훑으면 개발자의 실제 `.env` 가 비밀 스캔에 들어가 로컬에서만 빨개지고,
    로컬 전용 문서가 문서 경로 검사를 로컬에서만 통과시킨다.
    """
    import scripts.review_gate as gate

    _git(tmp_path, "init", "-q")
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# g\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.py", "docs/guide.md")
    (tmp_path / ".env").write_text("SECRET_KEY='not-tracked'\n", encoding="utf-8")
    (tmp_path / "local-only.md").write_text("# local\n", encoding="utf-8")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    assert sorted(_repo_files()) == ["docs/guide.md", "tracked.py"]


def test_repo_files_skips_tracked_files_deleted_from_the_worktree(tmp_path, monkeypatch):
    """추적 중이지만 지운 파일은 읽을 수 없다 — 목록에 넣으면 비밀 스캔이 죽는다."""
    import scripts.review_gate as gate

    _git(tmp_path, "init", "-q")
    (tmp_path / "gone.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "gone.py", "kept.py")
    (tmp_path / "gone.py").unlink()
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    assert _repo_files() == ["kept.py"]


def test_repo_files_falls_back_to_walking_without_git(tmp_path, monkeypatch):
    """git 을 쓸 수 없으면(소스 압축본 등) 작업 트리를 훑되 도구 디렉터리는 뺀다."""
    import scripts.review_gate as gate

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "a.pyc").write_bytes(b"")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gate.subprocess, "run", no_git)

    assert _repo_files() == ["a.py"]


# ------------------------------------------------------------------ secret scan


@pytest.mark.parametrize(
    "text",
    [
        'aws_key = "AKIAIOSFODNN7EXAMPLE"',  # gate-allow-secret
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n",  # gate-allow-secret
        'token = "ghp_' + "a" * 36 + '"',  # gate-allow-secret
        'slack = "xoxb-1234567890-abcdefghij"',  # gate-allow-secret
        'api_key = "' + "k" * 32 + '"',
    ],
    ids=["aws", "private-key", "github", "slack", "generic"],
)
def test_secret_like_values_are_detected(text):
    assert scan_secrets(text)


@pytest.mark.parametrize(
    "text",
    [
        'JWT_SECRET_KEY = "change-this-in-production-please-really"',
        'API_KEY: "your-api-key-here-goes-something-long"',
        "SECRET_KEY 는 배포 환경에서 반드시 교체한다.",
        'password = "short"',
    ],
    ids=["placeholder", "your-prefix", "prose", "too-short"],
)
def test_placeholders_and_prose_are_not_flagged(text):
    """오탐이 쌓이면 사람이 규칙을 끈다 — 꺼진 규칙은 없는 규칙이다."""
    assert scan_secrets(text) == []


# ------------------------------------------------------------------ 문서 참조


def test_missing_doc_path_is_detected():
    assert check_doc_paths("참고: `app/core/nope.py`", ["app/core/db/session.py"])


def test_doc_path_resolves_by_suffix_and_relative_prefix():
    """문서는 `db/session.py`·`../x.md` 처럼 앞을 생략해 쓴다 — 오탐을 만들면 안 된다."""
    known = ["app/core/db/session.py", "docs/ARCHITECTURE.md"]

    assert check_doc_paths("`db/session.py` `../docs/ARCHITECTURE.md`", known) == []


def test_bare_filename_is_not_checked():
    """슬래시 없는 파일명(`dependency.py`)은 위치가 아니라 이름 규칙을 가리킨다."""
    assert check_doc_paths("쓰지 말 것: `dependency.py`", ["app/x/dependencies.py"]) == []


def test_docs_gate_reads_readme_docs_and_workflows(tmp_path, monkeypatch):
    import scripts.review_gate as gate

    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("`app/core/gone.py`", encoding="utf-8")
    (tmp_path / "docs" / "GUIDE.md").write_text("`NOPE_FLAG=1`", encoding="utf-8")
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "_config_env_names", set)

    assert check_docs() == [
        "README.md: app/core/gone.py: 저장소에 없는 경로입니다",
        "docs/GUIDE.md: NOPE_FLAG: 설정에 없는 환경변수입니다",
    ]


def test_unknown_env_var_is_detected():
    assert check_doc_env_vars("설정: `NOPE_ENABLED=true`", {"DB_ROUTER_ENABLED"})


@pytest.mark.parametrize(
    "text",
    ["`WITH ... DELETE`", "`POST /api/v1/blog/posts`", "알고리즘은 `HS256` 이다"],
    ids=["sql", "http", "algorithm"],
)
def test_uppercase_tokens_are_not_mistaken_for_env_vars(text):
    assert check_doc_env_vars(text, set()) == []


def test_interpreter_env_vars_are_not_reported_as_missing():
    """`PYTHONIOENCODING` 은 앱 설정이 아니지만 문서가 정당하게 언급한다."""
    from scripts.review_gate import EXTERNAL_ENV

    assert check_doc_env_vars("`PYTHONIOENCODING=utf-8`", EXTERNAL_ENV) == []


# ------------------------------------------------------------------ pytest 판정


@pytest.mark.parametrize(
    "summary",
    ["540 passed, 3 skipped in 40s", "540 passed, 1 xfailed in 40s", "2 xpassed, 1 passed"],
    ids=["skipped", "xfailed", "xpassed"],
)
def test_silent_skips_are_rejected(summary):
    assert judge_pytest_summary(summary, allow_deselected=True)


def test_deselection_is_rejected_for_the_full_suite():
    """전체를 돌린다면서 일부를 골라내면 그 결과는 전체가 아니다."""
    summary = "547 passed, 28 deselected in 40s"

    assert judge_pytest_summary(summary, allow_deselected=False)
    assert judge_pytest_summary(summary, allow_deselected=True) == []


def test_clean_summary_passes():
    assert judge_pytest_summary("575 passed in 52.03s", allow_deselected=False) == []


# pytest 는 파이프로 캡처해도 요약에 색상 코드를 섞는다. 평문 요약만 넣고 시험하면
# 이 판정이 실제 게이트에서 **아무것도 못 잡는데도** 테스트는 초록이다 — 실제로
# 그 상태였다. 그래서 진짜 출력 모양(ANSI 포함)으로 시험한다.
_COLORED_SKIP = "\x1b[33m=========== \x1b[32m609 passed\x1b[0m, \x1b[33m\x1b[1m3 skipped\x1b[0m\x1b[33m in 36s\x1b[0m"
_COLORED_DESELECTED = "\x1b[32m788 passed\x1b[0m, \x1b[1m32 deselected\x1b[0m in 41s"
_COLORED_CLEAN = "\x1b[32m=========== \x1b[32m612 passed\x1b[0m\x1b[32m in 32s\x1b[0m"


def test_colored_summary_still_catches_skips():
    """색상 코드가 섞여도 잡아야 한다 — `\\b` 는 `[1m3` 에서 성립하지 않는다."""
    assert judge_pytest_summary(_COLORED_SKIP, allow_deselected=True)


def test_colored_deselection_follows_the_same_rule():
    assert judge_pytest_summary(_COLORED_DESELECTED, allow_deselected=False)
    assert judge_pytest_summary(_COLORED_DESELECTED, allow_deselected=True) == []


def test_colored_clean_summary_is_not_a_false_positive():
    """색상을 걷어내는 것이 반대로 오탐을 만들어서도 안 된다."""
    assert judge_pytest_summary(_COLORED_CLEAN, allow_deselected=False) == []
    assert judge_pytest_summary("\x1b[1m0 skipped\x1b[0m", allow_deselected=False) == []


def test_zero_counts_are_not_flagged():
    """`0 skipped` 는 문제가 아니다 — 숫자를 보지 않으면 여기서 오탐이 난다."""
    assert judge_pytest_summary("575 passed, 0 skipped", allow_deselected=False) == []


# ------------------------------------------------------------------ 빈 파일


def test_empty_modules_are_detected_but_package_markers_are_not(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "empty.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "full.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    paths = ["pkg/__init__.py", "pkg/empty.py", "pkg/full.py", "notes.md"]

    assert find_empty_python_files(paths, tmp_path) == ["pkg/empty.py"]


# ------------------------------------------------------------------ 게이트 자체


def test_gate_lists_its_groups(capsys):
    assert main(["--list"]) == 0
    assert "supply" in capsys.readouterr().out


def test_default_run_leaves_out_the_mysql_group(monkeypatch):
    """`mysql` 은 실제 MySQL 이 필요한 CI 전용 그룹 — 인자 없는 로컬 실행에 끼면 늘 실패한다."""
    import scripts.review_gate as gate

    ran: list[str] = []
    monkeypatch.setattr(gate, "run_group", lambda name: ran.append(name) or [])

    assert main([]) == 0
    assert "mysql" in gate.ALL_GROUPS
    assert "mysql" not in ran and "tests" in ran

    ran.clear()
    assert main(["--group", "mysql"]) == 0
    assert ran == ["mysql"]


def test_gate_reports_failure_with_nonzero_exit(monkeypatch, capsys):
    """실패 출력과 종료 코드 자체를 검사한다 — 조용히 0 을 돌려주면 게이트가 아니다."""
    import scripts.review_gate as gate

    monkeypatch.setitem(gate.ANALYSIS_GROUPS, "supply", lambda: ["일부러 만든 실패"])

    assert main(["--group", "supply"]) == 1
    output = capsys.readouterr().out
    assert "검증 게이트 실패" in output
    assert "일부러 만든 실패" in output


def test_gate_runs_as_a_module_with_utf8_output():
    """Windows/POSIX 모두에서 한글 출력이 게이트를 죽이지 않는다."""
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.review_gate", "--group", "supply", "docs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "검증 게이트 통과" in completed.stdout
