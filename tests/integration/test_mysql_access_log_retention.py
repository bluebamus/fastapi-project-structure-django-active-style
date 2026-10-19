"""접속 로그 보존 정리를 실제 MySQL 8.4 에 대고 확인한다 (security-ops-hardening ADR-002).

MySQL 은 ``DELETE ... WHERE id IN (SELECT ... LIMIT n)`` 을 거부한다. 리포지토리는 id 를 먼저
고르고 지우는 두 단계라 MySQL 에서도 돈다 — 그 쿼리가 실제로 배치 경계·컷오프를 지키는지 본다.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.features.home.models.models import UserAccessLog
from app.features.home.services.access_log_retention_service import AccessLogRetentionService

pytestmark = pytest.mark.mysql

NOW = datetime(2026, 10, 19, 0, 0, tzinfo=UTC)


async def test_batched_purge_respects_cutoff_on_mysql(mysql_session_maker):
    cutoff = NOW - timedelta(days=365)
    async with mysql_session_maker() as session:
        for i in range(5):
            session.add(
                UserAccessLog(
                    ip_address="10.0.0.1",
                    request_path=f"/old{i}",
                    request_method="GET",
                    created_at=cutoff - timedelta(seconds=i + 1),
                )
            )
        session.add(
            UserAccessLog(
                ip_address="10.0.0.1", request_path="/edge", request_method="GET", created_at=cutoff
            )
        )
        await session.commit()

    async with mysql_session_maker() as session:
        service = AccessLogRetentionService(
            session, retention_days=365, clock=lambda: NOW, batch_size=2
        )
        deleted = await service.purge_expired()

    async with mysql_session_maker() as session:
        left = (await session.execute(select(UserAccessLog.request_path))).scalars().all()

    assert deleted == 5
    assert left == ["/edge"]
