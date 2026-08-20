"""학습 경로가 실제로 이어지는지 검사한다 (docs-learnability 그룹).

이 저장소의 목적 중 하나는 **개발자가 규칙을 배울 수 있게 하는 것**이다. 그런데 학습
자료는 코드와 달리 깨져도 아무도 실패하지 않는다 — 링크가 끊기고 예제가 사라져도 테스트는
초록이고, 그 사실은 새로 온 사람이 헤맬 때에야 드러난다.

실제로 그런 상태였다. ORM/Raw 워크플로 지침서(1,200행)와 두 예제 기능이 모두 존재했는데
README·QUICKSTART·ARCHITECTURE 어디에서도 언급하지 않아 **도달할 수 없었다**. 자료가
없어서가 아니라 경로가 없어서 배울 수 없는 상태였다.

그래서 여기서는 문장의 품질이 아니라 **경로의 존재**를 검사한다: 진입점이 가이드를
가리키는가, 가이드가 가리키는 예제가 실재하는가, 예제가 여전히 그 방식으로 구현돼 있는가.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
DOCS_INDEX = REPO_ROOT / "docs" / "README.md"
GUIDE = REPO_ROOT / "docs" / "guides" / "orm-raw-workflow.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ 진입점


def test_learner_entry_points_exist():
    for path in (README, DOCS_INDEX, GUIDE):
        assert path.exists(), f"학습 진입점이 없습니다: {path.relative_to(REPO_ROOT)}"


def test_readme_identifies_this_repository():
    """제목이 다른 저장소 이름이면 처음 보는 한 줄부터 틀린 것이다."""
    title = _read(README).splitlines()[0]

    assert "Django" in title and "Active" in title, f"저장소를 식별하지 못하는 제목: {title}"
    assert "Default" not in title, "이전 기준선 저장소의 이름이 남아 있습니다."


def test_readme_reaches_the_orm_raw_guide():
    """README 에서 가이드까지 도달 경로가 있어야 한다 — 이게 끊겨 있었다."""
    text = _read(README)

    assert (
        "docs/guides/orm-raw-workflow.md" in text
    ), "README 가 워크플로 가이드를 가리키지 않습니다."


def test_docs_index_reaches_the_guide():
    assert "guides/orm-raw-workflow.md" in _read(DOCS_INDEX)


# ------------------------------------------------------------------ 선택 기준


def test_readme_teaches_the_orm_vs_raw_choice():
    """ "무엇을 언제 쓰나" 가 없으면 두 방식이 있다는 사실만 알고 고를 수 없다."""
    text = _read(README)

    assert "## ORM / Raw 데이터 접근" in text
    for keyword in ("BaseRepository", "RawRepositoryBase", "catalog", "reports"):
        assert keyword in text, f"README 에 '{keyword}' 가 없습니다."


def test_guide_states_orm_is_the_default():
    """기본값이 명시되지 않으면 Raw 가 '더 빠른 길' 로 오해된다."""
    text = _read(GUIDE)

    assert "기본값은 ORM" in text


@pytest.mark.parametrize(
    "rule",
    ["commit", "get_read_only_db_session", "get_writer_db_session", "named bind", "query_name"],
)
def test_guide_covers_the_core_rules(rule):
    assert rule in _read(GUIDE), f"가이드가 '{rule}' 규칙을 다루지 않습니다."


# ------------------------------------------------------------------ 예제 실재


@pytest.mark.parametrize(
    "path",
    [
        "app/features/catalog/repositories/product_repository.py",
        "app/features/reports/repositories/sales_report_repository.py",
        "tests/core/test_raw_sql_static_guard.py",
        "tests/integration/test_sales_report_mysql.py",
        "compose.test.yaml",
    ],
)
def test_referenced_examples_exist(path):
    """가이드가 가리키는 파일이 사라지면 학습 경로가 끊긴다."""
    assert (REPO_ROOT / path).exists(), f"가이드가 참조하는 경로가 없습니다: {path}"


def test_examples_still_use_the_advertised_bases():
    """예제가 다른 방식으로 바뀌면 가이드는 조용히 거짓말이 된다."""
    orm = _read(REPO_ROOT / "app/features/catalog/repositories/product_repository.py")
    raw = _read(REPO_ROOT / "app/features/reports/repositories/sales_report_repository.py")

    assert "BaseRepository" in orm, "ORM 예제가 더 이상 BaseRepository 를 쓰지 않습니다."
    assert "RawRepositoryBase" in raw, "Raw 예제가 더 이상 RawRepositoryBase 를 쓰지 않습니다."


def test_guide_internal_links_resolve():
    """가이드의 상대 링크가 실제 파일을 가리키는지 확인한다."""
    text = _read(GUIDE)
    targets = re.findall(r"\]\((\.\.?/[^)#]+)\)", text)

    assert targets, "가이드에 상대 링크가 없습니다 — 검사가 무의미해집니다."
    missing = [t for t in targets if not (GUIDE.parent / t).resolve().exists()]
    assert not missing, f"가이드의 끊긴 링크: {missing}"


def test_project_guide_update_notes_link_to_live_docs():
    """버전이 박힌 가이드의 `갱신` 블록이 가리키는 문서가 실재하는지 확인한다.

    v1.0.0 문서는 시대를 기록한 것이라 원문을 남기고 갱신 블록을 덧붙인다. 그
    블록만이 학습자를 현행 자료로 보내므로, 여기 링크가 끊기면 정정 자체가
    사라진 것과 같다 — 그런데 원문은 그대로 남아 계속 틀린 것을 가르친다.
    """
    guides = sorted((REPO_ROOT / "docs/project-guide").rglob("*.md"))
    assert guides, "project-guide 문서가 없습니다 — 검사가 무의미해집니다."

    checked = 0
    missing = []
    for doc in guides:
        for line in _read(doc).splitlines():
            if "갱신(" not in line:
                continue
            for target in re.findall(r"\]\((\.\.?/[^)#]+)\)", line):
                checked += 1
                if not (doc.parent / target).resolve().exists():
                    missing.append(f"{doc.name}: {target}")

    assert checked, "갱신 블록에 상대 링크가 없습니다 — 검사가 무의미해집니다."
    assert not missing, f"갱신 블록의 끊긴 링크: {missing}"


def test_docs_index_links_resolve():
    text = _read(DOCS_INDEX)
    targets = re.findall(r"\]\((\.\.?/[^)#]+|[A-Za-z][^)#:]*\.md|[a-z-]+/)\)", text)

    assert targets
    missing = [t for t in targets if not (DOCS_INDEX.parent / t).resolve().exists()]
    assert not missing, f"docs 안내의 끊긴 링크: {missing}"


# ------------------------------------------------------------------ 생성기


def test_generator_points_to_the_guide():
    """뼈대만 만들고 끝내면 다음에 무엇을 할지 알 수 없다."""
    source = _read(REPO_ROOT / "scripts/new_app.py")

    assert "docs/guides/orm-raw-workflow.md" in source
    assert "app/features/catalog/" in source and "app/features/reports/" in source


def test_project_metadata_matches_the_repository():
    """패키지 이름이 다른 저장소면 읽는 사람이 어디에 있는지 헷갈린다."""
    text = _read(REPO_ROOT / "pyproject.toml")

    assert 'name = "fastapi-project-structure-django-active-style"' in text
