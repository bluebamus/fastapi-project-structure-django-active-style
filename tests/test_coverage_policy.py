"""커버리지 하한 정책 (log-redaction-fixes ADR-007 — 사용자 결정).

기본 하한은 0(측정·리포트만)이고, 정본은 pyproject 의 `[tool.coverage.report] fail_under`
하나다. CI·로컬 게이트 명령줄에 `--cov-fail-under` 를 두면 값이 두 곳으로 갈라지므로 금지하고,
CI 는 수치를 볼 수 있게 커버리지를 측정·출력한다.
"""

import tomllib
from pathlib import Path

from scripts.review_gate import COMMAND_GROUPS

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _ci_commands() -> str:
    """주석을 뺀 ci.yml — 주석은 이 정책을 설명하느라 옵션 이름을 적는다."""
    lines = CI.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_default_floor_is_zero_and_explicit():
    assert _pyproject()["tool"]["coverage"]["report"]["fail_under"] == 0


def test_floor_lives_only_in_pyproject():
    addopts = " ".join(_pyproject()["tool"]["pytest"]["ini_options"].get("addopts", []))
    gate = " ".join(" ".join(cmd) for cmds in COMMAND_GROUPS.values() for cmd in cmds)
    for name, text in (
        ("ci.yml", _ci_commands()),
        ("review_gate", gate),
        ("addopts", addopts),
    ):
        assert (
            "cov-fail-under" not in text
        ), f"{name} 가 하한을 따로 정합니다 — pyproject 하나가 정본입니다."


def test_ci_unit_tests_measure_coverage():
    step = next(
        line
        for line in CI.read_text(encoding="utf-8").splitlines()
        if 'pytest -m "not mysql"' in line
    )

    assert "--cov=app" in step and "--cov-report=term-missing" in step, step
    # 설정 파일을 명시하지 않으면 서브프로세스 테스트의 측정 데이터가 branch 없이 남아
    # pytest-cov 의 합치기가 INTERNALERROR 로 끝난다.
    assert "--cov-config=pyproject.toml" in step, step
    assert "skip-covered" not in step


def test_gate_tests_group_measures_coverage():
    pytest_runs = [
        cmd for cmd in COMMAND_GROUPS["tests"] if "pytest" in cmd and "--collect-only" not in cmd
    ]

    assert pytest_runs
    for cmd in pytest_runs:
        assert "--cov=app" in cmd and "--cov-config=pyproject.toml" in cmd, cmd
