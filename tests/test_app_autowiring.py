"""새 앱이 **중앙 파일 수정 없이** 결선되는지 통합 검증한다 (AC-01, AC-02, AC-03, AC-05).

이 프로젝트의 존재 이유가 이 한 가지다. 앱을 하나 만들면 라우터·테이블·관리 화면이
저절로 붙어야 하고, 그 대가로 `main.py` · `migrations/env.py` · `app/features/admin.py`
를 열 일이 없어야 한다.

검증 방법 — 실제 저장소에 앱을 만들지 않는다:
    `app.features` 패키지의 ``__path__`` 에 임시 디렉터리를 덧붙인다. 파이썬 패키지의
    ``__path__`` 는 그냥 리스트라, 여기에 경로를 더하면 `pkgutil.iter_modules` 와
    `import_module` 이 그 디렉터리도 똑같이 취급한다. 즉 registry 입장에서는 진짜
    앱과 구분되지 않으면서, 저장소에는 파일이 남지 않는다.

    부팅 대신 새 `FastAPI` 인스턴스에 결선한다 — `main.py` 가 하는 일과 같은
    호출(`discover` → `import_models` → `install_routers` → `install_admin`)이다.
    "중앙 파일을 안 고쳤다" 는 별도로 파일 해시를 대조해 확인한다.
"""

from __future__ import annotations

import hashlib
import importlib
import pathlib
import sys

import pytest
from fastapi import FastAPI

import app.features
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

# 새 앱을 추가할 때 절대 손대지 않아야 하는 파일들 (FR-08).
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
    """디렉터리를 만든 것만으로 앱 목록에 들어온다 (FR-01, CR-02, CR-06)."""
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

    # models_registry facade 도 같은 목록을 본다 (NFR-05).
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
    """앱을 지우면 결선도 함께 사라진다 (FR-08 의 반대 방향).

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
