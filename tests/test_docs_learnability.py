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
from urllib.parse import unquote

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
GUIDE = REPO_ROOT / "docs" / "guides" / "DEVELOPMENT.md"
ARCHITECTURE = REPO_ROOT / "docs" / "guides" / "ARCHITECTURE.md"
HTML_GUIDES = (
    REPO_ROOT / "docs" / "guides" / "server-lifecycle-guide.html",
    REPO_ROOT / "docs" / "guides" / "feature-development-guide.html",
)
# 문서 목록은 README 의 이 절 한 곳에만 둔다(별도 docs/README.md 없음).
DOCS_INDEX_HEADING = "## 문서 안내"

# 마크다운 링크 `[..](target)` 의 target. 외부 URL·순수 앵커는 호출부에서 거른다.
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _docs_index() -> str:
    """README 의 문서 안내 절(다음 `## ` 제목 전까지)."""
    text = _read(README)
    start = text.index(DOCS_INDEX_HEADING)
    end = text.find("\n## ", start + len(DOCS_INDEX_HEADING))
    return text[start : end if end != -1 else len(text)]


def _broken_relative_links(doc: Path, text: str) -> tuple[int, list[str]]:
    """문서 기준 상대 링크를 풀어 실재하지 않는 것을 돌려준다(검사 수, 끊긴 목록)."""
    checked = 0
    missing = []
    for raw in LINK.findall(text):
        target = raw.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        checked += 1
        if not (doc.parent / target).resolve().exists():
            missing.append(f"{doc.relative_to(REPO_ROOT).as_posix()}: {raw}")
    return checked, missing


# ------------------------------------------------------------------ 진입점


def test_learner_entry_points_exist():
    for path in (README, GUIDE, ARCHITECTURE, *HTML_GUIDES):
        assert path.exists(), f"학습 진입점이 없습니다: {path.relative_to(REPO_ROOT)}"
    assert DOCS_INDEX_HEADING in _read(README), "README 에 문서 안내 절이 없습니다."


def test_readme_identifies_this_repository():
    """제목이 이 저장소를 식별하지 못하면 처음 보는 한 줄부터 틀린 것이다."""
    title = _read(README).splitlines()[0]

    assert "Django" in title and "Active" in title, f"저장소를 식별하지 못하는 제목: {title}"
    assert "Default" not in title, "제목에 이 저장소가 아닌 이름(Default)이 남아 있습니다."


def test_readme_reaches_the_orm_raw_guide():
    """README 에서 가이드까지 도달 경로가 있어야 한다 — 이게 끊겨 있었다."""
    text = _read(README)

    assert "docs/guides/DEVELOPMENT.md" in text, "README 가 워크플로 가이드를 가리키지 않습니다."


def test_docs_index_reaches_the_guide():
    index = _docs_index()
    assert "docs/guides/DEVELOPMENT.md" in index
    assert "docs/guides/ARCHITECTURE.md" in index
    for page in HTML_GUIDES:
        assert f"docs/guides/{page.name}" in index, f"문서 안내에 {page.name} 이 없습니다."


def test_html_guides_links_resolve():
    """HTML 안내서의 상대 href(파일·같은 문서 앵커)가 실재하는지 확인한다.

    HTML 은 마크다운 링크 검사에 걸리지 않고, 게이트도 `<code>` 경로만 본다. 안내서가
    옮겨진 문서(QUICKSTART 등)를 가리킨 채 남으면 아무도 모르므로 여기서 본다.
    """
    checked = 0
    missing: list[str] = []
    for page in HTML_GUIDES:
        text = _read(page)
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        for raw in re.findall(r'<a [^>]*href="([^"]+)"', text):
            if "://" in raw:
                continue
            target, _, anchor = raw.partition("#")
            checked += 1
            if target and not (page.parent / unquote(target)).resolve().exists():
                missing.append(f"{page.name}: {raw}")
            elif not target and anchor not in ids:
                missing.append(f"{page.name}: {raw}")

    assert checked, "HTML 안내서에 상대 링크가 없습니다."
    assert not missing, f"HTML 안내서의 끊긴 링크: {missing}"


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


def test_schema_management_policy_is_documented_in_both_places():
    """스키마 전환 정책은 README 와 호출 지점 **양쪽**에 있어야 한다.

    이 정책은 코드가 강제하지 않는다 — `DEBUG=true` 면 자동 생성은 그냥 돈다.
    지키게 만드는 것이 문서뿐이라, 문서가 사라지면 정책도 사라진다. 한쪽만
    검사하면 나머지 한쪽이 조용히 없어진다: README 만 있으면 코드를 읽는 사람이
    못 보고, 주석만 있으면 시작하는 사람이 못 본다.
    """
    readme = _read(REPO_ROOT / "README.md")
    resources_py = _read(REPO_ROOT / "app" / "core" / "resources.py")

    assert (
        "스키마 관리 — 자동 생성에서 Alembic 으로" in readme
    ), "README 의 스키마 전환 절이 사라졌습니다."
    for keyword in ("alembic upgrade head", "checkfirst", "DEBUG=false"):
        assert keyword in readme, f"README 의 전환 안내에 `{keyword}` 가 없습니다."

    ddl_call = resources_py.index("await create_db_tables()")
    block = resources_py[max(0, ddl_call - 2000) : ddl_call]
    assert (
        "스키마 관리 — 자동 생성에서 Alembic 으로" in block
    ), "resources.py 의 자동 생성 호출 지점이 더 이상 README 절을 가리키지 않습니다."
    assert (
        "checkfirst" in block
    ), "처음부터 Alembic 을 쓰는 경로(no-op 이 되는 이유)가 주석에서 사라졌습니다."


def test_all_docs_relative_links_resolve():
    """현행·기준선 문서의 상대 링크가 모두 실재하는 파일·폴더를 가리키는지 확인한다.

    예전에는 날짜가 박힌 버전 가이드의 `갱신` 블록 링크만 검사했다 — 그 블록이 학습자를
    현행 자료로 보내는 유일한 길이었기 때문이다. 버전 가이드를 현행 문서로 합친 뒤에는
    학습자가 따라가는 링크가 README·가이드·명세 전체에 있으므로 검사 범위를 그만큼
    넓힌다. `docs/crp/` 는 당시 경로를 그대로 기록하는 이력이라 제외한다.
    """
    docs = [README] + sorted(
        p for p in (REPO_ROOT / "docs").rglob("*.md") if "crp" not in p.relative_to(REPO_ROOT).parts
    )

    checked = 0
    missing: list[str] = []
    for doc in docs:
        count, broken = _broken_relative_links(doc, _read(doc))
        checked += count
        missing += broken

    assert checked, "상대 링크가 하나도 없습니다 — 검사가 무의미해집니다."
    assert not missing, f"끊긴 문서 링크: {missing}"


def test_docs_index_links_resolve():
    checked, missing = _broken_relative_links(README, _docs_index())

    assert checked, "문서 안내 절에 상대 링크가 없습니다."
    assert not missing, f"문서 안내의 끊긴 링크: {missing}"


# ------------------------------------------------------------------ 생성기


def test_generator_points_to_the_guide():
    """뼈대만 만들고 끝내면 다음에 무엇을 할지 알 수 없다."""
    source = _read(REPO_ROOT / "scripts/new_app.py")

    assert "docs/guides/DEVELOPMENT.md" in source
    assert "app/features/catalog/" in source and "app/features/reports/" in source


def test_project_metadata_matches_the_repository():
    """패키지 이름이 저장소 이름과 다르면 읽는 사람이 어디에 있는지 헷갈린다."""
    text = _read(REPO_ROOT / "pyproject.toml")

    assert 'name = "fastapi-project-structure-django-active-style"' in text
