# 아키텍처

이 문서는 현재 코드가 어떻게 짜여 있는지 설명합니다. 근거가 되는 파일 경로를 함께 적었습니다.

## 1. 디렉터리 구조

```text
main.py                 앱 조립 — 발견·미들웨어·예외 처리기·라우터·관리 화면·접근 정책 검사
config.py               모든 설정(Settings 클래스)과 기동 시 설정 검사
app/
  core/                 기능이 공유하는 기반
    registry.py         AppRegistry — 기능 앱 발견과 결선
    db/                 엔진·세션 Dependency(session.py), 읽기/쓰기 라우터(router.py), 모델 등록(models_registry.py)
    models/             Base·mixin(models_base.py), UTCDateTime(types.py)
    repositories/       BaseRepository·CRUDBase(ORM), RawCRUDBase·RawRepositoryBase(Raw SQL), DB 오류 번역
    services/           BaseService
    security/           접근 수준·인증 provider·JWT·refresh 저장소·rate limit·비밀번호 해시·관리 세션
    middlewares/        CORS, 접속 로그 미들웨어, 클라이언트 IP 판정, 백그라운드 태스크 관리
    resources.py        lifespan 자원 등록·정리
    redis.py            Redis provider·최소 버전 확인
    exception.py        AppException 계층과 ErrorResponse
  features/<name>/      기능 앱(auth, blog, catalog, home, reply, reports, sns, user)
  features/admin.py     SQLAdmin 조립
  celery/               Celery 앱·이벤트 루프 브리지·워커 생명주기
  utils/logs/           로깅 설정·필터·포매터·핸들러·큐
  utils/pagination/     페이지네이션 응답
  templates/admin/      SQLAdmin 템플릿 덮어쓰기(CSRF 토큰 주입)
migrations/             Alembic(env.py, versions/0001_baseline_schema.py)
scripts/                new_app.py(기능 생성), create_superuser.py, review_gate.py(검증 게이트)
tests/                  core·scripts·utils 와 앱 조립 수준 테스트
```

## 2. 앱 자동 배선

`app/core/registry.py` 의 `AppRegistry` 가 `app/features/*` 의 하위 패키지를 앱으로 봅니다(`_` 로 시작하는
디렉터리는 제외). 앱 하나는 다음 컨벤션을 따릅니다.

| 경로 | 계약 | 결선 |
|------|------|------|
| `api/routers/router.py` | 모듈 변수 `<name>_router: APIRouter` | `install_routers()` 가 `/api` 아래 마운트 |
| `models/` | import 시 `Base.metadata` 에 테이블 등록 | `import_models()` |
| `admin.py` | `admin_views: list[type]`(SQLAdmin `ModelView`) | `install_admin()` |
| `apps.py` | `ready()` — 부팅 초기화 훅 | `install_hooks()` |
| `tasks.py` | Celery 태스크 모듈 | `task_modules()` 가 워커 include 목록에 넣음 |

`discover()` 는 앱 목록만 만들고 부작용이 없습니다. 결선 메서드는 마지막 `discover()` 결과만 씁니다.
`main.py`·`migrations/env.py`·`app/celery/app.py`·`app/features/admin.py` 가 같은 레지스트리 결과를 쓰므로
런타임 테이블, 마이그레이션 대상, 워커 태스크, 관리 화면이 같은 앱 집합을 봅니다.

오류 정책: 선택 모듈이 아예 없으면 건너뜁니다. 모듈 안의 import 오류는 원래 예외를 그대로 올립니다. 모듈은
있는데 export 가 틀리면(라우터 변수 이름·타입, `admin_views` 누락·타입 오류) `AppContractError` 로 기동을
멈춥니다. 기능 패키지의 `__init__.py` 는 비워 두고 import 부작용을 두지 않습니다.

## 3. 계층

```text
router(view) ──Depends──▶ dependency(조립) ──▶ service ──▶ repository ──▶ AsyncSession
```

- **router** (`api/routers/v1/<name>.py`): 접근 수준 선언, 요청·응답 스키마, 쓰기 핸들러는 마지막에
  `await service.commit()` 을 한 번 부릅니다.
- **dependency** (`dependencies/<name>_dependencies.py`): 세션 Dependency 를 받아 Service 를 만들기만 합니다.
  조회용은 `get_read_only_db_session`, 변경용은 `get_writer_db_session` 을 받습니다.
- **service** (`services/`): `BaseService`(`app/core/services/services_base.py`)를 상속하고 Repository 를 만들어
  씁니다. 권한 판정이 필요한 서비스는 `OwnershipPolicy` 를 생성자로 받습니다.
- **repository** (`repositories/`): flush 까지만 하고 commit 하지 않습니다.
  - ORM: `BaseRepository[Model, PK]`(`app/core/repositories/repository_base.py`) — create·get_by_id·
    get_by_id_or_raise·get_all·count·exists·update·delete. 예제는 `app/features/catalog/`.
  - Raw SQL: `RawRepositoryBase`(`app/core/repositories/raw_repository_base.py`) — SQL 은 모듈 상수, 값은
    named bind 로만, 호출마다 `query_name` 필수. 로그에는 질의 이름·소요 시간·성공 여부만 남기고 SQL 본문·
    파라미터는 남기지 않습니다. 예제는 `app/features/reports/`.
- DB 예외는 `app/core/repositories/db_error_translator.py` 가 응답용 예외로 바꿉니다(중복 → 409, NOT NULL·
  참조 위반 → 422 계열). 응답에는 SQL·바인드 값을 싣지 않습니다.

## 4. DB 세션과 읽기/쓰기 라우팅

엔진과 세션은 `app/core/db/session.py` 에 있습니다.

| 이름 | 용도 |
|------|------|
| `get_writer_db_session` | 기능 코드의 쓰기 — 항상 primary. commit 은 핸들러가 함 |
| `get_read_only_db_session` | 기능 코드의 조회 — 쓰기(flush·DML)를 시도하면 `ReadOnlyRoutingError` |
| `get_routed_db_session` | 구문 성격으로 엔진을 고르는 투명 라우팅(특수 경로 전용) |
| `background_db_session()` / `get_background_db_session` | 요청 밖 작업(접속 로그 저장, Celery, 스크립트) — 분리된 풀 |

- 메인 엔진(pool 20 + overflow 20)과 백그라운드 엔진(10 + 10)을 나눠 접속 로그 저장이 API 풀을 고갈시키지
  않게 합니다. 모든 엔진은 `ENGINE_SAFETY_OPTIONS`(`hide_parameters=True`)로 만들어 예외·로그에 바인드 값이
  나오지 않습니다.
- `DB_ROUTER_ENABLED=true` 와 `DB_REPLICATION_ENABLED=true` 를 함께 켜면 `app/core/db/router.py` 의
  `DatabaseRouter` 가 SELECT 를 replica(`MYSQL_REPLICA_HOSTS`, 라운드로빈)로, 쓰기·잠금 조회를 primary 로
  보냅니다. 쓰기가 한 번 일어난 세션은 이후 SELECT 도 primary 에 고정됩니다(`DB_READ_STICKY_AFTER_WRITE`).
  `using_writer(session)` 은 복제 지연을 허용하지 않는 읽기를 primary 로 보냅니다.
- 읽기 전용 표시(`mark_read_only`)의 쓰기 거부는 라우터 설정과 무관하게 항상 동작합니다.
- 시각 컬럼은 `UTCDateTime`(`app/core/models/types.py`)입니다. UTC aware 값만 받고, MySQL 에서는
  `DATETIME(6)` 으로 저장하며, 읽으면 UTC aware 로 돌려줍니다.
- 스키마: `DEBUG=true` 면 기동 때 `create_db_tables()` 가 `create_all` 을 합니다. `DEBUG=false` 에서는 Alembic
  이 유일한 스키마 경로입니다(`migrations/`).

## 5. 인증과 권한

**접근 수준.** 모든 API 뷰는 경로 데코레이터의 `dependencies=[...]` 에 `Public`·`PublicWrite`·`LoginRequired`·
`SuperuserRequired` 중 하나를 선언합니다(`app/core/security/access.py`). 인자 `principal: CurrentPrincipal`·
`SuperuserPrincipal` 도 각각 로그인·슈퍼유저 선언으로 인정됩니다. 앱 조립이 끝난 뒤 `AccessPolicyGuard().verify(app)`
가 모든 라우트를 훑어, 선언이 없거나 모순인 뷰가 하나라도 있으면 `AppContractError` 로 기동을 멈춥니다.

**토큰.** `app/core/security/tokens.py` 의 `TokenService` 가 JWT(HS256 기본)를 발급·검증합니다. access 와 refresh
는 서명 키가 다르고 `type` claim 도 검사합니다. `iss`·`aud`·`exp`·`nbf` 를 확인하며 실패는 이유와 무관하게
401 하나입니다. access 기본 15분, refresh 기본 7일.

**refresh 회전.** `app/core/security/refresh_store.py` 가 Redis 에 발급된 refresh 의 `jti` 를 두고, 회전할 때
`GETDEL` 로 한 번만 소비합니다. 이미 쓴 토큰이 다시 오면 그 family 전체를 폐기하고, 로그아웃은 그 토큰의 family 를
폐기합니다. 비활성화·강등·비밀번호 해시 변경은 그 사용자의 모든 family 를 폐기합니다. 이미 발급된 access 는
만료까지 유효합니다.

**rate limit.** 로그인(사용자명·IP 별)과 가입은 `app/core/security/rate_limiter.py` 의 Redis 고정 창으로 제한하고
초과하면 429 와 `Retry-After` 를 줍니다(`AUTH_LOGIN_*`, `AUTH_REGISTER_*`).

**비밀번호.** `app/core/security/password_hasher.py` — 새 해시는 Argon2. 예전 bcrypt 해시는 검증 후 Argon2 로
다시 저장합니다. 해시 연산은 스레드로 넘깁니다.

**소유권.** 권한은 슈퍼유저/일반 2단계입니다. 글·댓글 수정·삭제는 `OwnershipPolicy.ensure_can_modify` 가 소유자
또는 슈퍼유저만 통과시킵니다(작성자가 없는 옛 행은 슈퍼유저만).

| 영역 | 공개 | 로그인 | 슈퍼유저 |
|------|------|--------|----------|
| `/health`, `/ready`, `/docs` | 모두 | | |
| auth | register·login·refresh·logout(`PublicWrite`) | `GET /me` | |
| blog·sns·reply | 목록·상세 | 생성·수정·삭제(수정·삭제는 소유자) | |
| catalog | 목록·상세 | | 생성·수정·삭제 |
| reports | | | 일별 매출 |
| home(접속 로그) | | | 목록·최근·IP별·사용자별·통계 |
| user | | 상세·수정(본인 또는 슈퍼유저) | 목록·생성·삭제 |

## 6. 관리 화면

`ADMIN_DISABLED=false` 면 `main.py` 가 `app/features/admin.py` 의 `register_admin()` 을 부르고, 이 함수가 SQLAdmin
을 `/admin` 에 만들고 레지스트리로 각 앱의 `admin_views` 를 등록합니다. `ADMIN_DISABLED=true` 면 sqladmin 과
ModelView 모듈을 import 하지도 않습니다.

- 로그인 백엔드 `app/features/auth/admin_auth.py`: 활성 슈퍼유저만 통과, 실패 사유를 구분하지 않음, 로그인
  rate limit(API 와 키를 따로 셈), 성공 시 세션 ID 회전, 매 요청 DB 에서 사용자 상태를 다시 확인.
- 세션 `app/core/security/admin_session.py`: 쿠키 `admin_session`(`Path=/admin`, `SameSite=Strict`, HttpOnly,
  배포 환경은 Secure)에는 무작위 세션 ID 만 두고 내용은 Redis 에 저장합니다. Redis 키는 세션 ID 의
  HMAC(`SESSION_SECRET_KEY`)이며, 미사용 만료(`ADMIN_SESSION_IDLE_SECONDS`)와 절대 만료
  (`ADMIN_SESSION_MAX_AGE_SECONDS`)가 있습니다. 강등·비활성화·삭제·비밀번호 변경은 그 사용자의 세션을 즉시 지웁니다.
- CSRF: 세션마다 토큰 하나. 로그인 폼은 hidden 필드로, 로그인 이후의 상태 변경 요청은 `AdminCsrfMiddleware` 가
  헤더 `X-CSRF-Token` 또는 폼 필드 `csrf_token` 으로 검사합니다. 토큰은
  `app/templates/admin/sqladmin/base.html` 이 폼·fetch·XHR 에 붙입니다. 로그아웃은 POST 전용입니다.
- 날짜 필터 `app/core/admin_filters.py` 의 `LocalDateFilter` 는 `TIME_ZONE` 기준 날짜(또는 기간)를 UTC 범위로
  바꿔 질의합니다.

## 7. 미들웨어와 예외 처리

`main.py` 가 등록하는 순서(바깥쪽이 마지막 등록):

1. `CustomCORSMiddleware`(`app/core/middlewares/cors_middleware.py`) — `CORS_*` 설정.
2. `UserInfoMiddleware`(`app/core/middlewares/user_info_middleware.py`) — `ACCESS_LOG_ENABLED` 이고 제외 경로·
   확장자가 아닌 요청의 접속 정보(IP·User-Agent 해석·경로·상태·응답 시간)를 모아, 응답 뒤 백그라운드 태스크로
   저장합니다. 저장 방법은 home 앱이 `apps.py` 의 `ready()` 에서 등록한 sink 가 정합니다. 쿼리 문자열의 민감 키
   (`ACCESS_LOG_SENSITIVE_QUERY_KEYS`)는 가립니다. 백그라운드 태스크는 동시 실행 상한을 넘으면 버리고 셉니다
   (`app/core/middlewares/background_tasks.py`).
3. `answer_unhandled_exception` — 처리기가 없는 예외를 기존 500 처리기로 끝내 traceback 중복과 연결 끊김을 막습니다
   (`DEBUG=true` 면 다시 던짐).

클라이언트 IP 는 `ClientIPResolver`(`app/core/middlewares/client_ip.py`)가 `X-Forwarded-For` 의 오른쪽에서
`TRUSTED_PROXY_HOPS` 번째 값으로 정합니다. 접속 로그와 로그인 rate limit 이 이 값을 씁니다.

예외 처리기(`main.py`): `AppException` 계층(`app/core/exception.py`) → 해당 상태 코드와 `ErrorResponse`,
검증 오류 → 422 `VALIDATION_ERROR`(OpenAPI 문서의 422 스키마도 `ErrorResponse` 로 바꿈), Starlette HTTP 예외 →
같은 형식(예외 헤더 유지), Redis 연결·타임아웃 → 503, 그 밖 → 500. 응답 본문에는 예외 원문을 싣지 않습니다.

## 8. 로깅

`app/utils/logs/` 가 소유합니다. `configure_logging()` 이 `build_dictconfig()`(`config.py` 와 이름이 같은
`app/utils/logs/config.py`)를 root 에 한 번 적용하고, `get_logger(name)` 은 핸들러 없는 자식 로거를 돌려줍니다.

- 핸들러는 root 에만 있습니다. uvicorn·Celery 로그도 root 로 전파돼 같은 형식으로 찍힙니다.
- 헤더의 `app=` 은 로거 이름이 아니라 소스 파일 경로로 정합니다(`ContextFilter`). 새 기능을 추가해도 로깅 설정을
  고칠 곳이 없습니다. 헤더별 레벨은 `LOG_APP_LEVELS`(예: `blog=DEBUG,sqlalchemy=WARNING`)로 줍니다.
- `RedactingFilter` 가 메시지·traceback 의 비밀값(토큰·비밀번호·DSN 비밀번호 등)을 가리고, `SQLNoiseFilter` 가
  SQL 소음을 거릅니다.
- ENV 별: development/test 는 콘솔, staging/production 은 콘솔 + 파일(`LOG_FILE_ENABLED`), 시각은 UTC.
- 파일은 프로세스별(`app.log`·`error.log`, Celery 는 `celery.log`·`celery-error.log`)이고
  `DailyRotatingFileHandler` 가 UTC 자정과 `LOG_MAX_SIZE_MB` 에서 교체하며 `LOG_RETENTION_DAYS` 지난 파일을
  지웁니다. 파일 쓰기는 상한 있는 큐와 별도 스레드(`queue_logging.py`)로 이벤트 루프 밖에서 하고, 넘친 레코드는
  세어서 종료 때 보고합니다.
- 한 파일을 한 프로세스가 쓴다는 전제입니다. uvicorn `--workers` 2 이상이나 Celery prefork 동시성 2 이상에서
  파일 로그를 쓰면 회전이 안전하지 않으므로, 그때는 파일 로그를 끄고 콘솔을 수집합니다.

## 9. Celery

`app/celery/app.py` 의 `celery_app` 은 broker·backend 로 Redis(`REDIS_URL`)를 쓰고, include 목록을
`AppRegistry().task_modules()` 로 만듭니다. 현재 태스크는 `app/features/home/tasks.py` 의
`home.aggregate_access_stats` 와 접속 로그 보존 기간(`ACCESS_LOG_RETENTION_DAYS`) 삭제 태스크입니다.
`beat_schedule` 은 비어 있습니다.

- 태스크는 요청 밖이라 `background_db_session()` 으로 세션을 열고, 서비스는 API 와 같은 조립 함수로 만듭니다.
- `app/celery/task.py` 의 `run_async` 는 워커 프로세스당 이벤트 루프 하나를 재사용해 코루틴을 실행합니다(async
  커넥션이 만든 루프에 묶이기 때문).
- `app/celery/worker_lifecycle.py` 는 prefork 자식 프로세스가 부모에게서 물려받은 커넥션 풀을 닫지 않고 버리고
  (`dispose(close=False)`), 자식 종료 때 이벤트 루프를 닫도록 신호를 연결합니다.

## 10. 수명주기

`main.py` 는 import 시점에 레지스트리 발견 → `install_hooks()` → 모델 import → FastAPI 생성 → 미들웨어·예외 처리기
→ 라우터 마운트 → `/health`·`/ready`·`/docs` → 관리 화면 → `AccessPolicyGuard` 순서로 조립합니다. `config.py`
import 시점의 설정 검사가 이보다 먼저 돕니다.

lifespan 은 `app/core/resources.py` 의 `manage_application_resources()` 입니다.

- 시작: 로깅 큐·DB 엔진 정리를 먼저 등록하고, Redis 에 연결해 PING 과 최소 버전(7.0)을 확인한 뒤
  `app.state.redis` 에 둡니다. 실패하면 기동이 멈춥니다. `DEBUG=true` 면 테이블을 만듭니다.
- 종료: 등록의 역순(백그라운드 태스크 drain → Redis → DB 엔진 → 로깅 큐)으로, 하나가 실패해도 나머지를 계속
  정리하고 전체를 한 deadline 안에서 끝냅니다. 시작 도중 실패해도 같은 경로로 정리합니다.

요청 쪽은 `app/core/redis.py` 의 `get_redis` 로 Redis 를 받습니다. `/ready` 는 writer DB `SELECT 1` 과 Redis
PING 을 동시에(각 2초 상한) 확인합니다.
