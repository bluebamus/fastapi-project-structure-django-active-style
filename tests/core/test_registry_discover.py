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


def test_discover_does_not_run_package_import_hooks():
    """발견은 **부작용이 없다** — 앱이 무엇인지 알아내기만 한다 (ADR-006, C-5).

    이전 계약은 그 반대였다: discover 가 각 앱 패키지를 import 해
    `__init__.py` 의 import-time 부수효과를 실행했다. 그러면 "앱 목록만 알고
    싶은" 경로에서도 초기화가 일어나고, 테스트가 모듈을 건드리는 순서에 따라
    상태가 달라진다. Phase 1-R2 에서 초기화를 `install_hooks()` 로 분리했다.
    """
    from tests.core._fakeapps import INIT_CALLS

    before = list(INIT_CALLS)
    reg = AppRegistry()
    discovered = reg.discover(package=FAKE_PACKAGE)

    assert [a.name for a in discovered] == ["alpha", "beta"]
    assert INIT_CALLS == before, "discover() 가 초기화 훅을 실행했습니다."


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


# ---------------------------------------------------------------- Phase 1-R2
# INV-9 / ADR-006 — 발견은 순수하고, 초기화는 명시적이다.


def test_discover_has_no_side_effects():
    """`discover()` 만으로는 아무것도 초기화되지 않는다.

    이전에는 discover 가 각 앱 패키지를 import 해 `__init__.py` 의 부수효과를
    실행했다. 그러면 "앱이 무엇인지 알아보는" 것만으로 sink 가 등록되고, 테스트가
    모듈을 건드리는 순서에 따라 결과가 달라진다.
    """
    from app.core.middlewares import access_log_sink as sink_module

    sink_module.set_access_log_sink(None)
    AppRegistry().discover()

    assert sink_module.get_access_log_sink() is None, "discover() 가 sink 를 등록했습니다."


def test_install_hooks_registers_the_sink():
    """초기화는 명시적 호출로만 일어난다."""
    from app.core.middlewares import access_log_sink as sink_module

    sink_module.set_access_log_sink(None)
    registry = AppRegistry()
    registry.discover()

    installed = registry.install_hooks()

    assert installed >= 1
    assert sink_module.get_access_log_sink() is not None


def test_install_hooks_is_idempotent():
    """재기동·lifespan 재진입에서 다시 불려도 sink 는 하나다."""
    from app.core.middlewares import access_log_sink as sink_module

    registry = AppRegistry()
    registry.discover()

    registry.install_hooks()
    first = sink_module.get_access_log_sink()
    registry.install_hooks()
    second = sink_module.get_access_log_sink()

    assert type(first) is type(second)


def test_apps_without_hook_module_are_skipped():
    """`apps.py` 는 선택이다 — 없는 앱이 대부분이다."""
    registry = AppRegistry()
    apps = registry.discover()

    without_hook = [module for module in apps if module.name != "home"]
    assert without_hook, "훅 없는 앱이 하나도 없으면 이 테스트는 의미가 없다."
    assert all(module.install_hook() is False for module in without_hook)
