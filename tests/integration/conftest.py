"""MySQL 8.4 통합 테스트 하네스 (계획서 §9, Phase 5).

SQLite 단위 테스트는 Base 계약과 Service 규칙을 빠르게 검증하지만, **MySQL 방언
승인의 근거가 되지 못한다**. 실제 SQL·migration 은 여기서 MySQL 에 대고 확인한다.

MySQL 이 없으면 **조용히 통과시키지 않고 skip 한다** — skip 사유가 출력에 남아야
"돌았는데 통과"와 "안 돌았다"를 구분할 수 있다. CI 는 skip 을 실패로 취급한다
(C-4: MySQL 이 없어서 전부 skip 된 초록은 실패다).

    docker compose -f compose.test.yaml up -d --wait
    pytest -m mysql
    docker compose -f compose.test.yaml down -v

이 저장소는 모델 metadata 를 `AppRegistry` 자동 발견에서 얻는다(INV-5). 그래서
여기서도 `AppRegistry().discover()` + `import_models()` 로 채운다 —
`migrations/env.py` 와 **같은 경로**여야 runtime/migration 의 모델 집합이 갈리지 않는다.
"""

from __future__ import annotations

import os
import socket

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# compose.test.yaml 과 같은 값. 3306(개발 머신의 상시 MySQL)·3307(IDE 포트 포워딩)·
# 3308(sibling: fastapi-default-project-structure)·3309(sibling: -passive-style)를
# 모두 피해 3310 이다.
#
# **DB·계정 이름도 이 저장소 전용이다.** 포트만 나누면 실수로 겹쳤을 때 남의
# 컨테이너에 조용히 붙어 스키마를 지운다. 계정이 다르면 그 경우 접속이 거부되어
# 실패가 눈에 보인다 — 격리는 포트가 아니라 자격증명으로 보장한다.
#
# root 가 아니라 전용 계정을 쓴다. 공식 이미지의 root 는 컨테이너 내부(localhost)
# 기준으로만 열려 있어 호스트에서 붙으면 거부되고, 애초에 테스트가 전 서버 권한을
# 가질 이유도 없다. MYSQL_USER 는 MYSQL_DATABASE 에 대한 전권을 받으므로
# DDL(migration)도 문제없다.
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = int(os.getenv("MYSQL_TEST_PORT", "3310"))
MYSQL_USER = "fastapi_active_test"
MYSQL_PASSWORD = "fastapi_active_test_password"
MYSQL_DATABASE = "fastapi_active_test"

ASYNC_URL = (
    f"mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
)
SYNC_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
)

_SKIP_REASON = (
    f"MySQL 8.4 가 {MYSQL_HOST}:{MYSQL_PORT} 에 없습니다. "
    "`docker compose -f compose.test.yaml up -d --wait` 로 띄운 뒤 다시 실행하세요."
)


def _mysql_is_reachable() -> bool:
    try:
        with socket.create_connection((MYSQL_HOST, MYSQL_PORT), timeout=1.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def mysql_available() -> bool:
    return _mysql_is_reachable()


@pytest.fixture(autouse=True)
def _require_mysql(request):
    """``@pytest.mark.mysql`` 이 붙은 테스트는 MySQL 이 없으면 skip 한다."""
    if request.node.get_closest_marker("mysql") and not _mysql_is_reachable():
        pytest.skip(_SKIP_REASON)


def drop_all_tables_sync() -> None:
    """스키마를 완전히 비운다 — ``alembic_version`` 을 포함한 **모든** 테이블.

    metadata 기준으로 지우면 모델에 없는 테이블(특히 ``alembic_version``)이 남는다.
    그러면 alembic 은 "아직 base 다"라고 판단하고 이미 존재하는 테이블을 다시
    만들려다 깨진다. 반대로 alembic_version 만 남기고 지워도 같은 문제다.
    두 상태가 어긋나지 않도록 통째로 비우는 것이 유일하게 안전한 초기화다.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(SYNC_URL)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table_name in connection.execute(text("SHOW TABLES")).scalars().all():
                connection.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    finally:
        engine.dispose()


def populate_metadata() -> None:
    """runtime 과 같은 경로로 ``Base.metadata`` 를 채운다.

    `migrations/env.py` 도 같은 `AppRegistry` 알고리즘을 쓴다 — 여기서 다른
    방식으로 모델을 모으면 통합 테스트가 검증하는 스키마가 실제와 갈린다.
    """
    from app.core.registry import AppRegistry

    registry = AppRegistry()
    registry.discover()
    registry.import_models()


@pytest.fixture
def mysql_empty_schema():
    """테이블이 하나도 없는 상태에서 시작한다 (migration 체인 테스트용)."""
    drop_all_tables_sync()
    yield
    drop_all_tables_sync()


@pytest_asyncio.fixture
async def mysql_session_maker():
    """registry 가 채운 metadata 로 새로 만든 스키마 위의 MySQL 세션 팩토리.

    테스트마다 스키마를 통째로 지우고 다시 만든다 — 통합 테스트가 서로의 데이터를
    보면 실패가 순서에 의존해 재현이 어려워진다.
    """
    from app.core.db.session import Base

    populate_metadata()
    drop_all_tables_sync()

    engine = create_async_engine(ASYNC_URL, poolclass=None)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
