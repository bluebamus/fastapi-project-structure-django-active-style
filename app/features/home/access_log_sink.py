"""
Home-domain implementation of the AccessLogSink Protocol.

Persists access-log entries using the background session context
(background_db_session) so the write runs on the background connection pool and
does not interfere with the main API pool. (UnitOfWork was removed; the
transaction boundary is the background_db_session context manager.)
"""

from app.core.middlewares.access_log_sink import AccessLogSink, set_access_log_sink


class HomeAccessLogSink(AccessLogSink):
    """Saves access-log entries via the background session context."""

    # 세션·서비스는 호출 시점에 import 한다. 이 모듈은 registry 의 **발견** 단계에서
    # home/__init__.py 를 통해 끌려오는데, 모듈 레벨에서 가져오면 "앱이 있는지" 만
    # 알면 되는 경로까지 DB 엔진과 모델을 통째로 올린다
    # (경계: tests/core/test_import_boundary.py, 같은 패턴: registry.load_admin_views).
    async def save(self, data: dict) -> None:
        from app.core.db.session import background_db_session
        from app.features.home.services.user_access_log_service import UserAccessLogService

        async with background_db_session() as session:
            service = UserAccessLogService(session)
            await service.create_access_log(data)
            await session.commit()


def register_sink() -> None:
    """Register the Home access-log sink as the active middleware sink.

    Called from ``home/__init__.py`` (import-time) so that convention discovery
    of the home app also wires up access-log persistence.
    """
    set_access_log_sink(HomeAccessLogSink())
