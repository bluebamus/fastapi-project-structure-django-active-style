"""
데이터베이스 세션 및 엔진 관리 모듈

SQLAlchemy 비동기 엔진과 세션 팩토리를 설정합니다.

주요 구성요소:
    - engine: FastAPI 요청 처리용 메인 엔진 = primary(writer) (pool_size=20, max_overflow=20)
    - read_engines: replica(reader) 엔진 목록 (복제 활성 시에만 생성)
    - db_router: 읽기/쓰기 바인딩을 결정하는 DatabaseRouter
    - background_engine: 백그라운드 태스크용 분리 엔진 (pool_size=10, max_overflow=10)
    - AsyncSessionLocal: 메인 세션 팩토리
    - BackgroundSessionLocal: 백그라운드 세션 팩토리
    - get_writer_db_session(): 쓰기 세션 제너레이터 (항상 primary) — 기능 코드의 쓰기용
    - get_read_only_db_session(): 읽기 전용 세션 제너레이터 (쓰기 시도 시 실패) — 기능 코드의 조회용
    - get_routed_db_session(): 세션 제너레이터 (읽기/쓰기 자동 라우팅) — 승인된 특수 경로 전용
    - get_background_db_session() / background_db_session(): 요청 밖 작업용
    (파일 끝의 get_session 등은 같은 객체를 가리키는 옛 별칭이다)

커넥션 풀 분리 이유:
    백그라운드 태스크(예: 접속 로그 저장)가 메인 API 요청의 커넥션 풀을
    고갈시키지 않도록 별도의 풀을 사용합니다.

읽기/쓰기 분리:
    DB_ROUTER_ENABLED=true 면 세션이 구문 성격에 따라 엔진을 자동 선택합니다.
    DB_REPLICATION_ENABLED=true 를 함께 켜면 SELECT 는 replica 로, 쓰기는 primary 로
    나갑니다. 라우터를 끄면 모든 쿼리가 단일 엔진으로 갑니다(기존 동작).
    자세한 규칙은 app/core/db/router.py 를 참고하세요.

사용 예시 (기능 코드는 세션을 직접 받지 않고 Dependency 가 Service 를 조립한다):
    async def get_catalog_service(
        session: AsyncSession = Depends(get_writer_db_session),
    ) -> CatalogService:
        return CatalogService(session)

    # 요청 밖 작업
    async with background_db_session() as session:
        await SomeService(session).do_write()
        await session.commit()
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,  # noqa: F401 - re-export
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.models.models_base import Base  # noqa: F401 - re-export
from app.utils.logs import get_logger
from config import db_settings

logger = get_logger("database")


# =============================================================================
# 메인 엔진 (FastAPI 요청용) = primary(writer)
# =============================================================================
# API 요청 처리를 위한 커넥션 풀
# - pool_size: 기본 유지 연결 수 (20)
# - max_overflow: 추가 허용 연결 수 (20) → 최대 40개 동시 연결
# - pool_pre_ping: 연결 사용 전 유효성 검사 (죽은 연결 자동 복구)
# - pool_recycle: 연결 재활용 주기 (MySQL wait_timeout보다 짧게 설정)
engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,  # SQL 로깅 (개발 시 True로 설정)
    pool_size=20,
    max_overflow=20,
    pool_timeout=30,  # 풀에서 연결 대기 시간 (초)
    pool_recycle=280,  # MySQL 기본 wait_timeout(28800s), 클라우드는 보통 300s
    pool_pre_ping=True,
    pool_reset_on_return="rollback",  # 반환 시 롤백으로 세션 초기화
    connect_args={
        "connect_timeout": 10,  # DB 연결 타임아웃 (초)
        "charset": "utf8mb4",  # 이모지 등 4바이트 UTF-8 지원
    },
)

# `engine` 은 SQLAdmin·Alembic 등 기존 소비처가 쓰는 이름이라 유지하고,
# 역할이 드러나는 별칭을 함께 노출한다.
writer_engine = engine


# =============================================================================
# replica 엔진 (읽기 전용) — 복제 활성 시에만 생성
# =============================================================================
def _create_read_engine(url: str) -> AsyncEngine:
    """replica 용 엔진을 만든다.

    읽기는 보통 쓰기보다 트래픽이 많고 트랜잭션이 짧으므로 풀을 primary 와
    같은 크기로 잡되, replica 대수만큼 커넥션이 곱해진다는 점에 유의한다.
    """
    return create_async_engine(
        url=url,
        echo=False,
        pool_size=20,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=280,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args={
            "connect_timeout": 10,
            "charset": "utf8mb4",
        },
    )


# 복제가 꺼져 있으면 빈 목록 → 라우터는 읽기도 primary 로 보낸다.
read_engines: list[AsyncEngine] = [
    _create_read_engine(url) for url in db_settings.MYSQL_REPLICA_URLS
]

# 읽기/쓰기 바인딩을 결정하는 라우터 (라우터가 꺼져 있어도 헬스체크용으로 구성해 둔다)
db_router = DatabaseRouter(
    writer=engine,
    readers=read_engines,
    sticky_after_write=db_settings.DB_READ_STICKY_AFTER_WRITE,
)


# =============================================================================
# 메인 세션 팩토리 (FastAPI DI용)
# =============================================================================
# - expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능
# - autoflush=False: 명시적 flush 권장 (예측 가능한 쿼리 타이밍)
#
# 라우터가 켜져 있으면 RoutingSession 이 구문마다 엔진을 고르고,
# 꺼져 있으면 단일 엔진에 직접 바인딩한다(오버헤드·동작 모두 기존 그대로).
if db_settings.DB_ROUTER_ENABLED:
    AsyncSessionLocal = create_routing_sessionmaker(db_router)
else:
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

# 기동 시 라우팅 구성을 한 줄로 남긴다 (비밀번호는 config.mask_dsn 이 마스킹).
logger.info("[database] 라우팅 구성: %s", db_settings.describe_routing())


# =============================================================================
# 백그라운드 태스크 전용 엔진 (메인 풀과 분리)
# =============================================================================
# 백그라운드 작업(로그 저장, 비동기 처리 등)용 별도 커넥션 풀
# 메인 API 요청과 분리하여 풀 고갈 방지
#
# 백그라운드 작업은 대부분 쓰기(접속 로그 적재 등)이므로 primary 에 직접 붙인다.
# 라우팅을 태우지 않는 편이 예측 가능하고, replica 로 새는 사고도 없다.
background_engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,
    pool_size=10,  # 백그라운드용은 작게 설정
    max_overflow=10,
    pool_timeout=60,  # 백그라운드는 대기 시간 여유있게
    pool_recycle=280,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
    connect_args={
        "connect_timeout": 10,
        "charset": "utf8mb4",
    },
)

# 백그라운드 세션 팩토리
BackgroundSessionLocal = async_sessionmaker(
    bind=background_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def background_db_session() -> AsyncGenerator[AsyncSession]:
    """요청 밖(백그라운드 태스크·Celery)에서 사용하는 세션 컨텍스트.

    요청 스코프 Depends(get_*_db_session)를 쓸 수 없는 곳에서 트랜잭션 경계를 제공한다.
    예외 시 롤백하고, 컨텍스트 종료 시 세션을 닫는다. 커밋은 호출자가 명시한다.

    Example:
        async with background_db_session() as session:
            await SomeService(session).do_write()
            await session.commit()
    """
    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_db_tables() -> None:
    """
    데이터베이스 테이블을 생성합니다.

    DEBUG=true 일 때 lifespan(manage_application_resources)에서 호출됩니다.
    이미 채워진 Base.metadata 의 테이블 중 없는 것만 만듭니다(checkfirst, 30초 guard).

    Note:
        모델 발견은 **이 함수가 하지 않는다**. main.py 가 만든 동일 ``AppRegistry``
        인스턴스가 이미 ``discover()`` + ``import_models()`` 로 ``Base.metadata`` 를
        채워둔 상태를 그대로 재사용한다(INV-5). 여기서 두 번째 스캔을 돌리면
        런타임과 Alembic 이 서로 다른 앱 목록을 볼 수 있고, 그 어긋남은 나중에
        "테이블이 안 생김" 으로만 드러나 원인을 찾기 어렵다.

    Raises:
        RuntimeError: ``Base.metadata`` 가 비어 있을 때. 0개 테이블을 조용히
            "생성 완료" 로 넘기지 않는다.
    """
    if not Base.metadata.tables:
        raise RuntimeError(
            "Base.metadata 가 비어 있어 테이블을 생성할 수 없습니다. "
            "create_db_tables() 는 모델을 직접 발견하지 않습니다 — 호출 전에 "
            "AppRegistry.discover() 와 import_models() 로 metadata 를 채우세요."
        )

    logger.info("[database] 테이블 생성 대상: %d개", len(Base.metadata.tables))
    logger.info("Creating database tables...")

    async with asyncio.timeout(30):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


async def get_routed_db_session() -> AsyncGenerator[AsyncSession]:
    """
    구문을 보고 엔진을 고르는 세션 제너레이터 — **승인된 특수 경로 전용**

    기능 코드는 이 의존성을 쓰지 않습니다. 쓰기는 get_writer_db_session(),
    조회는 get_read_only_db_session() 으로 의도를 미리 밝힙니다
    (tests/core/test_session_dependency_names.py 가 강제합니다).
    여기서 엔진을 구문으로 판정하면 쓰기 핸들러의 **첫 SELECT** 가 replica 로
    나가 복제 지연을 읽을 수 있습니다.

    요청 종료 시 자동으로 세션이 닫히고, 예외 발생 시 자동 롤백됩니다.

    Yields:
        AsyncSession: 데이터베이스 세션

    Note:
        - 세션은 요청 범위(request scope)로 관리됩니다
        - 한 요청 안에서 같은 Dependency 는 FastAPI 캐시로 같은 세션을 재사용합니다
          (writer·read-only 등 다른 getter 는 서로 다른 세션입니다)
        - 트랜잭션 경계는 쓰기 핸들러 본문이 `await service.commit()` 으로 관리합니다
    """
    start_time = time.perf_counter()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            # 예외 **메시지**는 기본 로그에 남기지 않는다 — DB 예외의 str() 에는 실행된
            # SQL 과 바인딩된 값이 그대로 들어 있고, 이 로거 이름("database")은
            # SQLNoiseFilter 의 NOISY_PREFIXES 에 걸리지 않아 그대로 통과한다.
            # 값이 키워드 형태가 아니라 RedactingFilter 도 지우지 못한다(C-4).
            # 추적이 필요한 debug 모드에서는 아래 debug 레코드가 전문을 남긴다.
            logger.error(
                "[get_routed_db_session] ROLLBACK - error: %s, duration: %.1fms",
                type(e).__name__,
                (time.perf_counter() - start_time) * 1000,
            )
            # DEBUG=true(유효 로그 레벨 DEBUG)에서만 SQL·바인딩 값·트레이스백 전문을 남긴다.
            logger.debug("[get_routed_db_session] ROLLBACK 상세", exc_info=True)
            raise e


async def get_read_only_db_session() -> AsyncGenerator[AsyncSession]:
    """
    읽기 전용 세션 제너레이터 (FastAPI DI)

    조회만 하는 엔드포인트에서 사용합니다. 쓰기를 시도하면 ``ReadOnlyRoutingError``
    로 즉시 실패해 "읽기 전용 핸들러가 몰래 쓰는" 사고를 코드 수준에서 차단합니다.
    라우터와 복제가 켜져 있으면 SELECT 는 replica 로 갑니다.

    Yields:
        AsyncSession: 읽기 전용 데이터베이스 세션

    Example:
        @app.get("/posts")
        async def list_posts(session: AsyncSession = Depends(get_read_only_db_session)):
            result = await session.execute(select(Post))
            return result.scalars().all()

    Note:
        - 쓰기 차단은 ``DB_ROUTER_ENABLED`` 와 무관하게 동작합니다. 세션 클래스
          이벤트(``before_flush``·``do_orm_execute``, app/core/db/router.py)가 집행합니다.
          라우터가 꺼져 있으면 읽기도 단일(writer) 엔진으로 나갈 뿐입니다.
        - 복제 지연을 허용할 수 없는 읽기라면 get_writer_db_session() 을 쓰세요.
        - 정리·롤백은 ``async with`` 가 맡습니다 (get_writer_db_session() Note 참고).
    """
    async with AsyncSessionLocal() as session:
        mark_read_only(session)
        yield session


async def get_writer_db_session() -> AsyncGenerator[AsyncSession]:
    """
    쓰기 세션 제너레이터 (FastAPI DI)

    항상 primary 로 나가는 세션을 반환합니다. 쓰기 직후 같은 요청에서 조회까지
    해야 하는 핸들러(예: 생성 후 결과 반환)에 적합합니다.

    Yields:
        AsyncSession: primary 에 고정된 데이터베이스 세션

    Note:
        예외 경로에 ``except Exception: rollback`` 을 두지 않습니다.
        ``AsyncSession.__aexit__`` 의 ``close()`` 가 활성 트랜잭션에 ROLLBACK 을 이미
        보내므로 덧붙여도 ROLLBACK 횟수는 같고, ``except Exception`` 은
        ``asyncio.CancelledError``(클라이언트가 응답 전에 끊은 경우)를 놓치는 반면
        ``__aexit__`` 는 놓치지 않습니다. 로깅 부수효과가 있는
        get_routed_db_session()·get_background_db_session() 은 except 블록이 필요합니다.

        기능 코드의 쓰기 의존성은 이것 하나입니다. get_routed_db_session() 도 쓰기를
        감지하면 primary 로 전환되지만 판정은 첫 구문 이후라, 이 의존성으로 "이
        핸들러는 쓰기다"를 미리 밝혀 첫 SELECT 조차 replica 로 새지 않게 합니다.
        commit 은 하지 않습니다(쓰기 핸들러 본문이 합니다).
    """
    async with AsyncSessionLocal() as session:
        using_writer(session)
        yield session


async def get_background_db_session() -> AsyncGenerator[AsyncSession]:
    """
    백그라운드 태스크용 세션 제너레이터

    메인 커넥션 풀과 분리된 백그라운드 풀을 사용합니다.
    asyncio.create_task() 등으로 생성된 백그라운드 작업에서 사용합니다.

    Yields:
        AsyncSession: 백그라운드 작업용 데이터베이스 세션

    Example:
        async def save_access_log(data: dict):
            async for session in get_background_db_session():
                log = UserAccessLog(**data)
                session.add(log)
                await session.commit()

    Note:
        - 메인 API 풀과 분리되어 있어 백그라운드 작업이 API를 블로킹하지 않습니다
        - 요청 밖 트랜잭션 경계는 background_db_session() 컨텍스트 사용을 권장합니다
    """
    start_time = time.perf_counter()

    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            # 예외 **메시지**는 기본 로그에 남기지 않는다 — DB 예외의 str() 에는 실행된
            # SQL 과 바인딩된 값이 그대로 들어 있고, 이 로거 이름("database")은
            # SQLNoiseFilter 의 NOISY_PREFIXES 에 걸리지 않아 그대로 통과한다.
            # 값이 키워드 형태가 아니라 RedactingFilter 도 지우지 못한다(C-4).
            # 추적이 필요한 debug 모드에서는 아래 debug 레코드가 전문을 남긴다.
            logger.error(
                "[get_background_db_session] ROLLBACK - error: %s, duration: %.1fms",
                type(e).__name__,
                (time.perf_counter() - start_time) * 1000,
            )
            # DEBUG=true(유효 로그 레벨 DEBUG)에서만 SQL·바인딩 값·트레이스백 전문을 남긴다.
            logger.debug("[get_background_db_session] ROLLBACK 상세", exc_info=True)
            raise e


# =============================================================================
# deprecated alias — 기존 호출부 호환용
# =============================================================================
# 정식 이름은 위의 `*_db_session` 이다(workflow-guide §2.1). 아래는 **같은 객체**를
# 가리키는 별칭이라, 이미 `dependency_overrides[get_read_session]` 을 쓰는 테스트도
# 그대로 동작한다. 다른 객체로 감싸면 override 키가 갈라져 조용히 안 먹는다.
# 신규 코드는 정식 이름을 쓴다.
get_session = get_routed_db_session
get_read_session = get_read_only_db_session
get_write_session = get_writer_db_session
get_background_session = get_background_db_session
background_session = background_db_session


# readiness 점검이 writer 응답을 기다리는 상한. 헬스체크는 빨리 답하는 것이 목적이라
# 요청 타임아웃보다 훨씬 짧게 둔다 — 여기서 늘어지면 오케스트레이터가 판정을 못 한다.
READINESS_TIMEOUT_SECONDS = 2.0


async def ping_writer_db(timeout: float = READINESS_TIMEOUT_SECONDS) -> None:
    """writer DB 에 ``SELECT 1`` 을 실행한다 (readiness 용).

    replica 가 아니라 **writer** 를 보는 이유는, 쓰기가 불가능한 인스턴스로
    트래픽이 들어오는 것이 준비 실패의 실질적 의미이기 때문이다.

    세션이 아니라 엔진 커넥션을 직접 쓴다. 헬스체크에 ORM 세션·라우팅 판정을
    태울 이유가 없고, 세션을 끼우면 "어느 엔진을 보는가" 가 라우터 설정에 따라
    달라진다.

    Raises:
        TimeoutError: ``timeout`` 안에 응답하지 못한 경우.
        Exception: 연결·쿼리 실패 시 드라이버 예외를 그대로 올린다. 호출자가
            사용자 응답에 내용을 싣지 않도록 주의해야 한다(DSN·자격증명 노출).
    """
    async with asyncio.timeout(timeout):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """
    앱 종료 시 엔진 리소스 정리

    lifespan의 shutdown 단계에서 호출됩니다.
    모든 커넥션 풀을 정리하고 데이터베이스 연결을 종료합니다.

    Note:
        이 함수가 호출되지 않으면 커넥션이 정리되지 않아
        데이터베이스에 좀비 연결이 남을 수 있습니다.
    """
    logger.info("[dispose_engine] Disposing database engines...")

    # 순차 호출이 아니라 **전부 시도**한다. 앞의 dispose 가 예외를 내면 뒤의 엔진이
    # 회수되지 않아 커넥션이 남는데, 그 증상은 한참 뒤 "커넥션 소진" 으로만 나타난다.
    # 정리는 "가능한 만큼 회수" 가 목표이지 "첫 실패에서 멈추기" 가 아니다.
    targets: list[tuple[str, AsyncEngine]] = [("writer", engine)]
    targets += [(f"reader#{index}", read_engine) for index, read_engine in enumerate(read_engines)]
    targets.append(("background", background_engine))

    failed: list[str] = []
    for name, target in targets:
        try:
            await target.dispose()
        except Exception as error:
            # 예외 원문은 남기지 않는다 — DSN 자격증명이 실려올 수 있다.
            failed.append(name)
            logger.warning(
                "[dispose_engine] %s 엔진 정리 실패 error_type=%s", name, type(error).__name__
            )
        else:
            logger.info("[dispose_engine] %s 엔진 정리 완료", name)

    if failed:
        logger.warning("[dispose_engine] %d개 엔진 정리 실패: %s", len(failed), ", ".join(failed))
    else:
        logger.info("[dispose_engine] 전체 엔진 정리 완료 - ALL DONE")
