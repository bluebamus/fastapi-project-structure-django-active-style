"""검증 게이트 규칙의 **검출력**을 증명한다 (계획서 §10 Phase 9).

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
    check_action_pins,
    check_doc_deprecated_names,
    check_doc_env_vars,
    check_doc_paths,
    check_image_digests,
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


def test_repository_workflows_are_pinned():
    """규칙이 맞아도 배선이 틀리면 아무것도 검사하지 않는다."""
    workflows = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))

    assert workflows, ".github/workflows 에 검사할 파일이 없습니다."
    for workflow in workflows:
        assert check_action_pins(workflow.read_text(encoding="utf-8")) == []


# ------------------------------------------------------------------ 이미지 digest


@pytest.mark.parametrize(
    "image", ["mysql:8.4", "mysql:latest", "mysql"], ids=["minor-tag", "latest", "bare"]
)
def test_tag_pinned_images_are_rejected(image):
    assert check_image_digests(f"    image: {image}\n")


def test_digest_pinned_image_passes():
    digest = "sha256:" + "b" * 64

    assert check_image_digests(f"    image: mysql@{digest}  # 8.4\n") == []


def test_repository_compose_files_are_digest_pinned():
    composes = sorted(REPO_ROOT.glob("compose*.y*ml"))

    assert composes, "compose 파일이 없습니다."
    for compose in composes:
        assert check_image_digests(compose.read_text(encoding="utf-8")) == []


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
    known = ["app/core/db/session.py"]

    assert check_doc_paths("참고: `app/core/nope.py`", known, set())


def test_relative_doc_path_resolves_by_suffix():
    """문서는 `db/session.py` 처럼 앞을 생략해 쓴다 — 오탐을 만들면 안 된다."""
    known = ["app/core/db/session.py"]

    assert check_doc_paths("참고: `db/session.py`", known, set()) == []


def test_bare_filename_is_treated_as_naming_convention():
    """README 의 '쓰지 말 것' 반례(`dependency.py`)를 존재 검사로 고발하지 않는다."""
    assert check_doc_paths("쓰지 말 것: `dependency.py`", ["app/x/dependencies.py"], set()) == []


def test_forward_reference_can_be_declared():
    """이월된 결함이 예고하는 파일은 '빠뜨린 것' 과 구분한다."""
    allowed = {"app/core/resources.py"}

    assert check_doc_paths("예정: `app/core/resources.py`", [], allowed) == []


def test_unknown_env_var_is_detected():
    assert check_doc_env_vars("설정: `NOPE_ENABLED=true`", {"DB_ROUTER_ENABLED"}, set())


@pytest.mark.parametrize(
    "text",
    ["`WITH ... DELETE`", "`POST /api/v1/blog/posts`", "알고리즘은 `HS256` 이다"],
    ids=["sql", "http", "algorithm"],
)
def test_uppercase_tokens_are_not_mistaken_for_env_vars(text):
    assert check_doc_env_vars(text, set(), set()) == []


def test_interpreter_env_vars_are_not_reported_as_missing():
    """`PYTHONIOENCODING` 은 앱 설정이 아니지만 문서가 정당하게 언급한다."""
    from scripts.review_gate import EXTERNAL_ENV

    assert check_doc_env_vars("`PYTHONIOENCODING=utf-8`", EXTERNAL_ENV, set()) == []
    assert check_doc_env_vars("`PYTHONIOENCODING=utf-8`", set(), set()), "규칙이 죽었습니다."


# ------------------------------------------------------------------ 폐기 별칭


@pytest.mark.parametrize(
    "alias",
    ["get_session", "get_read_session", "get_write_session", "background_session"],
    ids=["routed", "read", "write", "background"],
)
def test_docs_teaching_deprecated_aliases_are_rejected(alias):
    """`get_session` 은 쓰기용이 아니라 **동적 라우팅**이다 — 따라 쓰면 쓰기가 샌다."""
    assert check_doc_deprecated_names(f"쓰기용 `{alias}` 을 주입합니다.")


def test_canonical_names_pass():
    text = "쓰기는 `get_writer_db_session`, 조회는 `get_read_only_db_session` 을 씁니다."

    assert check_doc_deprecated_names(text) == []


def test_canonical_name_containing_alias_is_not_flagged():
    """`get_background_db_session` 안에 `background_session` 이 들어 있지 않다 — 경계 확인."""
    assert check_doc_deprecated_names("`get_background_db_session`") == []


def test_readme_does_not_teach_deprecated_aliases():
    readme = REPO_ROOT / "README.md"

    assert readme.exists()
    assert check_doc_deprecated_names(readme.read_text(encoding="utf-8")) == []


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


def test_zero_counts_are_not_flagged():
    """`0 skipped` 는 문제가 아니다 — 숫자를 보지 않으면 여기서 오탐이 난다."""
    assert judge_pytest_summary("575 passed, 0 skipped", allow_deselected=False) == []


# ------------------------------------------------------------------ 게이트 자체


def test_gate_lists_its_groups(capsys):
    assert main(["--list"]) == 0
    assert "supply" in capsys.readouterr().out


def test_gate_reports_failure_with_nonzero_exit(monkeypatch, capsys):
    """실패 출력과 종료 코드 자체를 검사한다 — 조용히 0 을 돌려주면 게이트가 아니다."""
    import scripts.review_gate as gate

    monkeypatch.setitem(gate.ANALYSIS_GROUPS, "supply", lambda: ["일부러 만든 실패"])

    assert main(["--group", "supply"]) == 1
    output = capsys.readouterr().out
    assert "검증 게이트 실패" in output
    assert "일부러 만든 실패" in output


def test_gate_runs_as_a_module_with_utf8_output():
    """Windows/POSIX 모두에서 한글 출력이 게이트를 죽이지 않는다 (F-028)."""
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
