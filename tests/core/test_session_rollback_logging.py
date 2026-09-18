"""세션 롤백 로그가 SQL·바인딩 값을 흘리지 않는다 (C-4, ADR-004 연장).

DB 예외의 ``str()`` 에는 실행된 SQL 과 **바인딩된 값**이 그대로 들어간다
(SQLAlchemy 는 `[SQL: ...] [parameters: ...]` 를 붙인다). 롤백 로거의 이름은
``database`` 라 ``SQLNoiseFilter`` 의 NOISY_PREFIXES 에 걸리지 않고, 값이
키워드 형태가 아니라 ``RedactingFilter`` 도 지우지 못한다. 즉 예외 메시지를
기본 로그에 찍으면 두 방어선을 **모두 통과해** 파일 로그에 남는다.

기본 로그에는 예외 **타입**만 남기고, 전문은 DEBUG 레코드로만 내보낸다.
DEBUG 는 staging/production 에서 기동이 거부된다(config.validate_deployment_safety).
"""

import logging

import pytest

from app.core.db.session import get_background_db_session, get_routed_db_session

# 실제 DB 예외가 물고 오는 모양. SENTINEL 은 "바인딩된 값" 자리에 있다.
SENTINEL = "victim-binding-sentinel@example.com"
DB_ERROR_TEXT = (
    "(pymysql.err.OperationalError) (1213, 'Deadlock found')\n"
    "[SQL: SELECT users.email FROM users WHERE users.email = %(email_1)s]\n"
    f"[parameters: {{'email_1': '{SENTINEL}'}}]"
)


class _FakeDBError(Exception):
    """str() 에 SQL 과 바인딩 값을 싣는, SQLAlchemy 예외와 같은 모양."""


SESSION_FACTORIES = pytest.mark.parametrize(
    "factory", [get_routed_db_session, get_background_db_session], ids=["routed", "background"]
)


async def _rollback(factory):
    """제너레이터를 열고 DB 예외를 던져 롤백 경로를 태운다."""
    agen = factory()
    await agen.asend(None)
    with pytest.raises(_FakeDBError):
        await agen.athrow(_FakeDBError(DB_ERROR_TEXT))


@SESSION_FACTORIES
async def test_rollback_error_log_has_no_sql_or_bindings(caplog, factory):
    caplog.set_level(logging.DEBUG, logger="database")

    await _rollback(factory)

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "롤백 시 ERROR 레코드가 하나는 남아야 한다."
    for record in errors:
        message = record.getMessage()
        assert SENTINEL not in message, f"바인딩 값이 ERROR 로그에 노출됐다: {message}"
        assert "[SQL:" not in message, f"SQL 본문이 ERROR 로그에 노출됐다: {message}"
        assert "parameters:" not in message, f"파라미터가 ERROR 로그에 노출됐다: {message}"


@SESSION_FACTORIES
async def test_rollback_error_log_keeps_exception_type(caplog, factory):
    """진단은 가능해야 한다 — 타입과 소요시간은 남는다."""
    caplog.set_level(logging.DEBUG, logger="database")

    await _rollback(factory)

    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("_FakeDBError" in m and "ROLLBACK" in m for m in errors), errors


@SESSION_FACTORIES
async def test_debug_level_keeps_full_traceback(caplog, factory):
    """DEBUG=true 에서는 추적에 필요한 전문(SQL·바인딩 값·트레이스백)이 남는다."""
    caplog.set_level(logging.DEBUG, logger="database")

    await _rollback(factory)

    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
    assert debugs, "DEBUG 레벨에서는 exc_info 를 실은 상세 레코드가 있어야 한다."
    formatted = "\n".join(logging.Formatter().format(r) for r in debugs)
    assert SENTINEL in formatted, "DEBUG 상세에 바인딩 값이 있어야 추적이 된다."


@SESSION_FACTORIES
async def test_no_debug_record_above_debug_level(caplog, factory):
    """INFO 이상에서는 상세 레코드 자체가 만들어지지 않는다."""
    caplog.set_level(logging.INFO, logger="database")

    await _rollback(factory)

    assert not [r for r in caplog.records if r.levelno == logging.DEBUG]
