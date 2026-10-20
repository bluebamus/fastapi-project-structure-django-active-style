"""Redis 연결 장애는 503 으로 끝난다 — 응답 뒤 예외를 다시 올리지 않는다 (integration-e2e F-004, 사용자 결정).

Redis 를 필수로 쓰는 API(로그인·가입 rate limit, refresh 저장소: login·refresh·logout, 사용자 비활성화·강등·삭제의
refresh·관리 세션 폐기)는 연결 오류를 그대로 올렸다. 전역 ``Exception`` 핸들러가 500 을 보낸 뒤 Starlette 가
예외를 다시 올려 uvicorn 이 traceback 을 한 번 더 남기고 연결을 끊었다(클라이언트는 응답 대신 연결 리셋).
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

import main


@pytest.mark.parametrize(
    "exc",
    [RedisConnectionError("Error 111 connecting to cache:6379. refused"), RedisTimeoutError("t")],
)
def test_redis_connection_errors_become_503_once(exc, caplog):
    app = FastAPI()
    main._register_exception_handlers(app)

    @app.post("/probe")
    async def probe():
        raise exc

    # raise_server_exceptions=True(기본) — 예외가 핸들러 밖으로 다시 올라오면 여기서 터진다.
    with caplog.at_level(logging.ERROR):
        response = TestClient(app).post("/probe")
    assert response.status_code == 503
    assert response.json() == {
        "error_code": "SERVICE_UNAVAILABLE",
        "message": "서비스가 일시적으로 사용 불가능합니다.",
        "detail": None,
    }
    assert "cache:6379" not in response.text
    assert sum(1 for r in caplog.records if r.exc_info) == 1
