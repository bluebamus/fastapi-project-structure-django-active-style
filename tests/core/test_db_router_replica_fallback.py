"""replica 연결 오류 → 그 읽기를 primary 로 한 번 다시 실행한다 (integration-e2e F-005, 사용자 결정 c).

읽기 전용 세션(get_read_only_db_session)만, 연결 계열 오류(접속 불가·연결 끊김·타임아웃)만 대상이다. 쓰기 세션·
문법 오류·라우터 없는 구성은 그대로 실패한다. 재시도에는 WARNING 이 한 줄 남는다.
"""

from __future__ import annotations

import logging

import pymysql
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db.router import DatabaseRouter, create_routing_sessionmaker, mark_read_only


def _replica_raising(error: Exception):
    async def connect():
        raise error

    return create_async_engine("mysql+aiomysql://replica/db", async_creator=connect)


@pytest.fixture
def writer():
    engine = create_async_engine("sqlite+aiosqlite://")
    yield engine


async def _read(writer, replica, *, read_only: bool = True):
    maker = create_routing_sessionmaker(DatabaseRouter(writer, [replica]))
    async with maker() as session:
        if read_only:
            mark_read_only(session)
        return (await session.execute(text("SELECT 42"))).scalar_one()


async def test_read_only_session_retries_on_primary_after_a_replica_connection_error(
    writer, caplog
):
    replica = _replica_raising(pymysql.err.OperationalError(2003, "Can't connect to MySQL server"))
    with caplog.at_level(logging.WARNING):
        assert await _read(writer, replica) == 42
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "replica" in warnings[0].getMessage()


async def test_other_errors_are_not_retried(writer):
    replica = _replica_raising(pymysql.err.ProgrammingError(1064, "syntax"))
    with pytest.raises(ProgrammingError):
        await _read(writer, replica)


async def test_writer_sessions_are_not_retried(writer):
    replica = _replica_raising(pymysql.err.OperationalError(2003, "Can't connect"))
    with pytest.raises(OperationalError):
        await _read(writer, replica, read_only=False)
