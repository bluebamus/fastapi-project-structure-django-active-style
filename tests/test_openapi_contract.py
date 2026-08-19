"""OpenAPI 공개 계약 검사 (DOC-001~005, Phase 9).

`test_route_inventory.py` 는 **어떤 경로가 있는가**를 골든으로 고정한다. 이 파일은
**그 경로들이 문서로서 성립하는가**를 규칙으로 검사한다. 둘은 역할이 다르다 —
골든은 새 경로를 막고, 규칙은 새 경로가 규격을 갖추도록 강제한다.

규칙 기반인 이유는 골든이 확장에 약하기 때문이다. 스냅샷만 두면 기능을 추가할 때마다
"스냅샷 갱신" 이 반사 행동이 되고, 그 순간 규격 위반도 함께 승인된다. 규칙은 새
엔드포인트에도 자동으로 적용된다.

검사 항목:

- DOC-001 모든 공개 operation 의 summary/description/고유 operation_id/tag/성공 응답
- DOC-002 파라미터 설명
- DOC-003 프로젝트 소유 schema 의 필드 description, 요청 DTO 의 examples,
  component key 에 모듈 경로형 `__` 금지
- DOC-004 tags_metadata 와 실제 tag 의 **양방향** 일치
- DOC-005 위 검사들의 자동화 자체

FastAPI 가 자체 생성하는 schema(`HTTPValidationError`, `ValidationError`,
`Body_*`)는 우리 소유가 아니므로 제외한다. 제외 목록은 접두사가 아니라 명시적
집합으로 둔다 — 접두사로 두면 우리 DTO 가 실수로 면제될 수 있다.
"""

import pytest

from app.core.tags_metadata import tags_metadata
from main import app

_METHODS = {"get", "post", "put", "patch", "delete"}

# FastAPI 가 생성하는 schema. 우리가 description 을 달 수 있는 대상이 아니다.
_GENERATED_SCHEMAS = {"HTTPValidationError", "ValidationError", "Body_authLogin"}


@pytest.fixture(scope="module")
def spec() -> dict:
    return app.openapi()


@pytest.fixture(scope="module")
def operations(spec) -> list[tuple[str, str, dict]]:
    return [
        (path, method, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in _METHODS
    ]


def _label(path: str, method: str) -> str:
    return f"{method.upper()} {path}"


# ------------------------------------------------------------------ DOC-001


def test_every_operation_has_summary_and_description(operations):
    missing = [
        _label(path, method)
        for path, method, operation in operations
        if not operation.get("summary") or not operation.get("description")
    ]

    assert not missing, f"summary/description 이 없는 operation: {missing}"


def test_operation_ids_are_unique_and_present(operations):
    ids = [operation.get("operationId") for _, _, operation in operations]

    assert all(ids), "operationId 가 없는 operation 이 있습니다."
    duplicated = {value for value in ids if ids.count(value) > 1}
    assert not duplicated, f"operationId 중복: {sorted(duplicated)}"


def test_operation_ids_are_not_module_qualified(operations):
    """FastAPI 기본 operationId 는 함수명+경로+메서드라 길고 리팩터링에 묶인다."""
    generated = [
        _label(path, method)
        for path, method, operation in operations
        if "__" in (operation.get("operationId") or "")
    ]

    assert not generated, f"명시적 operation_id 가 없는 operation: {generated}"


def test_every_operation_is_tagged(operations):
    untagged = [
        _label(path, method) for path, method, operation in operations if not operation.get("tags")
    ]

    assert not untagged, f"tag 가 없는 operation: {untagged}"


def test_success_responses_have_a_schema_except_204(operations):
    """204 는 body 가 없고, 나머지 성공 응답은 반드시 schema 를 가진다."""
    problems = []
    for path, method, operation in operations:
        for status, response in operation.get("responses", {}).items():
            if not status.startswith("2"):
                continue
            content = response.get("content")
            if status == "204":
                if content:
                    problems.append(f"{_label(path, method)} 204 에 body 가 있습니다")
                continue
            if not content or not any("schema" in media for media in content.values()):
                problems.append(f"{_label(path, method)} {status} 에 schema 가 없습니다")

    assert not problems, problems


def test_error_responses_are_documented(operations):
    """알려진 오류가 문서화된다 — 성공만 적힌 문서는 클라이언트가 분기할 수 없다.

    422 는 FastAPI 가 자동으로 넣으므로, 그것 말고 **직접 선언한** 오류가 하나라도
    있는지를 본다. 오류가 구조적으로 없는 목록/헬스 조회는 면제한다.
    """
    exempt = {"listPosts", "listReplies", "listSnsPosts", "listUsers", "listCatalogProducts"}
    problems = [
        _label(path, method)
        for path, method, operation in operations
        if operation["operationId"] not in exempt
        and not (set(operation.get("responses", {})) - {"200", "201", "204", "422"})
        and "{" in path
    ]

    assert not problems, f"경로 파라미터가 있는데 오류 응답이 문서화되지 않았습니다: {problems}"


# ------------------------------------------------------------------ DOC-002


def test_every_parameter_has_a_description(operations):
    missing = [
        f"{_label(path, method)} :: {parameter['name']}"
        for path, method, operation in operations
        for parameter in operation.get("parameters", [])
        if not (parameter.get("description") or parameter.get("schema", {}).get("description"))
    ]

    assert not missing, f"설명 없는 파라미터: {missing}"


# ------------------------------------------------------------------ DOC-003


def test_component_keys_are_not_module_qualified(spec):
    """`__` 이름은 공개 계약을 내부 디렉터리 구조에 묶는다 (F-004).

    FastAPI 는 같은 클래스명이 둘 이상이면 component key 에 모듈 경로를 합성한다.
    클라이언트 생성기가 그 key 를 타입명으로 쓰므로, 파일을 옮기는 것만으로
    클라이언트가 깨진다. 이름 충돌은 그때그때 고치는 게 아니라 여기서 막는다.
    """
    qualified = [name for name in spec["components"]["schemas"] if "__" in name]

    assert not qualified, (
        f"모듈 경로형 component key: {qualified}. "
        "클래스명이 전역에서 충돌합니다 — 도메인 의미가 드러나는 고유 이름으로 바꾸세요."
    )


def test_every_owned_schema_field_has_a_description(spec):
    missing = {}
    for name, schema in spec["components"]["schemas"].items():
        if name in _GENERATED_SCHEMAS:
            continue
        bad = [
            field
            for field, prop in (schema.get("properties") or {}).items()
            if not prop.get("description") and "$ref" not in prop and "allOf" not in prop
        ]
        if bad:
            missing[name] = bad

    assert not missing, f"description 없는 필드: {missing}"


def test_request_body_schemas_provide_examples(spec, operations):
    """요청 DTO 에는 예시가 있어야 한다 — 예시 없는 스키마는 호출법을 알려주지 않는다."""
    schemas = spec["components"]["schemas"]
    referenced = set()
    for _, _, operation in operations:
        for media in (operation.get("requestBody") or {}).get("content", {}).values():
            ref = media.get("schema", {}).get("$ref", "")
            if ref.startswith("#/components/schemas/"):
                referenced.add(ref.rsplit("/", 1)[-1])

    missing = [
        name
        for name in sorted(referenced - _GENERATED_SCHEMAS)
        if "examples" not in schemas[name] and "example" not in schemas[name]
    ]

    assert not missing, f"examples 가 없는 요청 DTO: {missing}"


def test_no_orm_or_row_types_leak_into_schemas(spec):
    """내부 ORM 객체나 `RowMapping` 이 문서에 노출되지 않는다 (VIEW-002)."""
    leaked = [
        name
        for name in spec["components"]["schemas"]
        if name in {"RowMapping", "Row", "CursorResult"} or name.endswith("Model")
    ]

    assert not leaked, f"내부 타입이 공개 schema 로 새어나왔습니다: {leaked}"


def test_example_schemas_exist_for_both_orm_and_raw(spec):
    """ORM/Raw 예제 DTO 가 모두 문서에 생성된다 (DOC-005)."""
    schemas = spec["components"]["schemas"]

    assert "ProductResponse" in schemas, "ORM 예제 DTO 가 없습니다."
    assert "DailySalesReportResponse" in schemas, "Raw 예제 DTO 가 없습니다."


# ------------------------------------------------------------------ DOC-004


def test_declared_and_used_tags_match_exactly(operations):
    """양방향 검사 — 한쪽만 보면 유령 태그가 쌓인다 (F-005)."""
    declared = {entry["name"] for entry in tags_metadata}
    used = {tag for _, _, operation in operations for tag in operation.get("tags", [])}

    assert used - declared == set(), f"metadata 에 없는 tag 를 씁니다: {sorted(used - declared)}"
    assert declared - used == set(), f"선언만 하고 쓰지 않는 tag: {sorted(declared - used)}"


def test_tag_descriptions_do_not_claim_unimplemented(operations):
    """구현이 끝난 기능을 '예정' 으로 설명하지 않는다."""
    used = {tag for _, _, operation in operations for tag in operation.get("tags", [])}
    stale = [
        entry["name"]
        for entry in tags_metadata
        if entry["name"] in used
        and any(word in entry["description"] for word in ("예정", "미구현"))
    ]

    assert not stale, f"구현됐는데 '예정/미구현' 으로 설명된 tag: {stale}"


def test_tag_metadata_entries_are_well_formed():
    for entry in tags_metadata:
        assert entry.get("name"), f"이름 없는 tag entry: {entry}"
        assert entry.get("description", "").strip(), f"설명 없는 tag: {entry['name']}"
