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


def test_scaffold_does_not_teach_deprecated_session_names(tmp_path):
    """생성기 템플릿이 폐기된 Dependency 이름을 퍼뜨리지 않는다 (INV-10).

    scripts/ 는 `test_session_dependency_names.py` 의 AST 스캔 범위(app/·tests/) 밖이라
    여기서 따로 막는다 — 실제로 한 번 빠져나갔다.
    """
    scaffold("widget", tmp_path, with_admin=True)

    deps = (tmp_path / "app/features/widget/dependencies/widget_dependencies.py").read_text(
        encoding="utf-8"
    )

    for deprecated in ("get_session", "get_read_session", "get_write_session"):
        assert deprecated not in deps, f"템플릿이 deprecated alias '{deprecated}' 를 가르칩니다."
    assert "get_writer_db_session" in deps
    assert "get_read_only_db_session" in deps


def test_scaffold_does_not_teach_commit_in_dependency(tmp_path):
    """`yield` 뒤 commit 은 응답 전송 후에 실행돼 커밋 실패가 201 로 둔갑한다 (ADR-004)."""
    scaffold("widget", tmp_path, with_admin=True)

    deps = (tmp_path / "app/features/widget/dependencies/widget_dependencies.py").read_text(
        encoding="utf-8"
    )

    assert "yield service" not in deps, "템플릿이 yield dependency 패턴을 가르칩니다."
    assert "Dependency 는 조립만 한다" in deps


def test_cli_survives_a_console_that_cannot_encode_its_message(root, monkeypatch, capsys):
    """Windows 한국어 콘솔(cp949)에서 안내문 때문에 프로세스가 죽지 않는다.

    안내문에 em dash 가 있어 cp949 콘솔에서 `UnicodeEncodeError` 가 났다. 앱은 정상
    생성됐는데 종료 코드가 1 이라서 `python -m scripts.new_app x && <다음 단계>` 가
    조용히 끊겼다 — "성공했는데 실패로 보이는" 실패라 원인을 찾기 어렵다.
    """
    import io
    import sys

    from scripts.new_app import main

    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["new_app", "widget", "--with-admin"])
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="cp949"))

    main()

    assert (root / "app/features/widget/api/routers/router.py").exists()
