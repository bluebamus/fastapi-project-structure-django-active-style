"""`ADMIN=false` 면 sqladmin/admin 모듈을 아예 올리지 않는다 (계획서 §8).

lazy import 는 main.py 의 `if app_settings.ADMIN:` 안에서 이뤄진다. 이 계약이 깨지면
Admin 을 끈 배포에서도 sqladmin 과 전 도메인 ModelView 가 메모리에 상주한다.
같은 프로세스에서는 잴 수 없어 깨끗한 서브프로세스로 확인한다.
"""

import subprocess
import sys
import textwrap

CHILD = textwrap.dedent(
    """
    import sys

    import main

    loaded = sorted(
        name
        for name in sys.modules
        if name == "sqladmin" or name.startswith("sqladmin.") or name.endswith("features.admin")
    )
    print("LOADED:" + ",".join(loaded))
    """
)


def _run(admin_flag: str) -> list[str]:
    import os

    env = dict(os.environ, ADMIN=admin_flag)
    result = subprocess.run(
        [sys.executable, "-c", CHILD],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert result.returncode == 0, f"자식 프로세스 실패:\n{result.stdout}\n{result.stderr}"
    line = next(x for x in result.stdout.splitlines() if x.startswith("LOADED:"))
    return [name for name in line[len("LOADED:") :].split(",") if name]


def test_admin_false_does_not_import_sqladmin():
    assert _run("false") == [], "ADMIN=false 인데 sqladmin/admin 모듈이 import 됐습니다."


def test_admin_true_does_import_sqladmin():
    """대조군 — 켜면 실제로 올라온다(테스트가 항상 통과하는 착시 방지)."""
    assert _run("true"), "ADMIN=true 인데 sqladmin 이 import 되지 않았습니다."
