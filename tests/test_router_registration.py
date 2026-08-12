"""라우터 자동 등록 계약 (FR-02, FR-08, CR-02).

이전에는 "`main.py` 에서 `include_router` 한 줄을 빠뜨렸는가" 를 검사했다. 이제
등록은 `AppRegistry` 가 하므로 빠뜨릴 한 줄이 없다. 대신 계약이 바뀌었다 —
**발견된 앱이 라우터를 내보내면 `/api` 아래 반드시 마운트돼 있어야 한다.**

이 검사가 잡는 회귀:
    - 발견 목록에서 앱이 통째로 빠지는 경우(스캔 규칙 손상)
    - 라우터를 내보내는데 마운트되지 않는 경우(결선 손상)
    - 모델을 가진 앱이 `Base.metadata` 에 안 올라오는 경우(마이그레이션이 빈다)

전부 "에러 없이 기능만 사라지는" 종류라, 자동화의 대가로 반드시 있어야 하는 그물이다.
"""

import pathlib

import pytest

import app.features
from app.core.db.models_registry import import_all_models, iter_model_modules
from app.core.db.session import Base
from app.core.registry import AppRegistry

FEATURES_DIR = pathlib.Path(app.features.__path__[0])


def _discovered():
    return AppRegistry().discover()


def _mounted_paths() -> set[str]:
    from main import app

    return set(app.openapi()["paths"].keys())


def test_discovery_is_not_vacuous():
    """발견 목록이 비면 아래 검사가 전부 헛통과한다."""
    names = [m.name for m in _discovered()]
    assert len(names) >= 6, f"기능 앱이 발견되지 않았다: {names}"


@pytest.mark.parametrize("module", _discovered(), ids=lambda m: m.name)
def test_every_app_router_is_mounted(module):
    """라우터를 내보내는 앱은 예외 없이 `/api/v1/<name>/...` 에 마운트돼 있다.

    앱마다 개별 케이스로 돌린다 — 한 앱이 빠졌을 때 어느 앱인지 바로 보인다.
    """
    if module.load_router() is None:
        pytest.skip(f"'{module.name}' 은 라우터가 없는 앱이다 (선택 구성요소)")

    mounted = _mounted_paths()
    assert any(
        f"/{module.name}/" in path for path in mounted
    ), f"앱 '{module.name}' 의 라우터가 마운트되지 않았다. 마운트된 경로: {sorted(mounted)}"


def test_no_central_router_list_remains():
    """`main.py` 에 기능별 include_router 목록이 남아 있지 않다 (FR-08).

    한 줄이라도 남으면 "새 앱은 자동, 옛 앱은 수동" 인 반쪽 상태가 되고, 그
    상태는 문서와 실제가 어긋나는 가장 흔한 원인이다.
    """
    source = (FEATURES_DIR.parent.parent / "main.py").read_text(encoding="utf-8")

    for name in (m.name for m in _discovered()):
        assert (
            f"app.include_router({name}." not in source
        ), f"main.py 에 '{name}' 의 수동 include_router 가 남아 있다"


def test_every_model_is_in_metadata():
    """models/models.py 를 가진 앱은 빠짐없이 Base.metadata 에 등록돼야 한다."""
    import_all_models()

    with_models = {
        module.name
        for module in _discovered()
        if (FEATURES_DIR / module.name / "models" / "models.py").is_file()
    }
    registered = {dotted.split(".")[2] for dotted in iter_model_modules()}

    # 모델 없는 앱(auth 등)은 정상 제외 — "파일은 있는데 새는" 경우만 잡는다 (BC-06).
    missing = with_models - registered
    assert not missing, f"models.py 가 있는데 등록되지 않은 앱: {sorted(missing)}"
    assert Base.metadata.tables, "Base.metadata 가 비어 있다 — 마이그레이션이 빈 채로 생성된다"
