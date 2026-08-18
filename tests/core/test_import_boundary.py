"""발견 단계의 import 경계 (Phase 1, 계획서 §2 "패키지 init 경량화").

`discover()` 는 "어떤 앱이 있는가" 만 확정한다. 그런데 기능 `__init__.py` 가
라우터·모델을 eager import 하면 발견만 해도 DB 모듈과 라우팅 트리가 통째로
메모리에 올라온다. 그러면 discover / install_routers / import_models 의 분리가
이름만 남고, ADMIN=false 나 Alembic 처럼 일부만 필요한 경로도 전부를 끌어온다.

이 경계는 같은 프로세스에서는 잴 수 없다(다른 테스트가 이미 import 해버린다).
그래서 깨끗한 서브프로세스에서 측정한다.
"""

import subprocess
import sys
import textwrap

CHILD = textwrap.dedent(
    """
    import sys

    from app.core.registry import AppRegistry

    registry = AppRegistry()
    apps = registry.discover()

    assert apps, "앱을 하나도 발견하지 못했습니다."

    leaked = sorted(
        name
        for name in sys.modules
        if name.startswith("app.features.")
        and (".api.routers" in name or name.endswith(".models.models"))
    )
    print("LEAKED:" + ",".join(leaked))
    """
)

AFTER_IMPORT_MODELS = textwrap.dedent(
    """
    import sys

    from app.core.registry import AppRegistry

    registry = AppRegistry()
    registry.discover()
    registry.import_models()

    loaded = sorted(n for n in sys.modules if n.endswith(".models.models"))
    print("MODELS:" + ",".join(loaded))
    """
)


def _run(source: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"자식 프로세스 실패:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_discover_does_not_import_routers_or_models():
    """발견만으로 라우터·모델 모듈이 끌려오면 안 된다."""
    output = _run(CHILD)
    leaked_line = next(line for line in output.splitlines() if line.startswith("LEAKED:"))
    leaked = [name for name in leaked_line[len("LEAKED:") :].split(",") if name]

    assert leaked == [], (
        "discover() 만으로 다음 모듈이 import 됐습니다 — 기능 __init__.py 의 "
        f"eager import 를 제거하세요: {leaked}"
    )


def test_import_models_still_loads_every_model_module():
    """경량화가 모델 등록을 깨뜨리지 않는다 — import_models() 는 여전히 전부 올린다."""
    output = _run(AFTER_IMPORT_MODELS)
    models_line = next(line for line in output.splitlines() if line.startswith("MODELS:"))
    loaded = [name for name in models_line[len("MODELS:") :].split(",") if name]

    for expected in ("blog", "home", "reply", "sns", "user"):
        assert (
            f"app.features.{expected}.models.models" in loaded
        ), f"{expected} 모델이 등록되지 않았습니다."
