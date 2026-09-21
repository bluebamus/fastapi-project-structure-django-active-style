"""세션 롤백 로그가 SQL·바인딩 값을 흘리지 않는다 (C-4, ADR-004 연장).

DB 예외의 ``str()`` 에는 실행된 SQL 과 **바인딩된 값**이 그대로 들어간다
(SQLAlchemy 는 `[SQL: ...] [parameters: ...]` 를 붙인다). 롤백 로거의 이름은
``database`` 라 ``SQLNoiseFilter`` 의 NOISY_PREFIXES 에 걸리지 않고, 값이
키워드 형태가 아니라 ``RedactingFilter`` 도 지우지 못한다. 즉 예외 메시지를
기본 로그에 찍으면 두 방어선을 **모두 통과해** 파일 로그에 남는다.

기본 로그에는 예외 **타입**만 남기고, 전문은 DEBUG 레코드로만 내보낸다.
DEBUG 는 staging/production 에서 기동이 거부된다(config.validate_deployment_safety).
"""

import asyncio
import logging

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db import session as db_session_module
from app.core.db.session import (
    get_background_db_session,
    get_read_only_db_session,
    get_routed_db_session,
    get_writer_db_session,
)

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


# ------------------------------------------------ writer·read-only 세션의 정리
# 이 둘은 로깅 부수효과가 없어 명시적인 try/except rollback 을 두지 않는다.
# ``AsyncSession.__aexit__`` 가 ``close()`` 를 부르고, ``close()`` 는 활성 트랜잭션에
# ROLLBACK 을 이미 보낸다. 명시 rollback 을 덧붙여도 ROLLBACK 총 횟수는 같고,
# ``except Exception`` 은 ``asyncio.CancelledError``(BaseException 상속 — 클라이언트
# 연결 끊김)를 놓치는 반면 ``__aexit__`` 는 놓치지 않는다.
#
# 그래서 "무엇이 정리하는가" 가 아니라 **결과**를 고정한다: 예외 경로에서 엔진에
# ROLLBACK 이 정확히 한 번 나간다. 정리를 빠뜨리면 0회가 되어 이 테스트가 깨진다.


@pytest_asyncio.fixture
async def rollbacks(monkeypatch):
    """세션 팩토리를 in-memory SQLite 로 갈아끼우고 엔진 ROLLBACK 을 센다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    counted: list[str] = []
    event.listen(engine.sync_engine, "rollback", lambda connection: counted.append("rollback"))
    monkeypatch.setattr(
        db_session_module,
        "AsyncSessionLocal",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False),
    )

    yield counted

    await engine.dispose()


@pytest.mark.parametrize(
    "factory", [get_writer_db_session, get_read_only_db_session], ids=["writer", "read-only"]
)
@pytest.mark.parametrize(
    "error",
    [RuntimeError, asyncio.CancelledError],
    ids=["exception", "cancelled"],
)
async def test_request_session_rolls_back_once_on_the_error_path(rollbacks, factory, error):
    """예외로 끝난 요청의 세션은 ROLLBACK 한 번으로 정리된다 — 0회도 2회도 아니다.

    ``CancelledError`` 를 함께 보는 이유: 클라이언트가 응답 전에 끊으면 이 경로로
    들어오는데, ``except Exception`` 으로는 잡히지 않는다.
    """
    agen = factory()
    session = await agen.asend(None)
    # 실제로 커넥션을 잡아 트랜잭션을 연다. 열지 않으면 ROLLBACK 자체가 무의미하다.
    await session.execute(text("SELECT 1"))

    with pytest.raises(error):
        await agen.athrow(error("요청 처리 중 실패"))

    assert rollbacks == ["rollback"], f"ROLLBACK 이 {len(rollbacks)}회 나갔다."
