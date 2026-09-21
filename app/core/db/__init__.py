"""
Database 모듈

데이터베이스 연결과 세션 관리를 제공합니다.
요청 스코프 세션은 get_writer_db_session / get_read_only_db_session(DI), 요청 밖 작업은
background_db_session(컨텍스트)을 사용한다. get_routed_db_session 은 승인된 특수 경로
전용이라 기능 코드에서는 쓰지 않는다. 트랜잭션 경계는 요청에서는 쓰기 핸들러 본문이,
요청 밖에서는 컨텍스트를 연 호출자가 commit 으로 닫는다(UnitOfWork 없음).

읽기/쓰기 분리는 DatabaseRouter 가 담당한다(app/core/db/router.py).
.env 의 DB_ROUTER_ENABLED / DB_REPLICATION_ENABLED 로 활성화한다.
"""

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.db.session import (
    READINESS_TIMEOUT_SECONDS,
    AsyncSessionLocal,
    BackgroundSessionLocal,
    Base,
    background_db_session,
    background_engine,
    background_session,
    create_db_tables,
    db_router,
    dispose_engine,
    engine,
    get_background_db_session,
    get_background_session,
    get_read_only_db_session,
    get_read_session,
    get_routed_db_session,
    get_session,
    get_write_session,
    get_writer_db_session,
    ping_writer_db,
    read_engines,
    writer_engine,
)

__all__ = [
    "Base",
    "engine",
    "writer_engine",
    "read_engines",
    "background_engine",
    "db_router",
    "DatabaseRouter",
    "ReadOnlyRoutingError",
    "create_routing_sessionmaker",
    "using_writer",
    "mark_read_only",
    "AsyncSessionLocal",
    "BackgroundSessionLocal",
    "get_session",
    "get_read_session",
    "get_write_session",
    "get_background_session",
    "background_session",
    "background_db_session",
    "create_db_tables",
    "get_background_db_session",
    "get_read_only_db_session",
    "get_routed_db_session",
    "get_writer_db_session",
    "ping_writer_db",
    "READINESS_TIMEOUT_SECONDS",
    "dispose_engine",
]
