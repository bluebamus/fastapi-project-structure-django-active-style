"""스캐폴딩 생성기가 잘못된 이름·경로 이탈·덮어쓰기를 거부하는지 고정한다.

`scaffold()` 는 사용자가 준 이름을 그대로 경로에 붙이고 `exist_ok=True` 로
디렉터리를 만든 뒤 파일을 쓴다. 그래서 세 가지가 뚫려 있었다.

1. `../` 나 절대 경로를 주면 `app/features` **바깥**에 파일이 생긴다.
2. 하이픈·공백이 든 이름은 파이썬이 import 할 수 없는 패키지를 만든다 —
   자동 발견이 조용히 건너뛰어 "왜 안 보이지" 가 된다.
3. **이미 있는 앱 이름으로 다시 실행하면 작성해 둔 코드를 덮어쓴다.**
   같은 명령을 실수로 두 번 치면 그동안 짠 코드가 사라진다.

3번이 가장 위험하다 — 되돌릴 수 없다.
"""

import pytest

from scripts.new_app import scaffold


@pytest.fixture
def root(tmp_path):
    (tmp_path / "app" / "features").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# 정상 경로
# ---------------------------------------------------------------------------


def test_valid_name_creates_app(root):
    """정상 이름은 그대로 생성된다."""
    scaffold("orders", root=root)
    assert (root / "app" / "features" / "orders" / "__init__.py").exists()
    assert (root / "app" / "features" / "orders" / "api" / "routers" / "router.py").exists()


def test_snake_case_with_underscore_is_allowed(root):
    """언더스코어가 든 snake_case 는 유효한 파이썬 식별자라 허용한다."""
    scaffold("order_items", root=root)
    assert (root / "app" / "features" / "order_items" / "__init__.py").exists()


# ---------------------------------------------------------------------------
# 1·2. 이름 검증 — 경로 이탈과 import 불가 이름을 거부한다
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "../escape",  # 상위 디렉터리 이탈
        "../../etc",  # 더 멀리 이탈
        "a/b",  # 경로 구분자
        "a\\b",  # 윈도우 경로 구분자
        "/absolute",  # 절대 경로
        "with-hyphen",  # import 불가
        "with space",  # import 불가
        "9leading",  # 숫자로 시작 — 식별자 아님
        "",  # 빈 이름
        ".",  # 현재 디렉터리
        "class",  # 파이썬 예약어
    ],
)
def test_invalid_names_are_rejected(root, bad_name):
    """식별자가 아니거나 경로를 벗어나는 이름은 만들기 전에 거부한다."""
    with pytest.raises(ValueError):
        scaffold(bad_name, root=root)


def test_rejected_name_creates_nothing_outside(root):
    """거부된 이름이 features 바깥에 흔적을 남기지 않는다."""
    before = sorted(p.name for p in root.iterdir())
    with pytest.raises(ValueError):
        scaffold("../escape", root=root)
    assert sorted(p.name for p in root.iterdir()) == before
    assert not (root.parent / "escape").exists()


# ---------------------------------------------------------------------------
# 3. 덮어쓰기 방지 — 가장 위험한 항목
# ---------------------------------------------------------------------------


def test_existing_app_is_not_overwritten(root):
    """이미 있는 앱 이름으로 재실행하면 실패하고 기존 코드를 보존한다."""
    scaffold("orders", root=root)

    written = root / "app" / "features" / "orders" / "api" / "routers" / "router.py"
    written.write_text("# 사람이 작성한 코드\nMY_MARKER = 1\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        scaffold("orders", root=root)

    assert "MY_MARKER" in written.read_text(
        encoding="utf-8"
    ), "재실행이 기존 코드를 덮어썼다 — 되돌릴 수 없는 손실이다"


def test_force_allows_overwrite(root):
    """덮어쓰기가 정말 필요하면 명시적 force 로만 허용한다."""
    scaffold("orders", root=root)
    written = root / "app" / "features" / "orders" / "api" / "routers" / "router.py"
    written.write_text("# 덮어써질 것\n", encoding="utf-8")

    scaffold("orders", root=root, force=True)

    assert "orders_router" in written.read_text(encoding="utf-8")
