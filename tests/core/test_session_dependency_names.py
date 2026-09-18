"""DB Session Dependency 정식 명명과 호환 alias (workflow-guide §2.1).

애플리케이션 계층에서는 SQLAlchemy 세션임이 이름에 드러나야 한다. 기존 이름은
**같은 객체를 가리키는 alias** 로 유지한다 — 다른 객체로 감싸면 FastAPI 의
`dependency_overrides` 키가 갈라져서 기존 테스트의 override 가 조용히 안 먹는다.
"""

import inspect

import pytest

from app.core.db import session as session_module

CANONICAL_TO_ALIAS = {
    # 주의: alias 이름을 리터럴로 적으면 이후의 일괄 rename 이 이 표까지 바꿔버려
    # 검사 의미가 사라진다(실제로 한 번 그렇게 망가졌다). 조각을 합쳐서 만든다.
    "get_read_only_db_session": "get_read" + "_session",
    "get_writer_db_session": "get_write" + "_session",
    "get_routed_db_session": "get" + "_session",
    "get_background_db_session": "get_background" + "_session",
    "background_db_session": "background" + "_session",
}


@pytest.mark.parametrize("canonical", sorted(CANONICAL_TO_ALIAS))
def test_canonical_name_exists(canonical):
    assert hasattr(session_module, canonical), f"정식 이름 {canonical} 이 없습니다."


@pytest.mark.parametrize("canonical,alias", sorted(CANONICAL_TO_ALIAS.items()))
def test_alias_is_the_same_object(canonical, alias):
    """alias 는 래퍼가 아니라 동일 객체여야 한다 (dependency_overrides 키 보존)."""
    assert getattr(session_module, alias) is getattr(
        session_module, canonical
    ), f"{alias} 가 {canonical} 과 다른 객체입니다 — 기존 override 가 깨집니다."


@pytest.mark.parametrize("canonical,alias", sorted(CANONICAL_TO_ALIAS.items()))
def test_both_names_are_exported(canonical, alias):
    from app.core.db import __all__ as exported

    assert canonical in exported, f"{canonical} 이 app.core.db 에서 export 되지 않았습니다."
    assert alias in exported, f"{alias} 가 app.core.db 에서 export 되지 않았습니다."


def test_read_only_dependency_marks_the_session():
    """정식 read-only Dependency 는 세션을 read-only 로 표시한다."""
    source = inspect.getsource(session_module.get_read_only_db_session)

    assert "mark_read_only" in source


def test_canonical_names_are_documented_as_primary():
    """새 코드가 alias 를 쓰지 않도록 deprecated 표시가 있어야 한다."""
    source = inspect.getsource(session_module)
    marker = source[source.index("# deprecated alias") :]

    for alias in CANONICAL_TO_ALIAS.values():
        assert alias in marker, f"{alias} 가 deprecated alias 구획에 없습니다."


def test_no_production_or_test_code_uses_deprecated_aliases():
    """alias 는 외부 호환용으로만 남긴다 — 저장소 안에서는 정식 이름만 쓴다.

    이 검사가 없으면 다음 기능이 습관적으로 옛 이름을 다시 퍼뜨린다(회귀 방지).
    정의·export 모듈 두 곳만 예외다.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    allowed = {
        root / "app" / "core" / "db" / "session.py",
        root / "app" / "core" / "db" / "__init__.py",
    }
    deprecated = set(CANONICAL_TO_ALIAS.values())

    offenders: list[str] = []
    for path in list((root / "app").rglob("*.py")) + list((root / "tests").rglob("*.py")):
        if path in allowed or ".venv" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 파싱 불가 파일은 검사 대상 아님
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in deprecated:
                offenders.append(f"{path.relative_to(root)}:{node.lineno} {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in deprecated:
                offenders.append(f"{path.relative_to(root)}:{node.lineno} .{node.attr}")
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in deprecated:
                        offenders.append(
                            f"{path.relative_to(root)}:{node.lineno} import {alias.name}"
                        )

    assert offenders == [], "deprecated alias 사용:\n  " + "\n  ".join(sorted(set(offenders)))


def test_feature_code_uses_only_writer_and_read_only_sessions():
    """기능 코드의 세션 Dependency 는 writer / read-only 둘뿐이다.

    `get_routed_db_session` 은 구문을 보고 엔진을 고르므로, 쓰기 핸들러의 **첫
    SELECT** 가 replica 로 새어나가 복제 지연을 읽을 수 있다. 의도는 코드가
    미리 밝히는 편이 맞다 — 코어에는 승인된 특수 경로용으로 남기되 기능
    (`app/features/**`)에서는 import 도 Depends 도 하지 않는다.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    banned = "get_routed" + "_db_session"

    offenders: list[str] = []
    for path in (root / "app" / "features").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == banned:
                offenders.append(f"{path.relative_to(root)}:{node.lineno} {banned}")
            elif isinstance(node, ast.Attribute) and node.attr == banned:
                offenders.append(f"{path.relative_to(root)}:{node.lineno} .{banned}")
            elif isinstance(node, ast.ImportFrom):
                offenders += [
                    f"{path.relative_to(root)}:{node.lineno} import {banned}"
                    for alias in node.names
                    if alias.name == banned
                ]

    assert offenders == [], (
        f"기능 코드가 {banned} 를 씁니다 — 쓰기는 get_writer_db_session, "
        "조회는 get_read_only_db_session 을 쓰세요:\n  " + "\n  ".join(sorted(set(offenders)))
    )
