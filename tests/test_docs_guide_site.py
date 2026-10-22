"""HTML 가이드 사이트(docs/guides)의 내용이 코드와 같은지 검사한다 (docs-guide-site 그룹).

링크 검사만으로는 표의 내용이 틀려도 초록이다 — API 표의 접근 수준과 설정 표의 누락이 그렇게
들어왔다. 여기서는 코드에서 뽑은 집합과 문서의 집합을 직접 대조한다.
"""

from html.parser import HTMLParser
from pathlib import Path

from pydantic_settings import BaseSettings

import config
from app.core.security.access import AccessPolicyGuard
from main import app

GUIDES = Path(__file__).resolve().parent.parent / "docs" / "guides"
MERMAID_VERSION = "11.12.0"


class _Page(HTMLParser):
    """표 행의 셀 텍스트·링크 href·스타일시트 href·모듈 스크립트 본문을 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.hrefs: list[str] = []
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []
        self.text: list[str] = []
        self._cell: list[str] | None = None
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "link" and a.get("rel") == "stylesheet":
            self.stylesheets.append(a["href"])
        elif tag == "script":
            self._in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None
        elif tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._in_script:
            self.scripts[-1] += data
        self.text.append(data)


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def _operations() -> set[tuple[str, str, str]]:
    """코드의 (메서드, 경로, 접근 수준) — OpenAPI operation × AccessPolicyGuard."""
    levels = AccessPolicyGuard().operations(app)
    expected = set()
    for path, item in app.openapi()["paths"].items():
        for method in item:
            (level,) = levels[(method.upper(), path)]
            expected.add((method.upper(), path, str(level)))
    return expected


def _api_rows(page: Path) -> set[tuple[str, str, str]]:
    rows = _parse(page).rows
    return {(r[0], r[1], r[2]) for r in rows if len(r) >= 3 and r[1].startswith("/")}


def test_api_table_matches_openapi_and_access_policy():
    expected = _operations()
    documented = _api_rows(GUIDES / "reference" / "api.html")
    assert (
        documented == expected
    ), f"문서에만: {sorted(documented - expected)}\n코드에만: {sorted(expected - documented)}"


def test_feature_api_tables_match_openapi_and_access_policy():
    """기능별 문서의 API 표는 전체의 부분집합이다 — 행마다 경로·접근 수준이 코드와 같아야 한다."""
    expected = _operations()
    checked = 0
    for page in sorted((GUIDES / "features").glob("*.html")):
        documented = _api_rows(page)
        checked += len(documented)
        wrong = sorted(documented - expected)
        assert not wrong, f"features/{page.name} 의 코드와 다른 행: {wrong}"
    assert checked, "기능별 문서에 API 표 행이 없습니다 — 검사가 무의미해집니다."


def test_configuration_page_names_every_setting():
    names = {
        field
        for obj in vars(config).values()
        if isinstance(obj, type) and issubclass(obj, BaseSettings) and obj is not BaseSettings
        for field in obj.model_fields
    }
    text = " ".join(_parse(GUIDES / "reference" / "configuration.html").text)
    missing = sorted(name for name in names if name not in text)
    assert not missing, f"configuration.html 에 없는 설정: {missing}"


def test_every_mermaid_page_pins_one_version():
    for page in sorted(GUIDES.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        if 'class="mermaid"' not in html:
            continue
        imports = [s for s in _parse(page).scripts if "mermaid" in s]
        assert imports, f"{page.name}: mermaid 블록이 있는데 로더가 없습니다."
        for script in imports:
            assert f"mermaid@{MERMAID_VERSION}/" in script, f"{page.name}: 고정 버전이 아닙니다."
            assert "mermaid@11/" not in script


def test_hub_links_every_guide_and_stylesheets_exist():
    hub = GUIDES / "index.html"
    linked = {(hub.parent / h).resolve() for h in _parse(hub).hrefs if not h.startswith("http")}
    for page in sorted(GUIDES.rglob("*.html")):
        if page != hub:
            assert (
                page.resolve() in linked
            ), f"허브가 {page.relative_to(GUIDES)} 를 링크하지 않습니다."
        for href in _parse(page).stylesheets:
            assert (page.parent / href).is_file(), f"{page.name}: 스타일시트 {href} 가 없습니다."
