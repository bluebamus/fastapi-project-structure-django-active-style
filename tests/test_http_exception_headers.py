"""HTTP 예외가 실어 온 헤더는 응답에 그대로 실린다 (log-redaction-fixes ADR-004).

전역 `StarletteHTTPException` 핸들러가 본문을 프로젝트 형식(`ErrorResponse`)으로 바꾸면서
`exc.headers` 를 버리면 405 의 `Allow`(RFC 9110 §15.5.6 필수), 401 의 `WWW-Authenticate`
같은 HTTP 계약이 깨진다. 본문 형식은 그대로 두고 헤더만 넘기는지 본다.
"""

from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

import main

BODY_KEYS = {"error_code", "message", "detail"}


def test_405_carries_allow_with_the_route_methods():
    client = TestClient(main.app)

    response = client.delete("/health")

    assert response.status_code == 405
    route = next(r for r in main.app.routes if isinstance(r, APIRoute) and r.path == "/health")
    allowed = {m.strip() for m in response.headers["allow"].split(",")}
    assert allowed == route.methods
    body = response.json()
    assert set(body) == BODY_KEYS
    assert body["error_code"] == "HTTP_405"
    assert body["detail"] is None


def _app_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    main._register_exception_handlers(app)

    @app.get("/probe")
    async def probe():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_fastapi_http_exception_headers_reach_the_response():
    client = _app_raising(
        HTTPException(
            status_code=401, detail="no", headers={"WWW-Authenticate": "Bearer", "X-Probe": "1"}
        )
    )

    response = client.get("/probe")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["x-probe"] == "1"
    assert response.json() == {"error_code": "HTTP_401", "message": "no", "detail": None}


def test_starlette_http_exception_headers_reach_the_response():
    client = _app_raising(StarletteHTTPException(status_code=429, headers={"Retry-After": "7"}))

    response = client.get("/probe")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert set(response.json()) == BODY_KEYS


def test_http_exception_without_headers_still_works():
    client = _app_raising(HTTPException(status_code=418, detail="teapot"))

    response = client.get("/probe")

    assert response.status_code == 418
    assert response.json() == {"error_code": "HTTP_418", "message": "teapot", "detail": None}


def test_api_401_carries_www_authenticate_bearer():
    """앱 고유 401(UnauthorizedException 계열)도 RFC 9110 §15.5.2 의 `WWW-Authenticate` 를 싣는다.

    토큰이 없거나 위조면 `get_current_principal` 이 UnauthorizedException 을 올린다(auto_error=False).
    그 예외가 헤더 없이 나가 401 이 계약을 어기고 있었다 — integration-e2e F-002.
    """
    client = TestClient(main.app)
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert set(response.json()) == BODY_KEYS
