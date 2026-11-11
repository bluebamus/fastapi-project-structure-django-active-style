"""OpenAPI 공개 계약 — API 소비자(클라이언트 생성기 포함)가 기대는 성질을 규칙으로 검사한다.

operationId 의 존재·고유성, 성공·오류 응답 스키마, 태그 일치, ORM·Row 타입 비노출, 422 본문이
실제 응답(`ErrorResponse`)과 같은지 본다.
"""

import pytest

from app.core.tags_metadata import tags_metadata
from main import app

_METHODS = {"get", "post", "put", "patch", "delete"}


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


# ------------------------------------------------------------------ operation


def test_operation_ids_are_unique_and_present(operations):
    ids = [operation.get("operationId") for _, _, operation in operations]

    assert all(ids), "operationId 가 없는 operation 이 있습니다."
    duplicated = {value for value in ids if ids.count(value) > 1}
    assert not duplicated, f"operationId 중복: {sorted(duplicated)}"


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


# ------------------------------------------------------------------ schema


def test_no_orm_or_row_types_leak_into_schemas(spec):
    """내부 ORM 객체나 `RowMapping` 이 문서에 노출되지 않는다."""
    leaked = [
        name
        for name in spec["components"]["schemas"]
        if name in {"RowMapping", "Row", "CursorResult"} or name.endswith("Model")
    ]

    assert not leaked, f"내부 타입이 공개 schema 로 새어나왔습니다: {leaked}"


# ------------------------------------------------------------------ tag


def test_declared_and_used_tags_match_exactly(operations):
    """양방향 검사 — 한쪽만 보면 유령 태그가 쌓인다."""
    declared = {entry["name"] for entry in tags_metadata}
    used = {tag for _, _, operation in operations for tag in operation.get("tags", [])}

    assert used - declared == set(), f"metadata 에 없는 tag 를 씁니다: {sorted(used - declared)}"
    assert declared - used == set(), f"선언만 하고 쓰지 않는 tag: {sorted(declared - used)}"


# ------------------------------------------------------------------ 422 문서 = 실제 형식


def _actual_422_body() -> dict:
    """앱이 등록한 검증 오류 핸들러가 실제로 내는 본문."""
    import asyncio
    import json

    from fastapi.exceptions import RequestValidationError
    from starlette.requests import Request

    handler = app.exception_handlers[RequestValidationError]
    request = Request({"type": "http", "method": "POST", "path": "/x", "headers": []})
    error = RequestValidationError([{"loc": ("body", "name"), "msg": "필수", "type": "missing"}])
    response = asyncio.run(handler(request, error))
    assert response.status_code == 422
    return json.loads(response.body)


def test_every_422_documents_the_actual_error_body(spec, operations):
    """422 를 광고하는 모든 operation 은 실제 본문(ErrorResponse)을 광고한다 — FastAPI 기본
    ``HTTPValidationError``(loc·msg)가 아니다."""
    wrong = {
        _label(path, method): ref
        for path, method, operation in operations
        if "422" in operation.get("responses", {})
        and (
            ref := operation["responses"]["422"]["content"]["application/json"]["schema"].get(
                "$ref"
            )
        )
        != "#/components/schemas/ErrorResponse"
    }
    assert not wrong, f"422 가 실제 형식과 다르게 문서화됐습니다: {wrong}"
    assert "HTTPValidationError" not in spec["components"]["schemas"]

    documented = spec["components"]["schemas"]["ErrorResponse"]
    body = _actual_422_body()
    assert set(documented["required"]) <= set(body) <= set(documented["properties"]), body
    assert body["error_code"] == "VALIDATION_ERROR"
