"""
Tests for Task 3.4: access-log middleware decoupling from home domain.

These tests verify that:
1. The middleware source contains no direct home-domain imports.
2. The sink registration roundtrip works correctly.
"""

import importlib
import importlib.util


def test_middleware_does_not_import_home():
    """Middleware source must not reference app.home or app.features.home."""
    src = importlib.util.find_spec("app.core.middlewares.user_info_middleware").origin
    text = open(src, encoding="utf-8").read()
    assert "app.home" not in text and "app.features.home" not in text


async def test_sink_registration_roundtrip():
    """set_access_log_sink / get_access_log_sink roundtrip works and delegates calls."""
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )

    original = get_access_log_sink()

    calls = []

    class StubSink:
        async def save(self, data: dict) -> None:
            calls.append(data)

    stub = StubSink()
    try:
        set_access_log_sink(stub)
        assert get_access_log_sink() is stub
        await get_access_log_sink().save({"x": 1})
        assert calls == [{"x": 1}]
    finally:
        set_access_log_sink(original)


async def test_sink_failure_log_has_no_sql_or_bindings(caplog):
    """저장 실패 로그가 SQL·바인딩 값을 흘리지 않는다 (C-4, ADR-008).

    sink 저장은 DB 쓰기다. 실패하면 예외 str() 에 SQL 과 바인딩된 값이 실려 오는데,
    이 로거 이름("user_info_middleware")은 SQLNoiseFilter 를 그대로 통과한다.
    기본 로그에는 예외 타입만 남기고 전문은 DEBUG 레코드로만 내보낸다.
    """
    import logging

    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.core.middlewares.user_info_middleware import UserInfoMiddleware

    sentinel = "victim-binding-sentinel@example.com"

    class Boom(Exception):
        pass

    class FailingSink:
        async def save(self, data: dict) -> None:
            raise Boom(
                "(pymysql.err.OperationalError) (1213, 'Deadlock found') "
                "[SQL: INSERT INTO user_access_log (email) VALUES (%(email)s)] "
                f"[parameters: {{'email': '{sentinel}'}}]"
            )

    original = get_access_log_sink()
    try:
        set_access_log_sink(FailingSink())
        with caplog.at_level(logging.DEBUG, logger="user_info_middleware"):
            middleware = UserInfoMiddleware.__new__(UserInfoMiddleware)
            await middleware._save_access_log({"email": sentinel})
    finally:
        set_access_log_sink(original)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "저장 실패 시 ERROR 레코드가 남아야 한다."
    for record in errors:
        message = record.getMessage()
        assert sentinel not in message, message
        assert "[SQL:" not in message, message
        assert record.exc_info is None, "ERROR 레코드의 트레이스백에도 SQL 이 실린다."
    assert any("Boom" in r.getMessage() for r in errors), "예외 타입은 남아야 진단이 된다."

    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
    assert debugs, "DEBUG 레벨에서는 전문이 남아야 한다."
    assert sentinel in " ".join(logging.Formatter().format(r) for r in debugs)
