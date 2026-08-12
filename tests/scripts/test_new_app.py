"""`scripts/new_app.py` 가 registry 규약을 만족하는 앱을 만드는지 고정한다 (FR-06).

Django `startapp` 대응물이다. 생성 결과가 규약에서 한 글자라도 어긋나면
(라우터 변수명, 디렉터리 이름) 자동 발견이 **조용히** 건너뛴다 — 그래서 생성
결과의 형태를 여기서 못 박는다.

안전성(이름 검증·경로 이탈·덮어쓰기)은 `test_new_app_safety.py` 가 담당한다.
"""

import pytest

from scripts.new_app import scaffold


@pytest.fixture
def root(tmp_path):
    """실제 저장소를 건드리지 않는 임시 프로젝트 루트."""
    (tmp_path / "app" / "features").mkdir(parents=True)
    return tmp_path


def test_creates_router_module_with_convention_name(root):
    """라우터 변수명은 `<앱이름>_router` 여야 registry 가 찾는다."""
    scaffold("widget", root=root)

    router_py = root / "app/features/widget/api/routers/router.py"
    assert router_py.exists()
    assert "widget_router = APIRouter()" in router_py.read_text(encoding="utf-8")


def test_creates_all_required_packages(root):
    """모든 하위 디렉터리에 `__init__.py` 가 있어야 import 가능한 패키지가 된다."""
    scaffold("widget", root=root)

    base = root / "app" / "features" / "widget"
    for rel in (
        "__init__.py",
        "models/__init__.py",
        "schemas/__init__.py",
        "services/__init__.py",
        "repositories/__init__.py",
        "tests/__init__.py",
        "api/__init__.py",
        "api/routers/__init__.py",
        "api/routers/v1/__init__.py",
        "dependencies/__init__.py",
        "dependencies/widget_dependencies.py",
    ):
        assert (base / rel).exists(), f"생성되지 않음: {rel}"


def test_does_not_create_central_declaration_file(root):
    """디렉터리 존재가 곧 등록 선언이다 — 앱별 config.py 를 만들지 않는다 (CR-06)."""
    scaffold("widget", root=root)

    assert not (root / "app/features/widget/config.py").exists()


def test_admin_is_optional_and_off_by_default(root):
    """`--with-admin` 없이는 admin.py 를 만들지 않는다 (선택 구성요소)."""
    scaffold("widget", root=root)

    assert not (root / "app/features/widget/admin.py").exists()


def test_with_admin_creates_admin_views_list(root):
    """`--with-admin` 은 `admin_views` 를 노출하는 admin.py 를 만든다.

    빈 목록으로 시작한다 — 그래야 모델을 아직 안 만든 상태에서도 registry 의
    계약 검사를 통과한다.
    """
    scaffold("widget", root=root, with_admin=True)

    admin_py = root / "app/features/widget/admin.py"
    assert admin_py.exists()
    assert "admin_views: list[type] = []" in admin_py.read_text(encoding="utf-8")


def test_app_without_models_is_valid(root):
    """모델 없는 앱도 정상이다 (실제 `auth` 가 그렇다 — BC-06).

    생성기는 `models/` 패키지만 만들고 모델 파일은 만들지 않는다.
    """
    scaffold("widget", root=root)

    models_dir = root / "app/features/widget/models"
    assert (models_dir / "__init__.py").exists()
    assert not (models_dir / "models.py").exists()


def test_multiword_name_becomes_pascal_case_class(root):
    """`user_profile` → `UserProfile` — 템플릿의 클래스 이름 예시에 쓰인다."""
    scaffold("user_profile", root=root, with_admin=True)

    admin_text = (root / "app/features/user_profile/admin.py").read_text(encoding="utf-8")
    assert "UserProfileAdmin" in admin_text

    router_text = (root / "app/features/user_profile/api/routers/router.py").read_text(
        encoding="utf-8"
    )
    assert "user_profile_router = APIRouter()" in router_text


def test_generated_router_module_is_importable_python(root):
    """생성물이 문법 오류면 발견 단계에서 기동이 깨진다 — 컴파일해서 확인한다."""
    import py_compile

    scaffold("widget", root=root, with_admin=True)

    base = root / "app" / "features" / "widget"
    for rel in ("api/routers/router.py", "dependencies/widget_dependencies.py", "admin.py"):
        py_compile.compile(str(base / rel), doraise=True)
