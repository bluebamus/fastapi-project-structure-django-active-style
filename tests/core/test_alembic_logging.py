"""Alembic 실행이 앱 로거를 죽이지 않는다 (C-5 부속, Phase 1).

`logging.config.fileConfig()` 는 기본값이 `disable_existing_loggers=True` 라,
migration 이 한 번 돌면 이미 만들어진 앱 로거들이 조용히 꺼진다. 그러면 그 이후의
보안 관련 로그(기동 거부·라우팅 구성 등)가 사라진다.
"""

import ast
import logging
from logging.config import fileConfig
from pathlib import Path

ENV_PY = Path(__file__).resolve().parents[2] / "migrations" / "env.py"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _fileconfig_calls(source: str) -> list[ast.Call]:
    tree = ast.parse(source)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) == "fileConfig"
    ]


def test_env_py_keeps_existing_loggers():
    """env.py 의 fileConfig 호출은 disable_existing_loggers=False 를 넘긴다."""
    calls = _fileconfig_calls(ENV_PY.read_text(encoding="utf-8"))
    assert calls, "env.py 에서 fileConfig 호출을 찾지 못했습니다."

    for call in calls:
        flags = {kw.arg: kw.value for kw in call.keywords}
        assert "disable_existing_loggers" in flags, (
            "fileConfig 가 disable_existing_loggers 를 명시하지 않습니다 — "
            "기본값 True 가 앱 로거를 꺼버립니다."
        )
        assert flags["disable_existing_loggers"].value is False


def test_fileconfig_with_flag_actually_preserves_logger():
    """플래그의 효과를 실제로 확인한다(회귀가 나면 여기서 잡힌다)."""
    probe = logging.getLogger("probe_alembic_survivor")
    probe.addHandler(logging.NullHandler())

    fileConfig(str(ALEMBIC_INI), disable_existing_loggers=False)

    assert probe.disabled is False, "fileConfig 후 기존 로거가 비활성화됐습니다."
