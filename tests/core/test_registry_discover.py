"""앱 발견 규칙을 고정한다 — 목록·순서·제외·멱등성 (FR-01, FR-05, NFR-01, NFR-02).

발견이 틀리면 그 뒤의 결선은 전부 조용히 틀린다. 라우터가 안 붙고 테이블이
안 생겨도 서버는 에러 없이 뜨기 때문에, 여기서 막지 못하면 배포 후에야 드러난다.
"""

import pkgutil

from app.core.registry import FEATURES_PACKAGE, AppRegistry

FAKE_PACKAGE = "tests.core._fakeapps"


def test_discover_finds_direct_subpackages_alphabetically():
    """직계 하위 서브패키지를 알파벳순으로 발견하고, 언더스코어는 제외한다."""
    reg = AppRegistry()
    apps = reg.discover(package=FAKE_PACKAGE)

    assert [a.name for a in apps] == ["alpha", "beta"]
    assert reg.enabled_apps == apps
    assert all(a.package == f"{FAKE_PACKAGE}.{a.name}" for a in apps)


def test_discover_excludes_underscore_packages():
    """`_hidden` 은 존재하지만 발견되지 않는다 (NFR-02)."""
    present = {info.name for info in pkgutil.iter_modules([_fake_path()])}
    assert "_hidden" in present, "픽스처가 사라졌다 — 제외 규칙을 검사할 수 없다"

    names = [a.name for a in AppRegistry().discover(package=FAKE_PACKAGE)]
    assert "_hidden" not in names


def test_discover_sorts_regardless_of_filesystem_order(monkeypatch):
    """정렬은 우연이 아니라 명시적이어야 한다 (NFR-01).

    `pkgutil.iter_modules` 가 역순으로 돌려줘도 결과는 알파벳순이어야 한다.
    이 가드가 없으면 "마침 파일시스템이 정렬된 순서로 주더라" 에 기대게 되고,
    다른 OS 에서 라우트 등록 순서가 달라진다.
    """
    real_iter = pkgutil.iter_modules

    def reversed_iter(path=None, prefix=""):
        return reversed(list(real_iter(path, prefix)))

    monkeypatch.setattr(pkgutil, "iter_modules", reversed_iter)

    names = [a.name for a in AppRegistry().discover(package=FAKE_PACKAGE)]
    assert names == ["alpha", "beta"]


def test_discover_runs_init_hook_once_per_app():
    """초기화 훅은 결정적인 순서로, 앱마다 한 번만 실행된다 (FR-05, AC-05).

    파이썬이 `sys.modules` 로 import 를 캐시하므로 재발견해도 훅은 다시 돌지
    않는다. 이 성질에 기대는 계약이므로 회귀로 고정한다.
    """
    from tests.core._fakeapps import INIT_CALLS

    reg = AppRegistry()
    reg.discover(package=FAKE_PACKAGE)
    after_first = list(INIT_CALLS)

    assert sorted(after_first) == ["alpha", "beta"], "훅 실행 앱 집합이 발견 목록과 다르다"

    second = reg.discover(package=FAKE_PACKAGE)
    assert [a.name for a in second] == ["alpha", "beta"]
    assert INIT_CALLS == after_first, "재발견이 초기화 훅을 중복 실행했다"


def test_discover_real_features_is_deterministic():
    """실제 `app.features` 발견 결과도 알파벳순이고 언더스코어를 제외한다."""
    names = [m.name for m in AppRegistry().discover(package=FEATURES_PACKAGE)]

    assert names == sorted(names)
    assert not any(n.startswith("_") for n in names)
    # 기반 저장소의 여섯 기능이 모두 발견돼야 한다 (BC-01 의 전제).
    assert set(names) == {"auth", "blog", "catalog", "home", "reply", "reports", "sns", "user"}


def _fake_path() -> str:
    import tests.core._fakeapps as pkg

    return pkg.__path__[0]
