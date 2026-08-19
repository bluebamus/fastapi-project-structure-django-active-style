"""전역 예외 핸들러는 raw 예외 본문을 응답에 담지 않는다 (계획서 §8, C-5).

DEBUG 에서만 노출한다 해도 개발 환경의 예외 메시지에는 DSN·쿼리·입력값이 그대로
실려 온다. 응답에는 안정적인 error code 만 남기고, 로그에는 raw path 대신 route
template 을 남긴다(경로에 박힌 식별자가 로그로 새지 않도록).
"""

import inspect

from fastapi.testclient import TestClient

import main

SENTINEL = "mysql+aiomysql://root:sup3rs3cret@db:3306/app"


def _client_with_exploding_route():
    @main.app.get("/_boom_{item_id}", include_in_schema=False)
    async def boom(item_id: str):
        raise RuntimeError(SENTINEL)

    return TestClient(main.app, raise_server_exceptions=False)


def test_unhandled_exception_response_hides_raw_detail(monkeypatch):
    monkeypatch.setattr(main.app_settings, "DEBUG", True)
    client = _client_with_exploding_route()

    response = client.get("/_boom_42")

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_SERVER_ERROR"
    assert body["detail"] is None, "raw 예외 본문이 응답에 실렸습니다."
    assert SENTINEL not in response.text
    assert "sup3rs3cret" not in response.text


def test_handler_logs_route_template_not_raw_path():
    """로그에는 /_boom_{item_id} 같은 template 을 남긴다."""
    source = inspect.getsource(main._register_exception_handlers)

    assert "route" in source, "예외 핸들러가 route template 을 쓰지 않습니다."


def test_debug_flag_no_longer_switches_detail_exposure():
    """DEBUG 여부로 노출을 가르던 분기가 사라졌는지 확인(회귀 방지)."""
    source = inspect.getsource(main._register_exception_handlers)

    assert "str(exc) if app_settings.DEBUG" not in source
