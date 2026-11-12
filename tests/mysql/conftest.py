"""실제 MySQL 검증용 픽스처 — CI 전용(`.github/workflows/ci.yml` 의 mysql 잡).

평소 `pytest` 는 이 디렉터리를 수집하지 않는다(pyproject `norecursedirs`). 경로를 직접 주면 돈다.

    MYSQL_TEST_URL=mysql+aiomysql://root:<비밀번호>@127.0.0.1:3306 pytest tests/mysql

`MYSQL_TEST_URL` 은 **자기 소유의 빈 MySQL** 관리자 계정이어야 한다 — 테스트마다 DB·계정을
만들고 지운다. 변수가 없으면 skip 이 아니라 실패한다(기본값으로 아무 서버에도 붙지 않는다).
"""

import os
import uuid
from collections.abc import AsyncIterator, Callable, Iterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.db.models_registry import import_all_models
from app.core.db.session import ENGINE_SAFETY_OPTIONS, Base


@pytest.fixture(scope="session")
def mysql_server_url() -> URL:
    raw = os.environ.get("MYSQL_TEST_URL")
    if not raw:
        pytest.fail(
            "MYSQL_TEST_URL 이 없습니다 — tests/mysql 은 실제 MySQL 이 필요합니다(CI 전용). "
            "로컬에서는 자기 소유의 빈 MySQL 관리자 URL 을 주세요.",
            pytrace=False,
        )
    return make_url(raw).set(drivername="mysql+aiomysql", database=None)


def _sync(url: URL) -> URL:
    """관리 작업(DB·계정 생성)과 Alembic 은 동기 pymysql 로 한다."""
    return url.set(drivername="mysql+pymysql")


@pytest.fixture
def mysql_url(mysql_server_url: URL) -> Iterator[URL]:
    """테스트마다 빈 DB 하나 — 테스트가 끝나면 지운다."""
    name = f"t_{uuid.uuid4().hex[:16]}"
    admin = sa.create_engine(_sync(mysql_server_url), **ENGINE_SAFETY_OPTIONS)
    try:
        with admin.begin() as conn:
            conn.exec_driver_sql(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
        yield mysql_server_url.set(database=name)
    finally:
        with admin.begin() as conn:
            conn.exec_driver_sql(f"DROP DATABASE IF EXISTS `{name}`")
        admin.dispose()


@pytest_asyncio.fixture
async def mysql_engine(mysql_url: URL) -> AsyncIterator[AsyncEngine]:
    """모델 스키마를 세운 테스트 DB 의 앱 드라이버(aiomysql) 엔진."""
    import_all_models()
    engine = create_async_engine(mysql_url, **ENGINE_SAFETY_OPTIONS)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def mysql_user(mysql_server_url: URL, mysql_url: URL) -> Iterator[Callable[[str], URL]]:
    """``make(grants)`` → 그 테스트 DB 에만 권한이 있는 새 계정의 URL. 끝나면 계정을 지운다."""
    admin = sa.create_engine(_sync(mysql_server_url), **ENGINE_SAFETY_OPTIONS)
    created: list[str] = []

    # exec_driver_sql 은 pymysql 의 `query % args` 치환을 거친다 — 호스트 와일드카드는 '%%' 로 쓴다.
    def make(grants: str) -> URL:
        user = f"u_{uuid.uuid4().hex[:12]}"
        password = uuid.uuid4().hex
        with admin.begin() as conn:
            conn.exec_driver_sql(
                f"CREATE USER '{user}'@'%%' IDENTIFIED WITH caching_sha2_password BY '{password}'"
            )
            conn.exec_driver_sql(f"GRANT {grants} ON `{mysql_url.database}`.* TO '{user}'@'%%'")
        created.append(user)
        return mysql_url.set(username=user, password=password)

    try:
        yield make
    finally:
        with admin.begin() as conn:
            for user in created:
                conn.exec_driver_sql(f"DROP USER IF EXISTS '{user}'@'%%'")
        admin.dispose()
