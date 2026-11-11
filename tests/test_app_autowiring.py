"""앱 자동 배선 — 실제 기능 앱과 생성기로 만든 앱이 라우터·모델·관리 화면에 결선되고, 지우면 사라진다."""

from __future__ import annotations

import hashlib
import importlib
import pathlib
import sys

import pytest
from fastapi import FastAPI

import app.features
from app.core.db.models_registry import import_all_models, iter_model_modules
from app.core.db.session import Base
from app.core.registry import AppRegistry
from scripts.new_app import scaffold

APP_NAME = "probeapp"
TABLE_NAME = "probe_widgets"

# 테스트마다 임시 앱을 새로 만들어 같은 모델 클래스를 다시 선언한다 — 여기서는
# 의도된 동작이다(각 테스트가 깨끗한 앱에서 시작해야 한다). SQLAlchemy 는 같은
# 이름의 선언 클래스가 다시 오면 경고하는데, 이 파일에 한해 무시한다.
# 운영 코드에서 같은 경고가 나면 그건 진짜 중복 선언이므로 무시하면 안 된다.
pytestmark = pytest.mark.filterwarnings("ignore:This declarative base already contains a class")

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 새 앱을 추가할 때 절대 손대지 않아야 하는 파일들.
CENTRAL_FILES = (
    "main.py",
    "migrations/env.py",
    "app/features/admin.py",
    "app/core/db/models_registry.py",
)

_ROUTE_SOURCE = f"""
@{APP_NAME}_router.get("/v1/{APP_NAME}/ping")
async def ping() -> dict[str, str]:
    return {{"pong": "{APP_NAME}"}}
"""

_MODELS_SOURCE = f'''"""임시 앱의 ORM 모델."""

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base


class ProbeWidget(Base):
    __tablename__ = "{TABLE_NAME}"

    id: Mapped[int] = mapped_column(primary_key=True)
'''

_MODELS_INIT_SOURCE = (
    f"from app.features.{APP_NAME}.models.models import ProbeWidget\n\n__all__ = ['ProbeWidget']\n"
)

_ADMIN_SOURCE = f'''"""임시 앱의 관리 화면."""

from sqladmin import ModelView

from app.features.{APP_NAME}.models.models import ProbeWidget


class ProbeWidgetAdmin(ModelView, model=ProbeWidget):
    name = "Probe Widget"


admin_views: list[type] = [ProbeWidgetAdmin]
'''


class _Recorder:
    def __init__(self) -> None:
        self.collected: list[type] = []

    def add_view(self, view: type) -> None:
        self.collected.append(view)


def _central_hashes() -> dict[str, str]:
    return {
        rel: hashlib.sha256((_REPO_ROOT / rel).read_bytes()).hexdigest() for rel in CENTRAL_FILES
    }


@pytest.fixture
def generated_app(tmp_path, monkeypatch):
    """임시 앱을 만들고 `app.features` 가 그것을 자기 하위로 인식하게 한다."""
    scaffold(APP_NAME, root=tmp_path, with_admin=True)

    base = tmp_path / "app" / "features" / APP_NAME
    router_py = base / "api" / "routers" / "router.py"
    router_py.write_text(router_py.read_text(encoding="utf-8") + _ROUTE_SOURCE, encoding="utf-8")
    (base / "models" / "models.py").write_text(_MODELS_SOURCE, encoding="utf-8")
    (base / "models" / "__init__.py").write_text(_MODELS_INIT_SOURCE, encoding="utf-8")
    (base / "admin.py").write_text(_ADMIN_SOURCE, encoding="utf-8")

    monkeypatch.setattr(
        app.features,
        "__path__",
        [*app.features.__path__, str(tmp_path / "app" / "features")],
    )

    yield base

    # 임시 앱이 다음 테스트로 새지 않게 걷어낸다.
    for name in [n for n in sys.modules if n.startswith(f"app.features.{APP_NAME}")]:
        sys.modules.pop(name, None)
    table = Base.metadata.tables.get(TABLE_NAME)
    if table is not None:
        Base.metadata.remove(table)


def test_generated_app_is_discovered(generated_app):
    """디렉터리를 만든 것만으로 앱 목록에 들어온다."""
    names = [m.name for m in AppRegistry().discover()]

    assert APP_NAME in names
    assert names == sorted(names), "새 앱이 들어와도 순서는 알파벳순을 유지해야 한다"


def test_generated_app_router_is_mounted(generated_app):
    """AC-01 — 중앙 파일 수정 없이 라우터가 OpenAPI 에 나타난다."""
    before = _central_hashes()

    registry = AppRegistry()
    registry.discover()
    api = FastAPI()
    registry.install_routers(api)

    assert f"/api/v1/{APP_NAME}/ping" in api.openapi()["paths"]
    assert _central_hashes() == before, "중앙 파일이 변경됐다 — 자동 등록이 아니다"


def test_generated_app_model_reaches_metadata(generated_app):
    """AC-02 — 임시 앱의 테이블이 런타임/Alembic 공용 metadata 에 한 번 나타난다."""
    assert TABLE_NAME not in Base.metadata.tables, "사전 조건: 아직 등록돼 있지 않아야 한다"

    registry = AppRegistry()
    registry.discover()
    registry.import_models()

    assert TABLE_NAME in Base.metadata.tables

    # Alembic 의 target_metadata 는 같은 Base.metadata 객체다 — 경로가 하나임을 고정한다.
    env_source = (_REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "AppRegistry" in env_source and "import_models()" in env_source

    # models_registry facade 도 같은 목록을 본다.
    from app.core.db.models_registry import iter_model_modules

    assert f"app.features.{APP_NAME}.models.models" in iter_model_modules()


def test_generated_app_admin_view_is_registered_once(generated_app):
    """AC-03 — 임시 앱의 ModelView 가 중앙 목록 수정 없이 정확히 한 번 등록된다."""
    registry = AppRegistry()
    registry.discover()
    registry.import_models()

    recorder = _Recorder()
    registry.install_admin(recorder)

    names = [v.__name__ for v in recorder.collected]
    assert names.count("ProbeWidgetAdmin") == 1, f"등록 결과: {names}"


def test_repeated_wiring_is_stable(generated_app):
    """AC-05 — 같은 앱 집합을 반복 결선해도 순서와 결과가 같다."""
    first, second = (AppRegistry(), AppRegistry())
    first.discover()
    second.discover()

    assert [m.name for m in first.enabled_apps] == [m.name for m in second.enabled_apps]

    api_a, api_b = FastAPI(), FastAPI()
    assert first.install_routers(api_a) == second.install_routers(api_b)
    assert sorted(api_a.openapi()["paths"]) == sorted(api_b.openapi()["paths"])

    rec_a, rec_b = _Recorder(), _Recorder()
    first.install_admin(rec_a)
    second.install_admin(rec_b)
    assert rec_a.collected == rec_b.collected


def test_removing_the_app_removes_its_wiring(tmp_path, monkeypatch):
    """앱을 지우면 결선도 함께 사라진다.

    추가만 자동이고 제거는 수동이면, 지운 앱의 라우트가 남아 500 을 낸다.
    """
    scaffold(APP_NAME, root=tmp_path)
    features_dir = tmp_path / "app" / "features"
    monkeypatch.setattr(app.features, "__path__", [*app.features.__path__, str(features_dir)])

    assert APP_NAME in [m.name for m in AppRegistry().discover()]

    # 디렉터리를 치우면(여기서는 __path__ 에서 제외) 발견 목록에서도 빠진다.
    monkeypatch.setattr(app.features, "__path__", list(app.features.__path__)[:-1])
    for name in [n for n in sys.modules if n.startswith(f"app.features.{APP_NAME}")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()

    assert APP_NAME not in [m.name for m in AppRegistry().discover()]


FEATURES_DIR = pathlib.Path(app.features.__path__[0])


def _discovered():
    return AppRegistry().discover()


def _mounted_paths() -> set[str]:
    from main import app

    return set(app.openapi()["paths"].keys())


# 라우터를 내보내는 앱만 파라미터로 쓴다. `pytest.skip` 을 쓰지 않는 이유는
# CI 게이트가 조용한 SKIP 을 실패로 취급하기 때문이다 — 라우터 없는 앱은 정상이므로
# 애초에 케이스를 만들지 않는다.
_APPS_WITH_ROUTER = [module for module in _discovered() if module.load_router() is not None]


def test_discovery_is_not_vacuous():
    """발견 목록이 비면 아래 검사가 전부 헛통과한다."""
    names = [m.name for m in _discovered()]
    assert len(names) >= 6, f"기능 앱이 발견되지 않았다: {names}"
    assert _APPS_WITH_ROUTER, "라우터를 내보내는 앱이 하나도 없다 — 마운트 검사가 무의미하다"


@pytest.mark.parametrize("module", _APPS_WITH_ROUTER, ids=lambda m: m.name)
def test_every_app_router_is_mounted(module):
    """라우터를 내보내는 앱은 예외 없이 `/api/v1/<name>/...` 에 마운트돼 있다.

    앱마다 개별 케이스로 돌린다 — 한 앱이 빠졌을 때 어느 앱인지 바로 보인다.
    """
    mounted = _mounted_paths()
    assert any(
        f"/{module.name}/" in path for path in mounted
    ), f"앱 '{module.name}' 의 라우터가 마운트되지 않았다. 마운트된 경로: {sorted(mounted)}"


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
