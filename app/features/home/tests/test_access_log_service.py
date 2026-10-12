"""Home 접속 로그 서비스의 실제 DB 동작 검증 (UnitOfWork 제거 후 세션 기반).

in-memory sqlite 로 service → repository → ORM CRUD 흐름을 검증한다.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog  # noqa: F401  (register table)
from app.features.home.services.user_access_log_service import UserAccessLogService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_list(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {"ip_address": "1.2.3.4", "request_path": "/x", "request_method": "GET"}
    )
    await session.commit()

    logs, total = await service.get_access_logs()
    assert total == 1
    assert logs[0].ip_address == "1.2.3.4"
    assert logs[0].id  # repository auto-assigns UUID


@pytest.mark.asyncio
async def test_stats_counts_device_type(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {
            "ip_address": "1.1.1.1",
            "request_path": "/a",
            "request_method": "GET",
            "device_type": "desktop",
        }
    )
    await session.commit()

    stats = await service.get_stats()
    assert stats.total_count == 1
    assert any(d.device_type == "desktop" and d.count == 1 for d in stats.device_types)


@pytest.mark.asyncio
async def test_long_values_are_truncated_to_column_lengths(session):
    """컬럼보다 긴 헤더 값은 잘려서 저장된다 (F-007, ADR-005).

    SQLite 는 VARCHAR 길이를 강제하지 않으므로 저장된 값의 길이로 확인한다.
    상한은 모델 컬럼에서 읽는다 — 테스트도 숫자를 따로 적지 않는다.
    """
    columns = UserAccessLog.__table__.c
    data = {
        "ip_address": "1.2.3.4",
        "request_path": "/" + "p" * 5000,
        "request_method": "GET",
        "forwarded_for": "9" * 1000,
        "accept_language": "ko" * 500,
        "session_id": "s" * 500,
        "device_model": "m" * 500,
        "user_agent": "u" * 5000,  # Text — 자르지 않는다
    }
    service = UserAccessLogService(session)
    log = await service.create_access_log(data)
    await session.commit()

    for name in ("request_path", "forwarded_for", "accept_language", "session_id", "device_model"):
        assert len(getattr(log, name)) == columns[name].type.length, name
    assert len(log.user_agent) == 5000
    assert len(data["request_path"]) == 5001, "호출자 dict 를 바꾸지 않는다"
