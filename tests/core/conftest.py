"""registry 계약 테스트용 공용 픽스처."""

import sys

import pytest


@pytest.fixture
def fake_app(tmp_path, monkeypatch):
    """디스크에 진짜 패키지를 만들어 실제 import 기계를 통과시킨다.

    `sys.modules` 에 미리 심는 방식으로는 `importlib.import_module` 의 실제 탐색
    경로를 타지 않아, "모듈이 없다" 와 "모듈 안의 import 가 틀렸다" 를 구분하는
    동작 자체를 비켜간다. 그 구분이 검사 대상이므로 파일을 실제로 만든다.

    Usage:
        fake_app("probe_pkg", "__package__")            # 빈 패키지
        fake_app("probe_pkg.admin", "import nope_xyz")  # 내용 있는 모듈
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    created: list[str] = []

    def make(dotted: str, source: str = "") -> None:
        parts = dotted.split(".")
        directory = tmp_path.joinpath(*parts[:-1]) if len(parts) > 1 else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        for depth in range(1, len(parts)):
            pkg_init = tmp_path.joinpath(*parts[:depth], "__init__.py")
            pkg_init.parent.mkdir(parents=True, exist_ok=True)
            pkg_init.touch()
        if source == "__package__":
            target = tmp_path.joinpath(*parts, "__init__.py")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        else:
            (directory / f"{parts[-1]}.py").write_text(source, encoding="utf-8")
        created.append(dotted)

    yield make

    # 테스트가 만든 모듈이 다음 테스트로 새지 않게 걷어낸다.
    for dotted in created:
        root = dotted.split(".")[0]
        for name in list(sys.modules):
            if name == root or name.startswith(f"{root}."):
                sys.modules.pop(name, None)
