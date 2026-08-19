"""FastAPI 진입점.

Django 스타일 앱 자동 등록: ``AppRegistry`` 가 ``app/features/*`` 를 스캔해 앱 목록을
만들고, 그 목록으로 라우터·모델·Admin 을 결선한다. **기능을 추가하거나 제거할 때
이 파일을 고치지 않는다** — 디렉터리 존재 자체가 등록 선언이다.

이 파일이 계속 담당하는 것: 애플리케이션의 주요 설정(미들웨어·예외 핸들러·문서·
lifespan·Admin 활성화 분기).

앱 규약과 한계는 ``app/core/registry.py`` 와 README 참고.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.db.session import create_db_tables, dispose_engine, engine, get_writer_db_session
from app.core.exception import AppException, ErrorResponse, ValidationException
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.registry import AppRegistry
from app.core.resources import ResourceManager
from app.core.tags_metadata import tags_metadata
from app.utils.logs import get_logger
from app.utils.logs.queue_logging import stop_queue_listener
from config import app_settings

logger = get_logger("main")

# =============================================================================
# 앱 자동 발견
#
# `app/features/*` 를 스캔해 앱 목록을 **한 번** 만들고, 아래 조립 과정 전체가
# 이 목록 하나를 재사용한다(라우터·모델·Admin). 기능을 추가·제거할 때 이 파일을
# 고칠 필요가 없다 (FR-01, FR-08, CR-03).
#
# 여기서 discover() 를 호출하는 위치가 중요하다. 앱 패키지 import 는 초기화 훅을
# 실행하는데(예: home 의 access-log sink 등록), 그 등록은 미들웨어 설정보다 먼저
# 끝나 있어야 한다. 그래서 FastAPI 인스턴스를 만들기 전에 발견을 마친다.
# =============================================================================
registry = AppRegistry()
registry.discover()
# 발견과 초기화를 분리한다. discover() 는 부작용이 없고(C-5), 부팅 시 한 번
# 해야 하는 앱별 결선은 여기서 **명시적으로** 요청한다.
registry.install_hooks()
registry.import_models()
logger.info("앱 자동 발견: %s", [m.name for m in registry.enabled_apps])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    애플리케이션 수명 주기 관리

    시작 시:
        - DEBUG=True: 데이터베이스 테이블 자동 생성 (개발 환경용)
        - DEBUG=False: 테이블 생성 건너뜀 (운영 환경은 Alembic 사용)

    종료 시:
        - 데이터베이스 엔진 리소스 정리
    """
    logger.info("[Startup] 애플리케이션 시작 (DEBUG=%s)", app_settings.DEBUG)

    # 정리 책임을 ResourceManager 에 맡긴다. 등록은 **start 이전에** 끝내므로
    # startup 이 중간에 실패해도 그 시점까지 확보된 자원이 회수된다. 정리는 등록의
    # 역순이고, 하나가 실패해도 나머지가 계속 실행된다 (ADR-001).
    #
    # 예산은 단일 monotonic deadline 에서 배분한다 — 단계 timeout 의 **합**으로
    # 정의하면 최악의 경우 오케스트레이터의 강제 종료에 걸려 정리가 아예 안 된다
    # (ADR-007).
    resources = ResourceManager()
    app.state.resources = resources

    # 등록 순서 = 정리의 역순. 로깅을 가장 먼저 등록해 **가장 나중에** 정리한다 —
    # 앞선 자원들의 종료 로그가 파일에 남아야 하기 때문이다. 백그라운드 태스크는 DB
    # 엔진을 쓰므로 엔진보다 나중에 등록해 먼저 정리한다.
    resources.register("logging-queue", stop_queue_listener, budget=5.0)
    resources.register("db-engines", dispose_engine, budget=10.0)
    resources.register("background-tasks", access_log_tasks.drain, budget=5.0)

    try:
        # DEBUG 모드일 때만 테이블 자동 생성
        # 운영 환경에서는 Alembic 마이그레이션 사용 권장
        if app_settings.DEBUG:
            try:
                await create_db_tables()
                logger.info("[Startup] 데이터베이스 테이블 생성 완료 (DEBUG 모드)")
            except Exception as e:
                logger.error("[Startup] 데이터베이스 테이블 생성 실패: %s", e)
                raise
        else:
            logger.info("[Startup] 테이블 자동 생성 건너뜀 (DEBUG=False, Alembic 사용)")

        yield
    finally:
        logger.info("[Shutdown] 애플리케이션 종료 시작")
        await resources.close()
        # 닫힌 자원 참조를 state 에 남기지 않는다 — 남기면 재진입 시 이전 자원을
        # 가리키는 핸들이 살아 있게 된다.
        app.state.resources = None
        logger.info("[Shutdown] 애플리케이션 종료 완료")


def _register_exception_handlers(app: FastAPI) -> None:
    """4가지 글로벌 예외 핸들러를 등록합니다."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """
        애플리케이션 커스텀 예외 핸들러

        AppException 및 하위 예외들을 처리하여 일관된 에러 응답을 반환합니다.
        """
        logger.error(
            "[AppException] %s: %s",
            exc.error_code,
            exc.message,
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": exc.error_code,
                "detail": exc.detail,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        요청 유효성 검증 예외 핸들러

        Pydantic 유효성 검증 실패 시 일관된 에러 응답을 반환합니다.
        """
        errors = exc.errors()
        detail = [
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in errors
        ]
        logger.warning(
            "[ValidationError] 요청 유효성 검증 실패",
            extra={
                "path": request.url.path,
                "method": request.method,
                "errors": detail,
            },
        )
        validation_exc = ValidationException(
            message="요청 데이터 유효성 검증에 실패했습니다.",
            detail=detail,
        )
        return JSONResponse(
            status_code=validation_exc.status_code,
            content=validation_exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """
        HTTP 예외 핸들러

        FastAPI/Starlette의 기본 HTTP 예외를 일관된 형식으로 변환합니다.
        """
        logger.warning(
            "[HTTPException] %s: %s",
            exc.status_code,
            exc.detail,
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=f"HTTP_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "HTTP 오류가 발생했습니다.",
                detail=None,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        일반 예외 핸들러

        처리되지 않은 모든 예외를 캐치하여 500 에러 응답을 반환합니다.
        운영 환경에서는 상세 정보를 숨깁니다.
        """
        # raw path 대신 route template 을 남긴다 — 경로에 박힌 식별자(사용자 id 등)가
        # 로그로 새지 않고, 같은 엔드포인트의 오류가 하나로 묶여 집계된다.
        route = request.scope.get("route")
        path_template = getattr(route, "path", None) or request.url.path

        logger.exception(
            "[UnhandledException] %s",
            type(exc).__name__,
            extra={
                "path": path_template,
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
        )
        # 예외 본문은 응답에 싣지 않는다. DEBUG 에서만 노출하는 방식도 쓰지 않는다 —
        # 개발 환경의 예외 메시지에도 DSN·쿼리·입력값이 그대로 실려 온다(C-5).
        # 상세는 위 로그(스택 트레이스 포함)에서 본다.
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="내부 서버 오류가 발생했습니다.",
                detail=None,
            ).model_dump(mode="json"),
        )


class HealthResponse(BaseModel):
    """헬스체크(liveness) 응답 스키마"""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"status": "ok", "version": "1.0.0"}]}
    )

    status: str = Field(description="상태 문자열")
    version: str = Field(description="애플리케이션 버전")


# readiness 는 별도 스키마를 두지 않고 HealthResponse 계약을 재사용한다.
# 실패는 프로젝트 표준 오류 응답(ErrorResponse)으로 내려간다.
_READY_DB_TIMEOUT_SECONDS = 2


def _add_health_and_docs(app: FastAPI) -> None:
    """헬스체크 엔드포인트와 Scalar API 문서를 등록합니다."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="헬스체크",
        description="서버의 정상 동작 여부를 확인합니다.",
        operation_id="healthCheck",
    )
    async def health_check() -> HealthResponse:
        """
        헬스체크 엔드포인트

        Returns:
            서버 상태 정보
        """
        return HealthResponse(
            status="healthy",
            version=app_settings.VERSION,
        )

    @app.get(
        "/ready",
        response_model=HealthResponse,
        tags=["Health"],
        summary="readiness 점검",
        description="DB 등 의존 자원까지 확인해 트래픽 수용 가능 여부를 알립니다.",
        operation_id="getReadiness",
        responses={503: {"model": ErrorResponse, "description": "의존 자원이 준비되지 않음"}},
    )
    async def readiness_check(
        db_session: AsyncSession = Depends(get_writer_db_session),
    ) -> HealthResponse | JSONResponse:
        """writer 로 `SELECT 1` 왕복 1회를 돌려 준비 상태를 확인한다.

        writer 를 쓰는 이유는 replica 가 살아 있어도 primary 가 죽으면 쓰기 트래픽을
        받을 수 없기 때문이다. 응답 지연이 무한정 늘어지지 않도록 timeout 을 건다.

        실패해도 예외를 그대로 올리지 않고 503 으로 낮춘다. 오류 응답에는 예외
        메시지·DSN·SQL 을 담지 않으며(C-5) 로그에도 예외 타입만 남긴다.
        """
        try:
            async with asyncio.timeout(_READY_DB_TIMEOUT_SECONDS):
                await db_session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("[Readiness] DB 점검 실패: %s", type(exc).__name__)
            return JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    error_code="NOT_READY",
                    message="의존 자원이 준비되지 않았습니다.",
                    detail=None,
                ).model_dump(mode="json"),
            )
        return HealthResponse(status="ready", version=app_settings.VERSION)

    # Scalar API 문서 (DEBUG 모드에서만 활성화)
    if app_settings.DEBUG:

        @app.get("/docs", include_in_schema=False)
        async def scalar_docs():
            """
            Scalar API 문서 페이지

            OpenAPI 스키마를 기반으로 인터랙티브 API 문서를 제공합니다.

            Note:
                이 엔드포인트는 DEBUG=True일 때만 활성화됩니다.
                운영 환경(DEBUG=False)에서는 보안을 위해 비활성화됩니다.
            """
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title=app_settings.PROJECT_NAME,
            )


# =============================================================================
# 애플리케이션 조립
# =============================================================================
app = FastAPI(
    title=app_settings.PROJECT_NAME,
    version=app_settings.VERSION,
    description=app_settings.DESCRIPTION,
    openapi_tags=tags_metadata,
    lifespan=lifespan,
    # 응답 직렬화는 FastAPI 기본 경로(Pydantic 이 JSON 바이트를 직접 생성)를 쓴다.
    # 이전에는 default_response_class=ORJSONResponse 였으나, response_model 이 있으면
    # Pydantic 이 먼저 직렬화해 orjson 은 이미 문자열이 된 값만 보므로 이득이 없고
    # FastAPI 0.141 에서 deprecated 됐다. 제거 전후 응답 바이트가 동일함을 확인했다.
    docs_url=None,  # Swagger UI 비활성화 (Scalar 사용)
    redoc_url=None,  # ReDoc 비활성화 (Scalar 사용)
    openapi_url="/openapi.json" if app_settings.DEBUG else None,
)

# 미들웨어 설정
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)

# API 문서 상태 로깅
if app_settings.DEBUG:
    logger.info("API 문서 활성화 (DEBUG 모드): /docs, /openapi.json")
else:
    logger.info("API 문서 비활성화 (운영 모드): 보안을 위해 /docs, /openapi.json 접근 차단")

# 글로벌 예외 핸들러
_register_exception_handlers(app)
logger.info("글로벌 예외 핸들러 설정 완료")

# 라우터 취합 — 발견된 앱의 `<name>_router` 를 registry 가 /api 에 마운트한다.
# 새 라우터 때문에 이 파일을 고치지 않는다 (FR-02, FR-08).
_mounted = registry.install_routers(app)
logger.info("라우터 include 완료: %d개", _mounted)

# 헬스체크 + Scalar 문서
_add_health_and_docs(app)

# SQLAdmin 관리자 페이지 (ADMIN 설정에 따라 활성화)
if app_settings.ADMIN:
    from app.features.admin import register_admin

    # 라우터·모델과 같은 발견 목록을 넘긴다 — 여기서 다시 스캔하지 않는다.
    admin = register_admin(app, engine, registry)
    logger.info("SQLAdmin 관리자 페이지 활성화 (ADMIN=True): /admin")
else:
    logger.info("SQLAdmin 관리자 페이지 비활성화 (ADMIN=False): /admin 접근 차단")


if __name__ == "__main__":
    import uvicorn

    from app.utils.logs import setup_uvicorn_logging

    uvicorn.run(
        "main:app",
        host=app_settings.SERVER_HOST,
        port=app_settings.SERVER_PORT,
        reload=app_settings.DEBUG,
        log_config=setup_uvicorn_logging(),
    )
