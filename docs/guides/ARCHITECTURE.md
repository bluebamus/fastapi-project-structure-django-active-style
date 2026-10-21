# 아키텍처 레퍼런스

이 저장소가 **실행 중에 어떻게 조립되고 동작하는가**를 한곳에 모은 문서입니다. 폴더 구조,
앱 자동 등록, 설정·로깅, 기동과 종료, 요청 처리, DB 세션, 보안 경계를 다룹니다.

- 설치·실행·API 목록은 [README](../../README.md), 새 기능을 만드는 절차는
  [기능 개발 가이드](./DEVELOPMENT.md)를 봅니다.
- §3~§9 의 흐름을 도식으로 따라가려면 [서버 수명주기 안내서](./workflows/server-lifecycle.html)를 엽니다.
  표·목록의 원문은 이 문서입니다.
- 코드와 이 문서가 다르면 **코드가 정답**입니다. 차이를 발견하면 이 문서를 고칩니다.

---

## 1. 폴더 구조와 의존 방향

```text
fastapi-project-structure-django-active-style/
├── main.py                 # 조립: AppRegistry 발견·결선 + 미들웨어·예외·문서·lifespan·Admin
├── config.py               # Pydantic Settings 9종 + 설정 검사 3종(validate_env_source·validate_renamed_settings·validate_deployment_safety)
├── pyproject.toml          # 의존성·도구 설정 ([tool.uv] package = false, pytest env 주입)
├── .python-version         # 3.14 (requires-python 은 >=3.13 — TypeVar default 사용)
├── .env.example            # 설정 전체 목록 (config.py 와 양방향 일치를 테스트가 강제)
├── alembic.ini             # script_location = migrations
├── compose.test.yaml       # 테스트 전용 컨테이너: MySQL 8.4 (호스트 3310) · Redis 7.4 (호스트 6381)
├── compose.e2e.yaml        # 전수 통합(e2e) 컨테이너: MySQL primary + GTID replica · Redis (§13)
├── app/
│   ├── features/           # 기능 앱 — 디렉터리 존재 = 등록 선언
│   │   ├── admin.py        # SQLAdmin 조립 진입점 register_admin() (앱이 아닌 파일)
│   │   └── auth/ blog/ catalog/ home/ reply/ reports/ sns/ user/   # 현재 8개 앱
│   ├── core/               # 프레임워크 인프라
│   │   ├── registry.py     # AppModule / AppRegistry / AppContractError
│   │   ├── resources.py    # ResourceManager + manage_application_resources()
│   │   ├── exception.py    # AppException 계층 + ErrorResponse
│   │   ├── tags_metadata.py
│   │   ├── db/             # session.py(엔진·세션·Dependency) · router.py(읽기/쓰기 라우팅) · models_registry.py(호환 facade)
│   │   ├── models/models_base.py         # Base + UUIDPrimaryKeyMixin · CreatedAtMixin · UpdatedAtMixin
│   │   ├── repositories/   # repository_base.py·crud_base.py (ORM) / raw_repository_base.py·raw_crud_base.py (Raw)
│   │   ├── services/services_base.py     # BaseService (commit/rollback 헬퍼)
│   │   ├── security/       # tokens.py(TokenService) · refresh_store.py(RefreshTokenStore) · rate_limiter.py(RateLimiter) · access.py(접근 수준) · admin_session.py(관리 세션)
│   │   └── middlewares/    # cors · user_info(접속 로그 수집) · background_tasks · access_log_sink
│   ├── celery/             # Celery 앱: app.py(registry 로 include) · task.py(run_async) · worker_lifecycle.py
│   └── utils/              # 순수 유틸: logs · pagination · validators
├── migrations/             # env.py 가 런타임과 같은 AppRegistry 로 모델 수집 / versions/
├── scripts/                # new_app.py(앱 생성기) · review_gate.py(로컬·CI 공용 게이트) · create_superuser.py(첫 관리자)
├── tests/                  # 횡단 테스트: core/ · integration/(MySQL) · e2e/(전수 통합) · scripts/ · utils/ · test_*.py
├── docs/                   # guides/(현행) · specs/(고정 기준선) · crp/(검수 이력)
└── logs/ media/ static/ poc/   # 런타임·예약 디렉터리 (추적하지 않음, logs/ 는 기동 시 자동 생성)
```

기능 테스트는 `app/features/<name>/tests/`, 여러 기능이나 `core` 계약을 보는 테스트는 최상위
`tests/` 에 둡니다. pytest `testpaths` 가 `tests` 와 `app` 을 모두 수집합니다.

### 의존 방향

```text
features → core → utils
```

| 영역 | 규칙 |
|---|---|
| `app/features/<name>/` | 비즈니스 코드는 전부 여기. `core`·`utils`·`config` 를 쓰고 **다른 기능을 import 하지 않는다**. 예외는 `auth → user`(자격증명을 `User` 모델이 소유) 하나다. |
| `app/core/` | 특정 기능의 Service/Repository 를 직접 알지 않는다. `AppRegistry` 가 등록을 위해 기능 모듈을 동적 import 하는 것은 예외다. 기능이 core 에 붙어야 하면 **등록 훅**을 쓴다(예: home 이 `set_access_log_sink()` 로 접속 로그 저장소를 등록). |
| `app/utils/` | 상위 계층을 import 하지 않는다. 누구나 쓸 수 있다. |

기능 간 데이터 연결도 import 가 아니라 값으로 합니다. 예: `Reply.post_id` 는 FK 제약 없는
문자열 참조입니다. 여러 기능이 참여하는 업무 흐름이 생기면 core 로 옮기지 말고 orchestration
경계를 따로 설계합니다. 기능 간 import 금지는 리뷰로 지키는 규칙이고, 테스트가 강제하는 경계는
둘입니다: 접속 로그 미들웨어가 home 을 import 하지 않는다(`tests/core/test_access_log_decoupling.py`),
발견 단계가 기능의 라우터·모델을 끌어오지 않는다(`tests/core/test_import_boundary.py`).

---

## 2. 앱 자동 등록 (AppRegistry)

`app/features/<name>/` 디렉터리를 만드는 것이 곧 앱 등록입니다. 중앙 목록(`INSTALLED_APPS`)도
앱별 설정 파일도 없습니다. 설계의 뼈대는 **발견과 결선의 분리**입니다.

```text
app/features/*
      │
AppRegistry.discover()            "어떤 앱이 있는가" — 부작용 0
      ├─ install_hooks()   ──→ 각 앱 apps.py 의 ready()
      ├─ import_models()   ──→ Base.metadata ──→ DEBUG create_all / Alembic
      ├─ install_routers() ──→ app.include_router(<name>_router, prefix="/api")
      ├─ task_modules()    ──→ Celery include (워커 — 각 앱 tasks.py)
      └─ install_admin()   ──→ Admin.add_view(...)   (ADMIN_DISABLED=false 일 때만)
```

결선 메서드는 마지막 `discover()` 결과만 쓰고 스스로 다시 스캔하지 않습니다. 목록이 둘이면
런타임과 마이그레이션이 서로 다른 앱을 보게 되고, 그 어긋남은 배포 뒤 "운영에만 테이블이
없다" 로 드러납니다. 요구사항 ID(`FR-*`·`NFR-*`·`SEC-*` 등, 코드 주석이 인용)와 설계 근거는
[`docs/specs/django-style-app-automation.md`](../specs/django-style-app-automation.md)에 있습니다.

### 2.1 규약 — registry 가 찾는 여섯 가지

| 경로 | 계약 | 없으면 |
|---|---|---|
| `<name>/__init__.py` | 앱 패키지 선언. **부수효과를 두지 않는다** | 패키지가 아니므로 발견되지 않음 |
| `<name>/apps.py` | `ready()` — 부팅 시 한 번 실행되는 초기화 훅 | 훅 없는 앱 |
| `<name>/api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱 |
| `<name>/models/` | import 시 ORM 모델이 `Base.metadata` 에 등록. 패키지와 `models.models` 모듈을 **둘 다** import 한다 | 모델 없는 앱 (실제 `auth`) |
| `<name>/admin.py` | `admin_views: list[type]` (SQLAdmin `ModelView`) | 관리 화면 없는 앱 |
| `<name>/tasks.py` | Celery 태스크(`@celery_app.task(name="<name>.<action>")`). 워커 include 에 들어간다 | 태스크 없는 앱 |

발견 규칙:

- `app.features` 의 **직계** 하위 패키지만 봅니다(재귀 없음). 이름이 `_` 로 시작하면 제외합니다
  (`__pycache__`, 작업 중인 `_scratch` 등).
- 순서는 **앱 이름 알파벳순**으로 고정입니다. 파일시스템 순서와 무관하게 라우트 등록 순서가
  같습니다. 앱 사이에 로딩 순서 의존을 만들지 않습니다.
- 앱 이름은 파이썬 식별자여야 합니다. `order-items` 같은 디렉터리도 발견·import 는 되지만(모델도
  등록된다) `<name>_router` 를 변수로 선언할 수 없어, `router.py` 가 있으면 `AppContractError` 로 기동이
  멈춥니다. 생성기(`scripts/new_app.py`)는 식별자가 아닌 이름을 거부합니다.
- 폴더가 있으면 다음 부팅에 켜집니다. 실험용 코드는 `_` 로 시작하는 이름을 쓰거나
  `app/features` 밖에 둡니다.

### 2.2 오류 정책 — 파일 부재는 선택, 잘못된 계약은 오류

자동 등록은 실패를 조용하게 만듭니다(라우터가 안 붙어도 서버는 뜹니다). 그래서 없는 것과 틀린
것을 구분합니다.

| 상황 | 동작 |
|---|---|
| 선택 모듈(`apps.py`·`router.py`·`models`·`admin.py`·`tasks.py`) 자체가 없다 | 건너뛴다 |
| 선택 모듈 **안의** import 가 틀렸다 | 원래 `ModuleNotFoundError` 를 그대로 올려 기동 실패 |
| `router.py` 에 `<name>_router` 가 없거나 `APIRouter` 가 아니다 | `AppContractError` 로 기동 실패 |
| `admin.py` 에 `admin_views` 가 없다 / list 가 아니다 / `ModelView` 가 아니다 | `AppContractError` 로 기동 실패 |
| 두 앱이 같은 `APIRouter` 객체나 같은 `ModelView` 를 내보낸다 | `AppContractError` 로 기동 실패 |
| `tasks.py` **안의** import 가 틀렸다 | 발견은 `find_spec` 으로 존재만 본다(태스크 모듈이 `celery_app` 을 import 해 순환이 되므로). 워커 기동 시 Celery 가 include 를 import 하며 원래 예외로 실패 |

판정은 `AppModule._import_optional()` 이 `ModuleNotFoundError.name` 이 **찾던 그 모듈(또는 상위
패키지)** 일 때만 "부재" 로 봅니다. method+path 단위의 라우트 충돌은 registry 가 검사하지
않습니다 — 경로 목록은 `tests/test_route_inventory.py` 가 고정합니다.

### 2.3 초기화 훅 — `apps.py` 의 `ready()`

```python
# app/features/home/apps.py
from app.features.home.access_log_sink import register_sink


def ready() -> None:
    register_sink()   # core 미들웨어에 자신을 저장소로 등록한다
```

- `install_hooks()` 가 발견 순서대로 호출합니다. `main.py` 는 FastAPI 인스턴스를 만들기 **전에**
  `discover()` → `install_hooks()` → `import_models()` 를 끝냅니다(훅이 모델 import 보다 먼저).
- `__init__.py` 의 import-time 부수효과를 쓰지 않는 이유: "무엇을 import 하면 무슨 일이
  일어나는가" 를 코드에서 읽을 수 없고, 테스트가 모듈을 import 하는 것만으로 상태가 바뀌어
  결과가 실행 순서에 좌우됩니다.
- `ready()` 는 **멱등**이어야 하고, DB·네트워크 I/O 와 무거운 계산을 하지 않습니다(부팅 시간에
  그대로 더해지고 실패 원인이 발견 단계로 숨습니다).
- Django `AppConfig.ready()` 와 역할은 같지만, 프레임워크가 보장하는 준비 단계가 아니라
  `main.py` 가 부르는 함수입니다. Alembic 경로는 훅을 호출하지 않습니다.

### 2.4 결선 지점

| 호출자 | 하는 일 |
|---|---|
| `main.py` | 한 `AppRegistry` 인스턴스로 훅·모델·라우터·Admin 을 모두 결선 |
| `migrations/env.py` | 새 `AppRegistry` 로 `discover()` + `import_models()` (같은 발견 규칙, 훅 없음) |
| `app/celery/app.py` | 새 `AppRegistry` 로 `discover()` + `import_models()` + `task_modules()` → `include` (훅 없음) |
| `app/core/db/models_registry.py` | `import_all_models()` — registry 에 위임하는 호환 facade (테스트가 사용) |
| `app/features/admin.py` | `register_admin(app, engine, registry)` → `create_admin_interface()`(Admin 생성 + 로그인 백엔드 `AdminAuthBackend` 주입, `/admin` 마운트) → `registry.install_admin()`(뷰 등록) |

`register_admin` 이 registry 를 **인자로 받는** 것이 계약입니다. 스스로 발견하면 라우터·모델과
다른 앱 집합을 볼 수 있습니다. Admin 인증 백엔드(`app/features/auth/admin_auth.py` 의
`AdminAuthBackend`)는 `create_admin_interface()` 가 주입합니다(`Admin` 생성 인자이기 때문 — §10.3).
`ADMIN_DISABLED=true` 면 `sqladmin`·기능 `admin.py`·인증 백엔드가 **로드조차 되지 않습니다** — 그래서
기능 `__init__.py` 에서 `admin_views` 를 재노출하지 않습니다.

### 2.5 Django 와의 대응 범위

| Django | 이 프로젝트 | 판정 |
|---|---|---|
| 앱 registry | `AppRegistry` 가 목록을 한 번 만들어 모든 결선에 제공 | 대응 |
| `AppConfig.ready()` | 앱 `apps.py` 의 `ready()` (`install_hooks()` 가 호출) | 역할만 대응 |
| 모델 발견 | 앱 `models` import 로 `Base.metadata` 구성 | 대응 |
| Admin 등록 | 앱 `admin.py` 의 `admin_views` 자동 수집 | 대응 |
| `startapp` | `python -m scripts.new_app <name>` | 대응 |
| URLconf | `<name>_router` 를 `/api` 에 자동 마운트 | Django 에 없는 확장 |
| `INSTALLED_APPS` | 디렉터리 존재 자체가 등록 선언 | 의도적인 차이 |
| `settings.py` / `LOGGING` | `config.py` / `build_dictconfig()` | 대응 (앱별 로거 등록은 없음, §5) |

Django 호환 계층도 Django 기반도 아닙니다. Django 의 앱 단위 응집도와 registry 개념을 FastAPI
조립 과정에 옮긴 것입니다.

### 2.6 앱 제거·이름 변경·진단

- 디렉터리를 지우면 다음 기동에서 라우터·모델·Admin, 그리고 **워커의 Celery 태스크**(include)에서
  빠집니다. 중앙 Celery 패키지는 기능을 import 하지 않으므로 워커도 import 오류 없이 뜹니다. 다만
  큐에 이미 들어간 그 앱의 태스크 메시지는 워커가 "등록되지 않은 태스크" 로 버립니다 — 발행을 먼저
  멈추고 큐를 비운 뒤 지웁니다. **DB 테이블과 데이터는 남습니다** — 보존·이관과 삭제 revision 을
  따로 설계합니다.
- 이름을 바꾸면 공개 URL prefix, `<name>_router`, import 경로, Celery 태스크 이름
  (`home.aggregate_access_stats` 형태), migration 참조가 함께 바뀝니다.

| 증상 | 먼저 볼 것 |
|---|---|
| 앱 전체가 안 보인다 | 직계 하위 패키지인지, `__init__.py` 가 있는지, 이름이 식별자이고 `_` 로 시작하지 않는지 |
| 라우터만 없다 | `api/routers/router.py` 경로와 `<name>_router` 이름 |
| migration 이 비었다 | 모델이 `Base` 를 상속하고 `models/` 아래에서 import 되는지 |
| Admin 뷰가 없다 | `ADMIN_DISABLED` 값, `admin_views` 가 `ModelView` 목록인지 |
| 기동 시 `ModuleNotFoundError` | 선택 모듈 **내부**의 잘못된 import |

회귀 가드: `tests/test_app_autowiring.py`(임시 앱 결선 + 중앙 파일 해시 불변),
`tests/test_router_registration.py`, `tests/test_admin_wiring.py`(모델을 가진 기능은 자기
`admin.py` 를 가진다), `tests/core/test_registry_*.py`(태스크 발견·앱 제거 포함),
`tests/core/test_celery_app.py`(include 출처·Celery 패키지의 기능 import 금지).

---

## 3. 기동 순서

```text
main:app import
  ├─ config.py import        설정 객체 생성·검증, validate_env_source() → validate_deployment_safety()
  ├─ app/core/db/session.py   엔진·세션 팩토리 생성 (아직 접속하지 않음)
  ├─ AppRegistry              discover → install_hooks → import_models
  ├─ FastAPI(...)             문서 URL(openapi_url 은 DEBUG 일 때만), lifespan
  ├─ app.openapi = _openapi_with_actual_422     문서의 422 를 ErrorResponse 로 바꾸는 후처리(§9)
  ├─ CustomCORSMiddleware(app).configure_cors() → setup_user_info_middleware(app)
  ├─ _register_exception_handlers(app)          5종 글로벌 핸들러(§9)
  ├─ @app.middleware answer_unhandled_exception 가장 바깥 사용자 미들웨어 — 처리기 없는 예외를 500 으로(§9)
  ├─ registry.install_routers(app)              <name>_router → /api
  ├─ _add_health_and_docs(app)                  /health · /ready · (DEBUG) Scalar /docs
  ├─ ADMIN_DISABLED=false → register_admin(app, engine, registry)   (true 면 import·마운트 없음)
  └─ AccessPolicyGuard().verify(app)            모든 뷰의 접근 수준 선언 검사, 위반이면 AppContractError(§10.2)
ASGI lifespan 진입
  └─ manage_application_resources(app)          Redis ping·버전(≥7.0) → (DEBUG) create_db_tables → yield
```

- `python main.py` 는 조립 후 `uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT,
  reload=DEBUG, log_config=None)` 을 호출합니다(uvicorn 로거는 root 의 프로젝트 핸들러로 전파 — §5). `uvicorn main:app` 으로 띄우면
  host/port/reload 는 CLI 옵션이 정합니다(`DEBUG=true` 가 CLI 에 reload 를 켜 주지 않습니다).
- `--lifespan off` 는 Redis 검증과 자원 정리를 건너뛰므로 지원하는 실행 방식이 아닙니다.
- reload 나 여러 worker 는 프로세스마다 import·lifespan 을 다시 수행합니다. Redis client 와 DB
  풀은 worker 마다 따로 있고, Celery 는 별도 프로세스입니다.
- 엔진 생성은 URL·풀 정책 준비일 뿐입니다. 실제 접속은 DDL, `/ready`, 세션의 첫 쿼리에서
  일어납니다.

---

## 4. 설정 (`config.py`)

### 4.1 값이 정해지는 방식

- 각 `BaseSettings` 클래스가 `env_file=".env"`, `extra="ignore"` 로 자기 필드를 직접 읽습니다.
  우선순위는 **프로세스 환경변수 → 현재 작업 디렉터리의 `.env` → 필드 기본값** 입니다.
- `.env` 는 작업 디렉터리 기준이라 저장소 루트에서 실행합니다. `.env.example` 은 복사용일 뿐
  자동으로 읽히지 않습니다. `.env` 가 없어도 기본값으로 뜨지만, 기본 주소의 Redis·MySQL 이
  준비됐다는 뜻은 아닙니다.
- 리스트는 JSON 배열로 씁니다: `CORS_ALLOW_ORIGINS=["http://localhost:3000"]`.
- `get_*_settings()` 는 `@lru_cache` 이고, 파일 끝의 `app_settings = get_app_settings()` 등이
  import 시 전역 인스턴스를 만듭니다. 실행 중 `.env` 를 바꿔도 반영되지 않습니다. 테스트에서
  캐시만 비워도 이미 가져간 전역 참조는 바뀌지 않으므로 새 프로세스나 monkeypatch 로 확인합니다.
- 타입 오류·validator 위반은 config import 를 실패시켜 lifespan 전에 기동을 막습니다.

### 4.2 클래스별 소비 지점

| 전역 인스턴스 | 쓰는 곳 |
|---|---|
| `timezone_settings` | 로그 시각(지역), 모델 시각 기본값(`utc_now()`, UTC), 리포트 영업일 경계(`local_dates_to_utc`·`utc_offset`), Celery beat timezone |
| `app_settings` | 앱 메타데이터, `DEBUG`/`ENV`/`ADMIN_DISABLED`, 직접 실행 host/port |
| `db_settings` | 엔진 URL·라우팅·풀, Alembic URL(`ALEMBIC_URL`), `describe_routing()`(DSN 마스킹) |
| `cors_settings` | `CustomCORSMiddleware.configure_cors()` |
| `log_settings` | `build_dictconfig()`(형식·레벨·헤더별 레벨·파일·회전·보관), `console_enabled()`(콘솔 on/off) — 모든 실행 경로 공통 |
| `middleware_settings` | `UserInfoMiddleware` (활성·제외 규칙·민감 query 키), `ClientIPResolver`(`TRUSTED_PROXY_HOPS`) |
| `redis_settings` | startup Redis ping client, Celery broker/backend |
| `jwt_settings` | `TokenService`(서명·검증·수명·iss/aud·leeway), 로그인·가입 rate limit(`AUTH_*`) |
| `session_settings` | `SESSION_SECRET_KEY` 는 `/admin` 관리 세션의 Redis 키 HMAC 키이고(`get_admin_session_store`) 배포 게이트가 검사한다. `ADMIN_SESSION_MAX_AGE_SECONDS`·`ADMIN_SESSION_IDLE_SECONDS` 가 관리 세션의 절대·미사용 만료다(기본값은 README [세션·토큰 만료](../../README.md#세션토큰-만료)). `UserInfoMiddleware` 는 `SESSION_COOKIE_NAME` 쿠키를 session_id 로 **기록만** 한다. API 인증에 쓰는 쿠키 세션은 없다(§10.3) |

설정 클래스가 있다고 기능이 있는 것은 아닙니다. API 쿠키 세션·Redis 캐시는
구현돼 있지 않습니다. URL 버전은 설정이 아니라 각 앱 router 의 `/v1/...` 선언이 정합니다
(`API_VERSION` 설정은 config-cleanup 2차에서 지웠고, `.env` 에 남은 줄은 무시됩니다).

### 4.3 검증

| 검증 | 거부하는 것 |
|---|---|
| `DatabaseSettings._validate_routing()` | 복제 활성인데 라우터가 꺼짐 / replica 목록이 빔 / 잘못된 replica host 표기 |
| `CORSSettings._reject_wildcard_with_credentials()` | 와일드카드 Origin + credentials |
| `LogSettings._format_renders()` / `_app_levels_parse()` / `_date_format_not_blank()` | 렌더할 수 없거나 필수 자리표시자가 빠진 `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT` / 해석할 수 없는 `LOG_APP_LEVELS` / 빈 `LOG_DATE_FORMAT` |
| `SessionSettings._idle_within_max_age()` | `ADMIN_SESSION_IDLE_SECONDS` 가 `ADMIN_SESSION_MAX_AGE_SECONDS` 보다 김 |
| `validate_env_source()` | `.env` 가 없으면 필수 값이 환경 변수로 와야 함(아래) |
| `validate_renamed_settings()` | 이름이 바뀐 옛 설정(`ADMIN`)이 남아 있음(아래) |
| `validate_deployment_safety()` | 아래 배포 게이트 |

**설정 검사.** `config.py` import 마지막에 세 검사가 차례로 실행되고, 위반은 `RuntimeError` 로 기동을
막습니다(메시지에는 설정 이름만, 값은 담지 않습니다). `ENV=test` 는 셋 다 건너뜁니다(pytest 가 지정).

1. `validate_env_source()` — **출처.** `.env` 가 없으면 `REQUIRED_WITHOUT_ENV_FILE`(`ENV`·비밀 키 3종·
   `MYSQL_HOST/USER/PASSWORD/DATABASE`)이 환경 변수로 모두 있어야 합니다. 컨테이너 주입은 통과합니다.
2. `validate_renamed_settings()` — **이름이 바뀐 설정.** 예전 `ADMIN`(true=켬)은 `ADMIN_DISABLED`
   (true=끔)로 바뀌었습니다. `.env`·환경 변수에 `ADMIN` 이 남아 있으면 Settings 가 조용히 버리고(extra
   "ignore") 관리 화면이 **켜지므로** 기동을 멈춥니다(test 제외).
3. `validate_deployment_safety()` — **내용.** 위반을 **한 번에 모아** 알립니다.

test 외 **모든 ENV**(개발 환경 포함 — 기본값·예시 값 그대로는 `.env` 를 채우라는 신호):

- placeholder 인 `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` —
  `is_placeholder_secret()` 가 판정한다: 앞뒤 공백 제거·소문자화 후 `change-this` 를 포함하거나 `your-` 로 시작하거나 빈 값.
  옛 예시 파일의 `your-...-change-this` 형식도 여기에 걸린다. 32자 미만도 위반
- access/refresh 서명 키가 같음
- placeholder 인 `MYSQL_PASSWORD` — 같은 `is_placeholder_secret()` 판정이고, **빈 값도 위반**이다
  (무인증 DB 계정). `REDIS_PASSWORD` 는 빈 값이 정당한 구성(인증 없는 사설망 Redis)이라
  **값이 있을 때만** 본다

staging/production 만:

- `DEBUG=true`
- `CORS_ALLOW_ORIGINS` 에 `*`
- `LOG_SQL_ECHO_ENABLED=true`
- `LOG_LEVEL=DEBUG` — 롤백 상세(SQL 본문)는 DEBUG 레코드로만 나갑니다(§8.2). 바인드 값은 모든 엔진의
  `hide_parameters=True` 가 예외 문자열·SQLAlchemy 로그에서 이미 뺍니다(§8.1).
  `DEBUG` 와 달리 `LOG_LEVEL` 은 단독으로도 유효 레벨을 DEBUG 로 올립니다

관리 화면을 켠 배포(`ADMIN_DISABLED=false`)는 위반이 아닙니다 — `/admin` 은 슈퍼유저 로그인이 필요합니다
(§10.3). `development`/`test` 는 편의 기본값(`DEBUG=true`, 관리 화면 켬)을 그대로 둡니다. 회귀 가드:
`tests/core/test_deployment_safety.py`, 설정과 `.env.example` 의 동기화는
`tests/core/test_settings_contract.py`.

---

## 5. 로깅

키 표·파일 목록·Django `LOGGING` 대응표·다중 워커 주의·업그레이드 노트는 README [로깅](../../README.md#로깅) 이 정본입니다.
여기는 구조만 적습니다.

- **설정 한 곳.** `app/utils/logs/config.py` 의 `build_dictconfig()` 가 Django `settings.LOGGING` 자리이고, 첫
  `get_logger()` 가 `configure_logging()` 으로 한 번 적용합니다. 핸들러는 **root 에만** 붙고 `loggers` 키는 없습니다.
- **모든 실행 경로가 root 의 핸들러 한 벌을 씁니다.** 앱 로거는 root 로 전파합니다. `python main.py` 는 uvicorn 에
  `log_config=None` 을 넘겨 uvicorn 로거도 root 로 갑니다. `uvicorn main:app`·`fastapi dev` 는 앱 import 전에 붙인
  자기 핸들러를 `configure_logging()` 이 걷어 내고(`setup.adopt_external_handlers()`) root 로 보냅니다. Celery 워커는
  `after_setup_logger` 수신자(`app/celery/worker_lifecycle.py`)가 프로세스를 `celery` 로 정하고 root 를 다시 구성합니다
  (`setup.configure_worker_logging()` — `--logfile` 은 같은 파일 형식의 핸들러로 유지). 태스크 로거(`celery.task`)는
  `after_setup_task_logger` 에서 자기 핸들러를 걷고 root 로 전파합니다. 그래서 형식·헤더·마스킹·헤더별 레벨이 경로마다 같습니다.
- **형식.** 포매터는 `TzFormatter` 하나(`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`, development 는 `.밀리초`,
  staging/production 은 UTC)입니다. 설정 로드 때 샘플 레코드를 렌더해 형식 오류를 막고, 필수 자리표시자
  (`{asctime}`·`{levelname}`·`{appname}`·`{module}`·`{classname}`·`{funcName}`·`{message}`)가 빠지면 빠진 목록과 함께 기동 오류입니다.
  uvicorn 접속 줄은 `{message}` 가 요청 줄입니다(전용 포매터 없음 — 예전 `TzAccessFormatter` 는 args 를 풀다 줄을 잃는 위험만 있었다).
- **헤더(`app=`).** 판별은 `filters._app_from_path(pathname, name)` 한 함수입니다. 우리 코드는 소스 경로(기능명·`core`·`celery`·
  `utils`·`migrations`·`app`), 설치된 라이브러리는 로거 이름 표(`celery`/`kombu`→`celery`, `uvicorn`, `sqlalchemy`, `alembic`, 그 밖 `ext`).
  새 기능은 등록 없이 기능명 헤더가 붙습니다.
- **필터 순서.** 콘솔·Celery `--logfile` 핸들러: `ContextFilter`(헤더·클래스명) → `AppLevelFilter`(`LOG_APP_LEVELS`, 지정 없는
  헤더는 `LOG_LEVEL`) → `RedactingFilter` → `SQLNoiseFilter`. 파일 경로는 둘로 나뉩니다 — 큐 핸들러가 `ContextFilter` →
  `AppLevelFilter` → `SQLNoiseFilter` 로 큐 앞에서 거르고, listener 뒤의 두 파일 핸들러가 `ContextFilter` → `RedactingFilter` 로
  가립니다. 마스킹은 모든 출력처에 걸리지만 파일 쪽은 큐 뒤에서 합니다. root 레벨은 `LOG_LEVEL` 과 헤더별 레벨 중 최솟값으로 내려 레코드가 필터까지 옵니다.
  콘솔·파일 핸들러 레벨(`LOG_CONSOLE_LEVEL`·`LOG_FILE_LEVEL`)은 출력처 하한으로 그대로 적용됩니다.
- **파일.** staging/production + `LOG_FILE_ENABLED=true` 에서만. 이름은 프로세스 종류가 정합니다(`LOG_FILES`: 웹 `app.log`·`error.log`,
  Celery `celery.log`·`celery-error.log`). 종류는 import 때 진입점(argv — `celery` CLI·`python -m celery` 면 celery)으로 정하고
  Celery 로깅 신호가 한 번 더 확정합니다 — 설정 로드 직후의 기동 초기 줄도 그 프로세스의 파일에 남습니다(integration-e2e F-006). 핸들러 `handlers.DailyRotatingFileHandler` 가 UTC 자정·하루 안 크기 초과 때 교체하고
  교체 시점에 `LOG_RETENTION_DAYS` 보다 오래된 날짜·분할 파일을 지웁니다. 파일 핸들러는 bounded queue 뒤 listener 스레드가 씁니다
  (이벤트 루프가 파일 I/O 로 멈추지 않게). prefork 자식은 listener 스레드를 물려받지 못하므로 `worker_process_init` 에서 다시 세웁니다
  (`queue_logging.restart_queue_listener_after_fork()`, 같은 프로세스면 아무것도 하지 않음). 한 파일은 한 프로세스가 쓴다는 전제라
  여러 워커는 파일 로그를 끄고 stdout 을 수집합니다 — uvicorn 이 spawn 한 워커에서 파일이 켜져 있으면 기동 시 WARNING 한 줄.
- **콘솔 on/off.** `LOG_CONSOLE_ENABLED=false` 면 root 에 콘솔 핸들러가 없고(모든 경로가 root 를 쓰므로 전부 꺼짐), 파일도 없으면
  `configure_logging()` 이 stderr 에 경고 한 줄을 남깁니다.

**마스킹 범위.** 메시지·인자·예외 traceback(체인 `raise … from` 포함)·`stack_info` 에서 DSN 의 사용자명·비밀번호, `password=`/`token=`
형태 값, `Bearer <토큰>`, 그리고 설정된 비밀값 원문(`config.LOG_SECRET_SETTINGS` → `log_secret_values()` → `configure_logging()` 이
`filters.set_secret_values()` 로 설치)을 가립니다. 4글자 미만 값은 DSN·`user=`·`username=` 에서만 가립니다(일반 단어 보호).
필터가 `exc_info` 를 traceback 문자열로 미리 렌더해 `exc_text` 에 고정한 뒤 가리므로 포매터는 가린 본문을 찍고, 예외 타입·파일·줄은
남습니다. 비밀값이 인자 하나 안에 있으면 그 인자만 가려 args 모양을 지키고, 틀과 인자에 걸쳐 있으면(`password=%s`) 전개한 문자열을
가리고 args 를 비웁니다. 정규식 정본은 `filters.redact()` 하나입니다. 접속 로그 테이블의 `session_id` 쿠키·Referer·X-Forwarded-For
원문 저장은 로그 마스킹 대상이 아니며 그대로 유지합니다(사용자 결정 — §7.1).

**레벨.** 명시값이 `DEBUG` 기반 기본값보다 우선합니다. 레벨은 "최소 심각도" 입니다.

| DEBUG | LOG_LEVEL / LOG_CONSOLE_LEVEL | 콘솔에 나오는 것 |
|---|---|---|
| false | 미설정 / 미설정 | INFO 이상 |
| true | 미설정 / 미설정 | DEBUG 이상 |
| false | DEBUG / DEBUG | DEBUG 이상 (앱은 여전히 DEBUG=false 동작) |
| 무관 | INFO / DEBUG | INFO 이상 — 헤더별 레벨(`LOG_APP_LEVELS`)로 낮춘 헤더만 DEBUG |
| 무관 | DEBUG / INFO | INFO 이상 |

기동 로그의 `(DEBUG=%s)` 는 표시값일 뿐 출력 조건이 아닙니다. 기동 INFO 가 안 보이면 `LOG_LEVEL`·`LOG_CONSOLE_LEVEL`·
`LOG_APP_LEVELS` 를 먼저 봅니다.

```python
from app.utils.logs import get_logger

logger = get_logger(__name__)          # 헤더 app= 은 이름이 아니라 소스 경로가 정한다
logger.info("상품 생성: %s", product.id)
logger.exception("저장 실패")            # 스택 트레이스 포함
```

---

## 6. lifespan 과 자원 관리

`main.py` 의 lifespan 본문은 `async with manage_application_resources(app): yield` 한 줄이고,
자원 조립은 `app/core/resources.py` 가 합니다.

```text
app.state.resources = ResourceManager(); app.state.redis = None
register("logging-queue", 5s) · register("db-engines", 10s)
acquire("redis", start=ping+버전 확인, close=aclose, 5s)   ← 정리를 먼저 등록한 뒤 start
register("background-tasks", drain, 5s)
DEBUG=true → create_db_tables()                  ← 30초 guard
yield  (요청 처리 기간)
finally: resources.close(); app.state.redis = None; app.state.resources = None
```

**Redis 는 필수입니다.** `Redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)`
후 `ping()` 이 실패하면 오류 타입만 ERROR 로 남기고 다시 올려 서버 시작을 멈춥니다. `DEBUG` 와
무관하고 끄는 설정은 없습니다. 이어서 `check_redis_version()`(`app/core/redis.py`)이 `INFO server` 의
`redis_version` 을 상수 `REDIS_MIN_VERSION`(7.0)과 비교해 낮으면 `RedisVersionError` 로 멈춥니다 —
최소 버전은 코드가 보내는 명령에서 정했습니다(rate limit 의 `EXPIRE … NX` 7.0 > `GETDEL` 6.2 >
`SET … EX` 2.6.12). INFO 가 막힌 관리형 Redis(`ResponseError`)는 WARNING 후 계속하고, 연결 오류는
그대로 올립니다. fakeredis 는 INFO 를 지원하지 않아 테스트·로컬 스모크에서는 경고 경로를 탑니다.
성공해야 `app.state.redis` 에 client 가 들어갑니다. 기동 이후
상태는 `/ready` 가 호출마다 `PING`(2초 상한)으로 확인합니다(§9). 요청 쪽은 core provider
`get_redis`(`app/core/redis.py`) 하나를 `Depends` 로 받습니다 — client 가 없으면(기동 전·종료 후)
503 `SERVICE_UNAVAILABLE` 이고, 테스트는 `app.dependency_overrides[get_redis]` 로 가짜를 넣습니다.
요청 중 Redis 연결·시간 초과 오류(`redis.exceptions.ConnectionError`·`TimeoutError`)는 전역 핸들러
(`main._register_exception_handlers` 의 `redis_unavailable_handler`)가 503 `SERVICE_UNAVAILABLE` 로 끝냅니다 —
요청은 거부하고(fail-closed), traceback 은 그 핸들러가 한 번만 남기며, 정상 응답이라 keep-alive 연결도 유지됩니다.
(처리기가 없는 그 밖의 예외도 이제 연결을 끊지 않습니다 — §9 의 `answer_unhandled_exception`.) 관리 화면은 자기 세션
미들웨어가 같은 상황을 503 으로 끝냅니다.

**개발용 DDL.** `create_db_tables()` 는 writer 엔진에서 `Base.metadata.create_all` 을 실행합니다.
없는 테이블만 만들고(checkfirst) 컬럼 변경·삭제는 하지 않습니다. 모델 발견은 하지 않으며,
metadata 가 비어 있으면 `RuntimeError` 입니다. MySQL 데이터베이스와 계정 권한은 미리 있어야
합니다. 자동 생성과 Alembic 의 전환 시점은 README 의 스키마 관리 절이 정합니다.

**종료.** `ResourceManager.close()` 는 등록 역순(background tasks → Redis → DB engines → logging
queue)으로 정리합니다.

- 멱등입니다. 각 단계의 일반 예외·timeout 은 기록하고 다음 단계로 넘어갑니다.
- 단계 예산(5/5/10/5초)은 전체 20초 deadline 의 남은 시간으로 줄어들지만, deadline 을 다 쓰면 남은
  자원마다 1초 예비분을 주므로 **엄격한 20초 상한은 아닙니다**.
- `CancelledError` 는 잡지 않으므로 정리 중 외부 취소가 오면 뒤 단계가 실행되지 않을 수 있습니다.
- logging queue 를 멈춘 뒤의 마지막 로그는 파일에 남는다고 보장하지 않습니다. SIGKILL·강제
  종료에는 회수 보장이 없습니다.
- startup 실패도 같은 `finally` 경로로 정리합니다(아직 등록하지 않은 background drain 은 제외).

회귀 가드: `tests/test_lifespan.py`, `tests/core/test_resources.py`.

---

## 7. 요청 처리

```text
요청 → answer_unhandled_exception → UserInfoMiddleware → CORS → 라우터
     → Depends: 세션 generator → get_<name>_service(_readonly) → Service(session) → Repository
     → 쓰기 핸들러 본문이 await service.commit() → 응답 DTO
     → (예외면) 세션 generator 가 rollback 후 재전파 → 글로벌 예외 핸들러
     → UserInfoMiddleware 가 상태·소요시간을 붙여 접속 로그 저장 태스크 제출
```

미들웨어는 CORS → UserInfo → `answer_unhandled_exception` 순서로 등록되며, Starlette 는 나중에 등록한 것을
바깥에 둡니다.
계층별 책임과 트랜잭션 경계(커밋은 쓰기 핸들러 본문이 응답 전에 한 번)는
[기능 개발 가이드 §2·§8](./DEVELOPMENT.md)이 소유합니다.

### 7.1 접속 로그

core 의 `UserInfoMiddleware` 가 수집하고, home 앱의 `HomeAccessLogSink` 가 저장합니다. core 는
`AccessLogSink` Protocol 과 등록 슬롯(`set_access_log_sink()`)만 알고, 슬롯이 비어 있으면 저장을
건너뜁니다 — home 이 없어도 앱은 동작합니다.

1. `ACCESS_LOG_ENABLED=false` 이거나 경로가 `ACCESS_LOG_EXCLUDE_PATHS`, 확장자가
   `ACCESS_LOG_EXCLUDE_EXTENSIONS` 에 해당하면 그대로 통과시킵니다.
   기본 제외: `/health`·`/docs`·`/redoc`·`/openapi.json`·`/favicon.ico`,
   `.css .js .ico .png .jpg .jpeg .gif .svg`.
2. `call_next()` 가 응답을 돌려주면 상태 코드와 `response_time_ms` 를 붙여
   `access_log_tasks.spawn()` 으로 저장을 제출합니다. 응답은 기다리지 않습니다.
   처리되지 않은 예외는 **500 으로 기록한 뒤** 그대로 다시 던집니다(바깥의 `answer_unhandled_exception` 이 500 으로 응답, §9).
3. `BackgroundTaskRunner` 는 동시 256개 상한을 넘으면 새 로그를 **버리고** `dropped` 를 셉니다.
   종료 시에는 수락 중단 → 5초 대기 → 남은 태스크 cancel → 취소 완료까지 await 순서로 drain 합니다.
4. sink 는 `background_db_session()`(별도 풀)으로 `UserAccessLogService` 를 조립해 저장하고 명시
   commit 합니다. 요청 세션을 넘기지 않습니다. 저장 실패는 로그만 남기고 응답에 영향이 없습니다.
   서비스는 저장 직전에 문자열을 **모델 컬럼 길이로 자릅니다**(`String(n)` 의 n 을 모델에서
   읽는다 — 숫자를 두 번 적지 않는다). 긴 헤더·쿠키 하나 때문에 MySQL strict 모드가 그 요청의
   기록을 통째로 거부하지 않게 하려는 것입니다.

| 분류 | 필드 |
|---|---|
| 네트워크 | `ip_address`, `forwarded_for`(X-Forwarded-For 원문), `real_ip`(X-Real-IP 원문) |
| User-Agent | `user_agent`, `os_name`, `os_version`, `browser_name`, `browser_version`, `device_type`, `device_brand`, `device_model`, `is_bot` |
| 요청·응답 | `request_path`, `request_method`, `query_string`(민감 키 값은 `***`), `referer`, `accept_language`, `response_status`, `response_time_ms` |
| 식별 | `session_id`(`SESSION_COOKIE_NAME` 쿠키), `user_id`(인증된 요청의 주체 id — 응답 뒤에 `request.state.user_id` 에서 읽는다) |

`ip_address` 는 core 의 `ClientIPResolver` 가 `TRUSTED_PROXY_HOPS` 로 판정합니다(미들웨어 등록 시
설정에서 한 번 만들어 생성자로 주입). 기본 `0` 은 전달 헤더를 보지 않고 직접 연결 주소를 씁니다.
`N` 이면 X-Forwarded-For 의 **오른쪽에서 N번째** — 각 프록시가 오른쪽 끝에 덧붙이므로 우리 프록시가
붙인 값만 채택하고, 클라이언트가 왼쪽에 써 보낸 값은 보지 않습니다. XFF 가 없으면 X-Real-IP,
목록이 N 개보다 짧거나 값이 IP 가 아니면 직접 연결 주소입니다. `query_string` 은
`ACCESS_LOG_SENSITIVE_QUERY_KEYS`(기본 password·token·access_token·refresh_token·secret·api_key·code,
대소문자 무시)의 값을 `***` 로 가려 저장합니다. `user_id` 는 인증 의존성 `get_current_principal` 이 핸들러
실행 중에 `request.state.user_id` 로 남긴 값이라, 미들웨어는 **응답을 받은 뒤** 읽습니다(요청 전에 읽으면
항상 비어 있다). 익명 요청·토큰 검증 실패는 비어 있습니다. 조회 API(`/api/v1/home/access-logs*`)는
슈퍼유저 전용입니다. `user_access_logs` 는 `ip_address`·`created_at`·`device_type`·
`os_name`·`browser_name`·`session_id`·`user_id`·`country` 에 인덱스가 있습니다 — `country`·
`country_code`·`city` 컬럼은 선언과 인덱스만 있고 미들웨어가 값을 채우지 않습니다(위 표에 없는
이유).

**보존 기간.** `ACCESS_LOG_RETENTION_DAYS`(기본 365, `0` = 삭제 안 함, 음수는 설정 오류)보다 오래된 행은
home 의 `AccessLogRetentionService` 가 지웁니다 — 기준은 `created_at < 지금(UTC) − N일`(정확히 N일 전
행은 남는다)이고, 5,000행씩 id 를 골라 지운 뒤 **배치마다 커밋**합니다(긴 잠금·거대 트랜잭션 방지,
중간 실패는 다음 실행이 이어 지운다). MySQL 이 LIMIT 낀 `IN` 서브쿼리를 거부하므로 "id 선택 → id 로
DELETE" 두 단계로 두 DB 에서 같은 쿼리를 씁니다. 실행은 Celery beat 가 매일 03:30(`TIME_ZONE`)에
`home.purge_expired_access_logs` 를 발행합니다(§11). 원문 필드(`session_id`·`referer`·XFF)는 그대로
저장합니다(사용자 결정).

비핵심 로그라서 API 가용성을 로그 완전성보다 우선한 설계입니다. 무손실 감사 로그가 필요하면
내구 큐·재처리·중복 제거를 따로 설계해야 합니다. 개인정보 쪽 한계는 §10.4 를 봅니다.

---

## 8. DB 엔진·세션·라우팅 (`app/core/db/`)

### 8.1 엔진과 세션 팩토리

| 객체 | 용도 | 풀 |
|---|---|---|
| `engine` (= `writer_engine`) | 요청 writer, DDL, `/ready`, SQLAdmin | 20 + overflow 20, timeout 30s |
| `read_engines` | replica SELECT (복제 활성 시) | replica 마다 20 + 20 |
| `background_engine` | 접속 로그·Celery 등 요청 밖 쓰기 | 10 + 10, timeout 60s |

공통: `pool_recycle=280`, `pool_pre_ping=True`, 드라이버 `connect_timeout=10`, 그리고 정본 옵션
`ENGINE_SAFETY_OPTIONS`(`hide_parameters=True`) — DB 예외의 `str()`·SQLAlchemy 로그에 SQL 문은 남기되
바인드 값(이메일·해시·토큰)은 `[SQL parameters hidden due to hide_parameters=True]` 로 바꿉니다. 값은
키워드 꼴이 아니라 로그 마스킹(§5)으로는 지울 수 없어서 엔진에서 막습니다. Alembic(`migrations/env.py`)도
같은 옵션을 펼치고, 새 엔진 생성 지점이 빠뜨리면 `tests/core/test_hide_parameters.py` 가 실패합니다. 세션 팩토리
(`AsyncSessionLocal`, `BackgroundSessionLocal`)는 `expire_on_commit=False`, `autoflush=False` 입니다.
최대 연결 수는 **(풀 + overflow) × 엔진 수(writer + replica) × API worker 수 + background 풀 ×
프로세스 수** 로 계산해 DB 연결 한도와 맞춥니다. 기동 시 `describe_routing()` 이 라우팅 구성을
비밀번호를 가린 채 한 줄 로그로 남깁니다.

`AsyncSession` 은 요청(또는 한 독립 작업) 하나의 트랜잭션 상태입니다. 전역으로 공유하지 않고,
같은 세션으로 `asyncio.gather` 를 돌리지 않습니다.

### 8.2 세션 Dependency

| 정식 이름 | 형태 | 용도 |
|---|---|---|
| `get_writer_db_session` | async generator | 쓰기. 첫 쿼리부터 writer 고정 |
| `get_read_only_db_session` | async generator | 조회. read-only 표시, 쓰기 시도는 `ReadOnlyRoutingError` |
| `get_routed_db_session` | async generator | 동적 라우팅(SELECT→reader, 쓰기 후 writer). 승인된 특수 경로 전용 — 기능 코드에서는 쓰지 않음 |
| `get_background_db_session` | async generator | background 풀 (요청 밖, generator 형태) |
| `background_db_session()` | async context manager | 요청 밖 트랜잭션의 권장 형태 |

- 모든 generator 는 `async with` 로 세션을 열고 끝나면 닫습니다. 예외로 빠져나가도 `close()` 가
  활성 트랜잭션을 ROLLBACK 한 뒤 예외가 그대로 올라갑니다 — 명시적으로 예외를 잡는 것은 로그를
  남기는 `get_routed_db_session`·`get_background_db_session` 둘뿐입니다. context manager
  `background_db_session()` 도 `except` 에서 rollback 한 뒤 다시 던집니다(로그 없음).
  **성공 시 자동 commit 하지 않습니다.**
- FastAPI `Depends` 는 요청 안에서만 해석됩니다. 요청 밖에서는 `async with background_db_session()
  as session:` 으로 열고 Service 를 직접 조립합니다. Repository 는 세션이 어디서 왔는지 모릅니다.
- `session.py` 끝의 옛 별칭은 같은 객체를 가리키는 호환용입니다. 문서와 신규 코드는 정식 이름만
  씁니다(대응표: `scripts/review_gate.py` 의 `DEPRECATED_SESSION_ALIASES`, 게이트가 문서에서 옛
  이름을 거부합니다).
- 같은 요청에서 같은 Dependency 는 FastAPI 캐시로 재사용되지만, writer/read-only getter 는 서로 다른
  callable 이라 같은 세션이 아닙니다.

### 8.3 읽기/쓰기 라우팅 (`DB_ROUTER_ENABLED`)

기본값 `false` — 모든 세션이 writer 엔진 하나에 붙습니다. `DB_ROUTER_ENABLED=true` 이고
`DB_REPLICATION_ENABLED=true` + `MYSQL_REPLICA_HOSTS` 가 있으면 라우팅 세션이 다음을 따릅니다.

1. ORM flush·Core DML·ORM 잠금 조회(`select(...).with_for_update()`) → writer
2. 그 밖의 SELECT → reader (라운드로빈). 한 세션이 고른 reader 는 세션 끝까지 유지(pin)
3. `DB_READ_STICKY_AFTER_WRITE=true`(기본) 면 쓰기 뒤 같은 세션의 SELECT → writer
4. reader 가 없으면 writer
5. `text()` Raw SQL 은 **1~3 규칙만** 따릅니다 — 라우터는 문자열을 해석하지 않으므로
   `text("SELECT ... FOR UPDATE")` 는 reader 로 나갈 수 있습니다. Raw SQL 로 잠금이 필요하면
   `get_writer_db_session` 을 쓰거나 `using_writer(session)` 으로 직접 고정합니다(§8.2, 개발 가이드 §7)

복제 지연을 허용할 수 없는 읽기는 writer 세션을 쓰거나 `using_writer(session)` 으로 고정합니다.
sticky 는 세션 내부 정책이라 다음 요청의 read-only 세션까지 지연을 없애지 않습니다.

**replica 장애 대체(integration-e2e F-005).** read-only 세션(`get_read_only_db_session`)의 읽기가 replica 에서
연결 계열 오류(접속 불가 2002·2003·2005, 끊김 2006·2013·2055, 서버 종료·오프라인 1053·3032, 연결 수 초과 1040,
또는 SQLAlchemy 의 `connection_invalidated`)로 실패하면, 그 세션을 롤백하고 writer 에 고정한 뒤 **같은 구문을 한 번**
primary 로 다시 실행하고 WARNING(`replica 연결 오류(...) — 이 읽기를 primary 로 한 번 다시 실행합니다`, 비밀값 없음)을
남깁니다. 실행 지점은 `RoutingSession._execute_internal`(`execute`·`scalars`·`get` 이 모두 지난다)입니다.
쓰기·routed 세션, 이미 writer 에 고정된 세션, 문법·제약·잠금 오류, 복제 지연(오류가 아니다), 라우터가 꺼진 구성은
바뀌지 않습니다. `/ready` 는 replica 를 보지 않습니다(writer·Redis 만).

**read-only 집행**은 라우터가 꺼져 있어도 적용됩니다. 세션 클래스 이벤트(`before_flush`,
`do_orm_execute`)가 read-only 세션에서 ORM flush 와, 읽기로 판별되지 않는 구문을 거부합니다.
판별은 괄호 깊이 0 의 단어만 훑습니다 — 읽기 전용 CTE(`WITH ... SELECT`)는 통과하고, 최상위에
쓰기 키워드가 있는 문장(`WITH ... UPDATE`·`DELETE` 포함)·잠금 조회·multi-statement·따옴표나
괄호가 맞지 않아 판별할 수 없는 문장은 거부합니다. `session.info` 표시는 보안 경계가 아니므로 운영에서는
read-only DB 계정·권한을 최종 방어선으로 둡니다. 회귀 가드: `tests/core/test_read_only_guard.py`,
`tests/core/test_db_router.py`.

### 8.4 시각 저장 — UTC·마이크로초

DB 의 시각은 **UTC** 로 저장합니다. `Base.type_annotation_map` 이 `Mapped[datetime]` 을
`app/core/models/types.py` 의 `UTCDateTime` 으로 바꿉니다 — aware 값은 UTC 로 변환해 저장하고, naive 값은
`ValueError`(flush 시 `StatementError`)로 거부하며, 읽을 때 UTC tzinfo 를 붙입니다. MySQL 컬럼은
`DATETIME(6)`(마이크로초)입니다. 모델 기본값은 `timezone_settings.utc_now()` 하나에서 나오고, 응답 JSON 은
`...Z` 오프셋을 가집니다. `TIME_ZONE` 은 저장값의 의미를 바꾸지 않습니다 — 로그 표시·리포트 영업일·Celery
beat 표시에만 쓰입니다. 리포트는 지역 날짜 범위를 UTC 반열린 구간으로 바꿔 조회하고
`DATE(CONVERT_TZ(created_at, '+00:00', <오프셋>))` 로 묶습니다(쿼리당 고정 오프셋 — DST 지역은 행별 변환이
필요합니다). 회귀 가드: `tests/core/test_utc_datetime.py`, MySQL 은 `tests/integration/test_mysql_utc_datetime.py`.

---

## 9. 오류 응답과 health / ready

글로벌 핸들러 5종이 모든 오류를 `ErrorResponse{error_code, message, detail}` 로 바꿉니다.

| 예외 | 응답 |
|---|---|
| `AppException` 계열 (`NotFoundException`, `DuplicateException`, `ValidationException`, `DatabaseException`, 기능 예외) | 예외가 정한 상태 코드·`error_code`·`detail`. 예외의 `headers` 를 싣는다(401 `WWW-Authenticate: Bearer`·429 `Retry-After`) |
| `RequestValidationError` | 422, `detail` 에 `field`·`message`·`type` 목록. OpenAPI 도 모든 operation 의 422 를 이 형식(`ErrorResponse`)으로 광고한다 — FastAPI 기본 `HTTPValidationError` 는 `main.py` 의 문서 후처리가 바꾼다 |
| Starlette `HTTPException` | 해당 상태, `error_code=HTTP_<status>`. 예외의 `headers` 를 그대로 싣는다(405 `Allow`·401 `WWW-Authenticate` 등) |
| `redis.exceptions.ConnectionError`·`TimeoutError` | 503 `SERVICE_UNAVAILABLE`(fail-closed). traceback 은 `[RedisUnavailable]` 한 번, keep-alive 유지(§6) |
| 그 밖의 `Exception` | 500 `INTERNAL_SERVER_ERROR`, 고정 메시지, `detail=null` — **DEBUG 여부와 무관**. 가장 바깥 사용자 미들웨어 `answer_unhandled_exception`(`main.py`, 가장 나중에 등록)이 이 처리기로 응답을 끝내 traceback 은 `[UnhandledException]` 한 번, keep-alive 연결은 유지된다(Starlette `ServerErrorMiddleware` 까지 가면 응답 뒤 예외를 다시 던져 uvicorn 이 한 번 더 남기고 연결을 닫는다). `DEBUG=true` 면 지금처럼 다시 던진다. 관리 화면(sqladmin 하위 앱)은 자기 `ServerErrorMiddleware` 가 먼저 응답하므로 해당하지 않는다 |

500 의 예외 타입·route template·스택은 로그에만 남습니다(경로에 박힌 식별자 대신 template).
Repository 의 DB 오류 변환(`DBErrorTranslator` — MySQL 오류 코드·SQLite 메시지로 중복 409·필수 값
422·참조 없음 422·참조 중 409·그 외 500)도 드라이버 원문을 응답에 싣지 않습니다. `AppException` 은
상태 코드 500 이상만 ERROR(`detail` 포함)로, 4xx 는 WARNING 으로 남기고 4xx 의 `detail`(클라이언트가
보낸 값)은 로그에 싣지 않습니다. 경로는 route template 입니다. 회귀 가드:
`tests/test_exception_handler_leak.py`, `tests/core/test_db_error_translator.py`.

| 경로 / 지점 | 의미 | 결과 |
|---|---|---|
| `GET /health` | 프로세스 생존·버전 (DB·Redis 검사 없음) | `{"status":"healthy","version":...}` |
| `GET /ready` | writer 로 `SELECT 1` 과 Redis `PING` 을 동시에, 각 2초 guard | 둘 다 성공 `status="ready"`, 하나라도 실패 503 `NOT_READY` (예외 메시지·DSN 없음, 로그는 대상과 예외 타입만) |
| `/docs`, `/openapi.json` | `DEBUG=true` 일 때만 | 아니면 404 |
| 설정·registry 오류 | lifespan 이전 조립 실패 | 프로세스 기동 실패 |
| Redis ping·개발 DDL 실패 | startup 실패 | 등록된 자원 정리 후 중단 |
| 커밋 실패 | 쓰기 핸들러 안에서 예외 | 성공 응답 전에 오류 응답 |
| 접속 로그 포화·저장 실패 | 응답과 분리 | 로그 경고, `dropped` 증가 |

`/health` 만으로 DB·Redis 준비를 판단하지 않습니다. 오케스트레이터의 readiness 는 `/ready` 에
겁니다 — DB 와 Redis 를 모두 봅니다.

---

## 10. 인증과 보안 경계

### 10.1 JWT (`auth` 앱, `app/core/security/`)

역할마다 클래스 하나이고, 협력 객체는 생성자로 받습니다. 여러 기능이 함께 쓰는 provider
(해시기·토큰·refresh 저장소·소유권·인증 주체)는 core `app/core/security/dependencies.py` 에, auth 전용
provider(rate limit·`AuthService`)는 auth 의 `dependencies/auth_dependencies.py` 에 있습니다 — user 기능도
해시기·refresh 저장소를 쓰므로 auth 를 import 하지 않도록 core 로 올렸습니다(기능끼리 import 금지).

| 클래스 | 위치 | 역할 | provider |
|---|---|---|---|
| `PasswordHasher` | `app/core/security/password_hasher.py` | Argon2 해시, 옛 bcrypt 해시 검증·재해시 (가입·사용자 생성·운영 스크립트 공유) | `get_password_hasher`(core, 프로세스 단일) |
| `TokenService` | `app/core/security/tokens.py` | JWT 발급·검증 — 검증 규칙의 유일한 정의 지점 | `get_token_service`(core) |
| `RefreshTokenStore` | `app/core/security/refresh_store.py` | refresh jti 기록·소비(`GETDEL`)·family 폐기 | `get_refresh_token_store`(core, `get_redis`) |
| `RateLimiter` | `app/core/security/rate_limiter.py` | Redis 고정 창(`INCR` + 첫 hit `EXPIRE NX`, MULTI) | `get_rate_limiter`(`get_redis`) |
| `AuthService` | `app/features/auth/services/auth_service.py` | register · authenticate · issue_tokens · rotate · logout | `get_auth_service` |

- OAuth2 password flow + JWT access/refresh(PyJWT). 자격증명은 `User.hashed_password` 에 있고
  `auth` 는 인증 로직만 갖습니다(모델 없는 앱).
- **claims:** `sub, type, iat, nbf, exp, jti, iss, aud` + access 는 `username`·`su`(발급 시점의 슈퍼유저 여부,
  bool 이 아니면 거부), refresh 는 `fam`(로그인 세션 = family id). 검증은 허용 알고리즘 목록(설정 하나)·`audience`·`issuer`·`leeway`·필수 claim 을 모두
  지정하고, `type` 이 다르면 거부합니다. access 와 refresh 는 서로 다른 키로 서명합니다. 실패 이유와
  관계없이 `InvalidTokenException`(401 `AUTH_INVALID_TOKEN`, core) 하나로 응답합니다.
- **refresh 회전·재사용 탐지:** 발급할 때 `auth:rt:{jti}` → `{fam, sub}`(TTL = refresh 만료)와
  `auth:user:{sub}:fams` 를 기록합니다. `/refresh` 는 jti 를 `GETDEL` 로 소비하고 같은 family 로 새 쌍을
  발급합니다. 소비된 jti 가 다시 오면 재사용으로 보고 family 를 폐기(`auth:fam:{fam}:revoked`)한 뒤
  401 — 그 사이 정상 회전으로 받은 토큰도 함께 죽습니다. 사용자가 없거나 비활성이어도 family 를
  폐기합니다. `/logout` 은 family 를 폐기하고 이미 쓴 토큰이어도 204 입니다. `revoke_user(sub)` 는
  사용자의 모든 family 를 폐기합니다.
- **rate limit:** 라우트 의존성 `login_rate_limit`(IP, IP+소문자 사용자명)·`register_rate_limit`(IP)이
  핸들러 전에 셉니다. 초과는 `TooManyRequestsException`(429, `Retry-After`) — `AppException` 의
  `headers` 를 전역 핸들러가 응답에 싣습니다. 로그인 성공 시 IP+사용자명 카운터를 지웁니다.
  IP 는 접속 로그와 같은 `ClientIPResolver`(`TRUSTED_PROXY_HOPS`)로 판정합니다.
- **해시 이전:** 새 해시는 Argon2(pwdlib). `$2` 로 시작하는 옛 bcrypt 해시는 옛 규칙(UTF-8 72바이트
  절단)으로 검증하고, 맞으면 Argon2 해시로 바꿔 저장합니다 — `/login` 핸들러가 커밋합니다.
- `get_current_user`(auth)는 `get_current_principal` 이 검증한 주체로 read-only 세션에서 활성 사용자를
  읽습니다 — 엔티티가 필요한 `/me` 만 씁니다. 이 조회는 replica 가 아니라 **primary** 로 갑니다(`using_writer`,
  e2e-policy-2 결정 5) — 복제 지연 때 유효한 토큰이 401 이 되지 않고, 비활성화·삭제가 바로 반영됩니다. 나머지
  read-only 조회의 라우팅은 그대로입니다. 이 객체를 쓰기 세션에서 직접 수정하지 말고, 쓰기 세션으로 다시 조회합니다.
- **상수 시간 인증:** 사용자가 없거나 해시가 없어도 Argon2 더미 해시로 검증을 수행해 응답 시간으로
  사용자명 존재를 알아내기 어렵게 합니다(네트워크 변동까지 없애지는 못합니다).
- **논블로킹 해싱:** 해시·검증은 `asyncio.to_thread` 로 이벤트 루프 밖에서 돕니다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | README [세션·토큰 만료](../../README.md#세션토큰-만료) 표 |
| `JWT_ALGORITHM` | HS256 (HS256/HS384/HS512 만 허용) |
| `JWT_ISSUER` / `JWT_AUDIENCE` | `fastapi-project-structure` / `fastapi-project-structure-api` |
| `JWT_LEEWAY_SECONDS` | 10 |
| `AUTH_LOGIN_MAX_ATTEMPTS` / `AUTH_LOGIN_IP_MAX_ATTEMPTS` / `AUTH_LOGIN_WINDOW_SECONDS` | 5 / 20 / 60 |
| `AUTH_REGISTER_MAX_ATTEMPTS` / `AUTH_REGISTER_WINDOW_SECONDS` | 5 / 3600 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` (placeholder — test 외 모든 ENV 에서 설정 검사가 거부, §4) |

### 10.2 인가 — 인증 주체 · 슈퍼유저 · 소유권 (`app/core/security/`)

권한은 **슈퍼유저/일반 2단계**입니다(`users.is_superuser`, 기본 false). 판정 부품은 core 에 하나씩
있고, 기능은 core 만 의존합니다.

| 부품 | 위치 | 역할 |
|---|---|---|
| `Principal` | `authorization.py` | 검증된 access 토큰의 주체(`id`, `username`, `is_superuser`) — frozen dataclass |
| `get_current_principal` / `CurrentPrincipal` | `dependencies.py` | Bearer access 토큰 → `TokenService.decode` → `Principal`. **DB 조회 없음.** 성공 시 `request.state.user_id` 를 남긴다(접속 로그가 응답 뒤에 읽는다). 실패 401 |
| `require_superuser` / `SuperuserPrincipal` | `dependencies.py` | 주체가 슈퍼유저가 아니면 403 `FORBIDDEN` |
| `OwnershipPolicy.ensure_can_modify(owner_id, principal)` | `authorization.py` | 소유자 또는 슈퍼유저만 통과, 아니면 403. `owner_id` 가 None(작성자 컬럼 도입 전의 행)이면 슈퍼유저만 |
| `Public` · `PublicWrite` · `LoginRequired` · `SuperuserRequired` | `access.py` | 뷰의 `dependencies=[...]` 에 넣는 접근 수준 선언. `Public`·`PublicWrite` 는 아무것도 하지 않는 표식 의존성(런타임 비용 없음), 나머지는 위 두 의존성 그대로 |
| `AccessPolicyGuard` | `access.py` | 앱 조립 직후(`main.py`, 라우터·헬스·Admin 결선 뒤) 모든 `APIRoute`(숨긴 경로·중첩 include 포함, 문서용 Starlette `Route`·`/admin` `Mount` 제외)의 의존성 트리를 재귀로 훑어 선언 없음·이중 선언·쓰기+`Public`·조회+`PublicWrite` 를 모으고, 하나라도 있으면 목록 전체를 담은 `AppContractError` 로 기동을 멈춘다. `require_superuser` 는 내부에서 `get_current_principal` 을 쓰므로 슈퍼유저 하나로 판정 |

- **무상태 판정:** 보호 라우트는 토큰만 봅니다. 비활성화·강등은 refresh family 폐기(`revoke_user`)와
  짧은 access 만료(기본 15분)로 반영됩니다 — 이미 발급된 access 토큰은 만료까지 남습니다.
- **소유권은 서비스가 판정합니다.** blog·sns·reply·user 서비스는 생성자로 `OwnershipPolicy` 를 받고,
  수정·삭제 메서드가 `principal` 을 인자로 받아 존재 확인(404) 뒤 판정합니다(403). user 단건 조회·
  수정은 사용자 자신이 소유자이며, 존재 확인 **전에** 판정해 남의 id 로 존재 여부를 떠볼 수 없습니다.
- **작성자는 서버가 채웁니다.** 생성 시 `author_id = principal.id`, `author = principal.username`.
  요청 본문의 `author` 는 무시되고 Update 스키마에는 없습니다. `author_id` 는 FK 없는 String(36)(인덱스)
  — 사용자를 지워도 글은 남습니다.
- **user 의 특권 필드:** `is_active`·`is_superuser` 는 슈퍼유저만 바꿉니다(본인이면 403
  `USER_PRIVILEGED_FIELD`). 비활성화·강등·삭제는 `RefreshTokenStore.revoke_user` 로 그 사용자의 모든
  refresh family 를 폐기합니다. 생성(`POST /users`)은 슈퍼유저 전용이고 비밀번호가 필수입니다.
- **첫 슈퍼유저:** API 에는 경로가 없습니다(가입은 항상 일반 사용자). `scripts/create_superuser.py` 가
  `background_db_session` + core `get_password_hasher` + `UserRepository` 로 만들거나 승격합니다
  (README "첫 관리자 만들기").
- **접근 수준의 정본은 뷰 선언이고, 기본 정책은 거부입니다.** 선언하지 않은 뷰는 열린 채 배포되는 대신
  서버가 뜨지 않습니다. 데코레이터 선언만으로는 "선언을 잊은 뷰" 를 막을 수 없어 기동 검사를 둡니다.
  함수를 감싸는 `@login_required` 식 데코레이터는 쓰지 않습니다 — FastAPI 는 뷰 시그니처로 주입·검증·
  OpenAPI 를 만들기 때문에 감싸면 셋이 함께 깨집니다. 핸들러 인자 `CurrentPrincipal`·`SuperuserPrincipal` 은
  선언으로 인정되므로 같은 수준을 데코레이터에 중복으로 적지 않습니다. 예시 정책이 의도대로인지는
  `tests/test_authorization.py` 의 `EXPECTED` 표(README 권한 표와 같은 내용)가 가드의 판정·OpenAPI
  `security` 표시와 대조해 고정합니다. 소유자 판정은 선언이 아니라 서비스 동작이라 같은 파일의 실요청
  테스트가 맡습니다.

### 10.3 SQLAdmin

- `/admin` 은 **활성 슈퍼유저 로그인**이 필요합니다(admin-login ADR-002). `create_admin_interface()` 가
  `AdminAuthBackend`(`app/features/auth/admin_auth.py`)를 주입합니다. 로그인은 API 로그인과 같은
  `verify_credentials`(Argon2·bcrypt 재해시·비활성 거부)를 쓰고, 슈퍼유저가 아니면 실패입니다. 실패
  사유는 구분하지 않습니다(400). 시도 수는 API 와 같은 `AUTH_LOGIN_*` 한도로 키를 따로 셉니다
  (`admin:rl:`, 초과 시 로그인 화면을 429 + `Retry-After` 로).
- 세션은 `/admin` 하위 앱에만 붙은 **Redis 서버 세션**입니다(`app/core/security/admin_session.py` —
  저장소 `AdminSessionStore`, ASGI 미들웨어 `RedisSessionMiddleware`). 쿠키 `admin_session`(`Path=/admin`,
  `SameSite=Strict`, HttpOnly, Max-Age=절대 만료, staging/production 은 Secure)에는 `secrets.token_urlsafe(32)`
  세션 ID 만 있고, 내용 `{"data", "user_id", "created_at"}` 은 Redis `admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, ID)}`
  에 있습니다(TTL = min(미사용, 절대 만료까지 남은 시간), 요청마다 갱신). 사용자별 인덱스
  `admin:user_sessions:{user_id}` 로 한 사용자의 세션을 한 번에 지웁니다. 로그인 성공은 세션을 비우고
  사용자 id·새 CSRF 토큰을 넣은 뒤 `rotate_session` 으로 **세션 ID 를 새로 발급하고 이전 키를 지웁니다**.
  로그아웃·`authenticate` 거부는 키를 지우고, 사용자 서비스의 비활성화·강등·삭제는 refresh 폐기와 같은
  지점에서 `AdminSessionStore.revoke_user` 를 부릅니다(`get_user_service` 가 주입, `ADMIN_DISABLED=true` 면
  `None`). 관리 화면에서 직접 고친 경우는 `UserAdmin` 의 커밋 전 훅 `on_model_change`(비활성화·슈퍼유저 해제·비밀번호
  해시 변경일 때만, 변경 전후 비교)·`on_model_delete` 가 `UserService` 와 같은 판정 `revocation_for`·폐기
  `revoke_user_access` 를 부릅니다(규칙 한 곳 — 관리 화면 경로 = API 경로). 비활성화·슈퍼유저 해제·비밀번호 해시
  변경·삭제면 관리 세션과 refresh 를 모두 끊습니다. Redis 폐기가 실패하면 예외로 커밋이 막혀 DB 변경이 남지 않습니다(fail-closed).
  `scripts/create_superuser.py --set-password` 로 기존 사용자의 비밀번호를 바꿀 때도 커밋 전에 같은
  `revoke_user_access` 로 관리 세션과 refresh 를 끊습니다 — Redis 에 닿지 못하면 종료 코드 2, 비밀번호는 그대로입니다.
  자기 강등은 지금 세션도 끊습니다. 매 요청 DB 확인도 유지합니다(이중 방어). Redis 오류는 503 입니다(fail-closed) — 쿠키 없는 첫 요청처럼 응답 직전에 새 세션을 저장하다 실패해도 같습니다.
- **세션은 관리 화면 전용입니다.** 메인 앱에는 세션 미들웨어가 없고, API 보호 경로는 Bearer
  토큰만 봅니다 — 관리 세션 쿠키로 API 를 호출해도 401 입니다. 회귀 가드: `tests/test_admin_login.py`
  의 세션 범위 테스트.
- 로그인 화면은 `app/templates/admin/sqladmin/login.html`(Bootstrap 5.3.8 CSS, SRI 고정, JS 없음)이
  sqladmin 기본 화면을 덮어씁니다(`templates_dir` 의 FileSystemLoader 가 먼저 찾는다).
- **CSRF**(synchronizer token, 세션에 하나): 템플릿 전역 함수 `csrf_token(request)`(`AdminAuthBackend.csrf_token`)
  가 세션에 `secrets.token_urlsafe(32)` 토큰을 둡니다. 로그인 폼은 hidden 필드로 싣고 `login()` 이 레이트
  리밋·자격 확인 **전에** `csrf_valid`(bytes `hmac.compare_digest`)로 비교합니다. 로그인 이후의 모든
  POST·PUT·PATCH·DELETE(생성·수정·삭제·일괄 삭제·가져오기·로그아웃)는 하위 앱의 `AdminCsrfMiddleware` 가
  헤더 `X-CSRF-Token` 또는 폼 필드 `csrf_token`(본문 버퍼링 후 receive 재생)을 같은 함수로 비교해 403 으로
  막습니다(로그인 POST 는 건너뜀 — 검사는 한 번). 버퍼링하는 폼 본문은 10 MiB 까지입니다 — `Content-Length` 로
  먼저, 없거나 거짓이면 읽는 도중 누적 크기로 판정해 넘으면 413, 1 MiB 를 넘는 필드(starlette 폼 파서 기본 상한)나
  깨진 폼은 400 입니다(e2e-policy-2 결정 7, 상한은 `admin_auth.py` 의 상수). 토큰은 `app/templates/admin/sqladmin/base.html`(원본
  `sqladmin_original/base.html` 상속, `head_tail` 블록만 추가)의 meta 와 인라인 스크립트가 폼 제출·XHR·fetch
  에 붙입니다. 로그아웃은 `_make_logout_post_only` 가 POST 전용으로 바꾸고(GET 405) 스크립트가 링크를
  POST 폼으로 바꿉니다. sqladmin 원본이 어긋나면 `test_packaged_templates_still_fit_the_base_override` 가 실패합니다.
- **목록 날짜 필터**: `created_at` 이 있는 모든 뷰가 core 의 `LocalDateFilter`(`app/core/admin_filters.py`)를
  씁니다. 입력 `YYYY-MM-DD` 를 `TIME_ZONE` 의 [자정, 다음 자정) 으로 보고 UTC aware 범위로 바꿔 질의합니다
  (같은 날 / 이후(포함) / 이전(미포함) / 기간 `YYYY-MM-DD~YYYY-MM-DD` — 시작일 00:00 ≤ t < 종료일 다음날 00:00,
  한쪽만 있으면 열린 구간, 역순·형식 오류는 필터 미적용). 전용 템플릿
  `sqladmin/filters/local_date_filter.html`(sqladmin 이 필터 객체의 `template` 을 include 한다)이 날짜 입력
  두 개를 한 값으로 합쳐 보내고, 빠른 선택(오늘·최근 7일·30일)은 기간 링크입니다. 기본 `OperationColumnFilter` 는 `UTCDateTime` 을 날짜로 보지
  못해 문자열을 바인딩하고 500 이 났습니다. 잘못된 입력은 필터 없이 목록을 보여 주고 WARNING 을 남깁니다.
- `ADMIN_DISABLED=true` 면 `/admin` 이 아예 없습니다(404). sqladmin·관리 세션 미들웨어·인증 백엔드를
  만들지 않고 OpenAPI·`/docs`·오류 응답·헤더·기동 로그 어디에도 관리 경로가 나오지 않습니다
  (`tests/test_admin_disabled.py`). 관리 화면을 쓰지 않는 배포는 끕니다.
- `User.hashed_password` 는 목록·상세·폼·내보내기 어디에도 나오지 않고, `User` 는 Admin 에서
  생성할 수 없습니다(비밀번호 없는 계정 방지). 구조 증거: `tests/core/test_admin_views.py`.
- 설계·흐름도·위협 모델·운영 절차 전체: [admin 인증 안내서](workflows/admin-authentication.html).

### 10.4 현재 한계 — 외부 공개 전에 결정할 것

| 항목 | 현재 상태 |
|---|---|
| 권한 모델 | 슈퍼유저/일반 2단계뿐이다(세분화된 역할·그룹 없음). 강등·비활성화는 access 만료(기본 15분)까지 반영이 늦다 |
| 작성자 | 작성자 컬럼 도입 전의 글(`author_id` NULL)은 슈퍼유저만 수정한다. `author` 표시 이름은 작성 시점의 username 이라 이름을 바꿔도 따라가지 않는다 |
| 참조 무결성 | `Reply.post_id` 는 FK 없는 문자열 — 게시글 존재 검증·삭제 전파 정책 없음 |
| 로그인 보호 | 고정 창 rate limit(창 경계에서 최대 2배 통과, API·`/admin` 공통). 계정 잠금은 없다 |
| 관리 세션 | Redis 서버 세션 — 로그아웃·강등·비활성화·삭제(API·관리 화면 모두)는 서버에서 즉시 폐기된다. Redis 장애 중에는 관리 화면이 503 이다. sqladmin 의 사용자 정의 `@action` 은 GET 이라 CSRF 검사 대상이 아니다(이 저장소에는 없다). 관리 화면에서 직접 편집한 강등은 다음 요청의 DB 확인으로 끊긴다 |
| 토큰 폐기 | refresh 는 family 단위로 폐기된다(재사용 탐지·로그아웃). access 토큰은 만료(기본 15분)까지 유효하다 |
| 접속 로그 개인정보 | `query_string` 은 민감 키 값만 가리고 나머지와 `referer`·`session_id` 쿠키는 원문 저장한다 — **사용자 결정으로 유지**(log-redaction-fixes ADR-003). 보존 기간은 `ACCESS_LOG_RETENTION_DAYS`(기본 365일, beat 가 매일 삭제 — §7.1). 조회 API 는 슈퍼유저 전용 |
| CORS | 기본 `CORS_ALLOW_ORIGINS=["*"]`, credentials false (staging/production 은 게이트가 `*` 를 거부) |

---

## 11. Celery (요청 밖 작업)

- `app/celery/app.py` 의 `celery_app` 은 `REDIS_URL` 을 broker/backend 로 씁니다. `include` 는 API 와
  같은 `AppRegistry` 발견 결과(`task_modules()`)로 만들고, 같은 경로로 모델도 등록합니다
  (`import_models()` — 태스크가 쓰는 모델의 relationship 이 다른 앱을 가리켜도 매퍼가 구성된다).
  `app/celery/` 는 기능을 import 하지 않습니다(`tests/core/test_celery_app.py` 의 AST 계약).
- 태스크는 기능 폴더의 선택 모듈 `app/features/<name>/tasks.py` 에
  `@celery_app.task(name="<app>.<action>")` 로 정의합니다(예: `home.aggregate_access_stats`).
  기능별 `worker/` 는 두지 않습니다.
- **앱을 지우면 그 앱의 태스크도 include 에서 빠집니다.** 고칠 중앙 목록이 없고 워커는 그대로
  뜹니다(큐에 남은 메시지는 §2.6).
- **include 모듈의 import 는 CI 가 검사합니다.** `tests/core/test_celery_app.py` 의
  `test_celery_include_modules_import_and_register_their_tasks` 가 워커 기동 때처럼 include 를 import 하고
  각 모듈이 태스크를 등록했는지 본다 — `tasks.py` 의 import 오류가 워커 기동이 아니라 CI 에서 드러난다.
- 태스크 본문의 서비스 조립은 그 기능의 provider 함수(세션을 받는 일반 함수, 예:
  `build_user_access_log_service(session)`)를 재사용합니다. 요청용 `Depends` provider 도 같은
  함수를 부르므로 조립 경로가 하나입니다.
- 동기 태스크 안에서 코루틴은 `app/celery/task.py` 의 `run_async(coro)` 로 실행합니다. 워커 프로세스마다
  영속 이벤트 루프 하나를 재사용해, 닫힌 루프에 묶인 async 풀 연결 문제를 피합니다(prefork 순차
  실행 전제 — 다른 pool 을 쓰면 재검증).
- `worker_lifecycle.register_worker_signals()` 가 prefork 자식 초기화에서 상속된 sync 풀을
  폐기(`dispose(close=False)`)하고 루프를 새로 만들며, 종료 시 루프를 닫습니다. async DB dispose 까지
  하지는 않습니다.
- API 기동은 worker/beat 를 띄우지 않고, API lifespan 이 워커 자원을 정리하지도 않습니다.
- `enable_utc=True` 입니다 — ETA·만료·결과 시각은 UTC 로 다루고, `timezone`(`TIME_ZONE`)은 beat crontab 해석·표시에만 쓰입니다.
- **beat 스케줄은 태스크를 가진 기능이 등록합니다.** 중앙 앱은 `beat_schedule={}` 만 두고, 기능의 `tasks.py` 가
  import 될 때 `celery_app.conf.beat_schedule["<app>.<action>"] = {...}` 로 자기 항목을 넣습니다(중앙 목록이
  기능을 import 하지 않는다 — include 와 같은 철학). beat 도 워커처럼 시작 시 include 를 import 하므로 이
  등록이 보입니다. 현재 항목: `home.purge_expired_access_logs` 매일 03:30(`crontab(hour=3, minute=30)`,
  `TIME_ZONE` 기준). 실행: `celery -A app.celery.app:celery_app beat`(배포 전체에서 하나만).
- 태스크에는 요청 세션·Service·Request 를 넘기지 않고 JSON 직렬화 가능한 id·값만 넘깁니다. 태스크가
  `background_db_session()` 을 열고 재시도·중복 정책을 스스로 정합니다.

---

## 12. Alembic

`migrations/env.py` 는 런타임과 **같은 발견 규칙**으로 모델을 모읍니다. 새 앱을 추가해도 이 파일은
고치지 않습니다. FastAPI lifespan 에 들어가지 않으므로 Redis ping 도 하지 않습니다.

```python
_registry = AppRegistry()
_registry.discover()
_registry.import_models()
target_metadata = Base.metadata
config.set_main_option(
    "sqlalchemy.url",
    db_settings.ALEMBIC_URL.render_as_string(hide_password=False).replace("%", "%%"),
)
```

- URL 우선순위(`DatabaseSettings.ALEMBIC_URL`, `URL` 객체): `ALEMBIC_DATABASE_URL` 설정값(`make_url`) →
  primary URL 의 드라이버만 `mysql+pymysql` 로 바꾼 값. `env.py` 는 환경변수를 직접 읽지 않습니다.
- DSN 은 문자열로 이어 붙이지 않고 `URL.create(...)` 로 만듭니다 — 비밀번호의 `@ / : #` 는 렌더링 때
  인코딩되고, `%` 는 ConfigParser 보간을 피하려고 `%%` 로 넘깁니다. 회귀 가드: `tests/core/test_dsn_urls.py`.
- revision 체인: `f4adf0ae24ea`(baseline) → `b2f1a9c0d3e4`(user 비밀번호) →
  `c3d5e7a91b02`(catalog_products) → `d4e6f8b12c34`(sales_orders) → `e5a7c9d1f3b5`(시각 컬럼 UTC·`DATETIME(6)`) →
  `a7c3e9f1b2d4`(슈퍼유저·작성자 id 컬럼, head).
- `e5a7c9d1f3b5` 는 MySQL 에서만 동작합니다(SQLite no-op). 기존 값을 `CONVERT_TZ(col, '+09:00', '+00:00')` 로
  옮기므로 **기존 데이터가 `+09:00`(Asia/Seoul 벽시계)으로 저장됐다는 가정**입니다 — 적용 전에 백업하고,
  다른 시간대로 운영하던 DB 는 적용 전에 리비전의 `_LOCAL_OFFSET` 상수를 그 오프셋으로 바꿔야 합니다(README
  운영 배포 확인 7). downgrade 는 역변환 후 `DATETIME` 으로 좁힙니다(소수 초 반올림).
- autogenerate 는 `UTCDateTime` 을 `sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")` 로 적습니다
  (`env.py` 의 `render_item=render_alembic_type`) — 리비전이 앱 클래스를 import 하지 않습니다.
- 서버 기동은 upgrade 를 하지 않습니다. 운영은 트래픽 전환 전에 `alembic upgrade head` 를 적용합니다.
- 회귀 가드: `tests/core/test_migration_chain.py`(빈 DB `upgrade head` 결과 = ORM metadata),
  `tests/core/test_alembic_metadata.py`, 게이트 `structure` 그룹(`alembic heads` 단일 head).

작성 절차는 [기능 개발 가이드 §10](./DEVELOPMENT.md), 자동 생성과의 전환은 README 를 봅니다.

---

## 13. 도구와 검증 게이트

| 명령 | 설명 |
|---|---|
| `uv sync` | 의존성 설치 (`[tool.uv] package = false` — 루트 패키지 빌드 없음) |
| `uv run python -m pytest` | 전체 테스트. pytest-env 가 `DEBUG=true`·`ENV=test` 를 주입, SQLite·가짜 Redis 사용 |
| `uv run python -m pytest -m mysql` | MySQL 8.4 통합(`tests/integration/`). `127.0.0.1:3310` 에 없으면 skip (`MYSQL_TEST_PORT` 로 변경) |
| `uv run python -m pytest -m e2e` | 전수 통합(`tests/e2e/`). `compose.e2e.yaml` 을 먼저 띄운다 — 실행법은 README "전수 통합(E2E)" |
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` | 정적 분석 |
| `uv run python -m scripts.review_gate [--group ...]` | CI 와 같은 판정. `--list` 로 그룹 확인 |

`pytest` 콘솔 스크립트 대신 `python -m pytest` 를 씁니다(다른 인터프리터를 집은 전례). 게이트 판정용
mypy 는 캐시 없이 돈 결과만 인정합니다.

| 게이트 그룹 | 내용 |
|---|---|
| `static` | ruff check · ruff format --check · mypy · bandit(`app`, `main.py`, `config.py`) |
| `tests` | 전체 pytest(skip·xfail·deselect 0 이어야 통과 — MySQL 필요, 커버리지 측정·출력) + collect-only |
| `structure` | `alembic heads` |
| `supply` | Action SHA 고정 · compose 이미지 digest · 비밀값 스캔 |
| `docs` | README·`docs/guides`·`docs/crp`·워크플로 주석이 가리키는 경로·환경변수 실재, 가르치는 문서의 옛 세션 별칭 금지 |
| `deps` | pip-audit (네트워크 필요) |

CI(`.github/workflows/ci.yml`)는 세 job 입니다: `gate` job 이 `static structure supply docs deps` 와
`pytest -m "not mysql"`(skip·xfail 0 확인)을, `mysql` job 이 `compose.test.yaml` 을 띄워
`pytest -m mysql` 과 `tests` 그룹을, `e2e` job 이 `compose.e2e.yaml` 을 띄워 `pytest -m e2e`(skip·xfail 이 있거나
0건이면 실패, 실패 시 산출물 업로드)를 돌립니다.

**전수 통합(`e2e` 마커).** `tests/e2e/` 는 `-m` 표현식에 `e2e` 가 있고 `not e2e` 가 아닐 때만 수집됩니다
(`tests/e2e/conftest.py` 의 `pytest_ignore_collect`) — 다른 실행에는 skip·deselect 를 남기지 않습니다. 하네스는
`compose.e2e.yaml`(MySQL primary + GTID replica, Redis) 위에서 Alembic upgrade → 슈퍼유저 생성 → uvicorn·Celery worker 를
실제로 띄우고, 접속 대상이 `127.0.0.1` 의 고정 포트가 아니면 시작하지 않습니다. 새 API 는
`tests/e2e/test_api_matrix.py` 의 `OPS` 에 한 줄을 더해야 `test_inventory.py` 의 대조를 통과합니다. 커버리지는 gate job 의 pytest 와 `tests` 그룹이
`--cov=app --cov-config=pyproject.toml --cov-report=term-missing` 으로 측정·출력하고, 하한은 `pyproject.toml` 의
`[tool.coverage.report] fail_under` 하나(기본 0 = 하한 없음 — 사용자 결정)가 정합니다.

---

## 14. 변경 이력

| 날짜 | 변경 내용 |
|---|---|
| 2026-10-21 | **docs-guide-review**: 가이드 검수 지적을 코드에 맞췄다 — 기동 도식(422 문서 후처리·`answer_unhandled_exception`·`AccessPolicyGuard`)·글로벌 핸들러 5종·미들웨어 순서·Settings 9종·설정 검사 3종·핸들러별 로그 필터·CI 세 job·e2e 마커(§1·§2·§3·§4·§5·§7·§8·§9·§10.3·§13). 코드 변경 없음. |
| 2026-10-21 | **e2e-policy-2**(사용자 결정): OpenAPI 의 422 를 실제 본문 `ErrorResponse` 로 광고(문서 후처리 한 곳), 처리기가 없는 예외를 가장 바깥 사용자 미들웨어 `answer_unhandled_exception` 이 500 으로 끝냄(traceback 한 번·keep-alive 유지, DEBUG 는 다시 던짐), `create_superuser --set-password` 도 refresh·관리 세션을 커밋 전에 폐기(Redis 불가면 종료 코드 2), `/me` 의 사용자 조회는 primary, 관리 CSRF 폼 버퍼링 상한(본문 10 MiB 초과 413, 필드 1 MiB 초과·깨진 폼 400). 모든 401 의 `WWW-Authenticate: Bearer`·관리 화면 Redis 장애 503 은 이미 충족 — 계약 테스트로 고정. 의존성: `cryptography` 를 `aiomysql[rsa]` 로 선언(`pymysql` 은 추가 옵션 없이). |
| 2026-10-20 | **integration-e2e**: 전수 통합 스위트(`tests/e2e/`, `compose.e2e.yaml` primary+GTID replica+Redis, CI job `e2e`). 고친 결함 — `pymysql[rsa]`(인증 캐시가 빈 MySQL 에 TLS 없이 붙을 때 RSA 필요, F-001), 401 의 `WWW-Authenticate: Bearer`(F-002), 상품 관리 폼의 서버 관리 열 제외(F-003). 사용자 결정 반영 — Redis 연결 장애 503(F-004), read-only 읽기의 replica 연결 오류 → primary 한 번 재시도(F-005), 프로세스 종류를 진입점으로 정해 Celery 기동 초기 줄도 `celery.log`(F-006). |
| 2026-10-19 | **logging-overhaul**: 모든 실행 경로(앱·`python main.py`·`uvicorn main:app`·Celery 메인·태스크)가 root 의 핸들러 한 벌로 같은 형식을 쓴다(`setup_uvicorn_logging()`·`TzAccessFormatter` 삭제). 헤더에 라이브러리 출처(`celery`·`uvicorn`·`sqlalchemy`·`alembic`), 형식 필수 필드 검사, 헤더별 레벨 `LOG_APP_LEVELS`, 프로세스별 파일(`app.log`·`error.log`/`celery.log`·`celery-error.log`), UTC 자정+크기 교체와 `LOG_RETENTION_DAYS`(예전 `LOG_BACKUP_COUNT`·`LOG_*_FILENAME` 삭제), DSN 사용자명·설정 비밀값 원문 마스킹(§5). |
| 2026-10-19 | **config-cleanup R-804**: `python main.py` 의 uvicorn 접속 줄이 매번 logging 오류로 사라지던 결함(포매터가 args 를 요청 라인 필드로 풀지 못함)을 `TzAccessFormatter` 로 고쳤다. `?token=` 처럼 비밀값이 든 요청은 두 경로(`python main.py`·`uvicorn main:app`) 모두 마스킹이 args 를 비워 같은 오류가 났다 — 이제 인자 단위로 가린다(§5). |
| 2026-10-19 | **config-cleanup 2차**: `API_VERSION`(`ApiSettings`)을 삭제했다(URL 버전은 router 의 `/v1/...`). `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT`·`LOG_CONSOLE_ENABLED` 를 로깅 구성에 연결했다 — 기본값은 기존 하드코딩 형식과 같고, 잘못된 형식은 기동 오류, 출력이 모두 꺼지면 stderr 경고(§5). 설정 사용 계약 테스트의 예외 목록을 없앴다. |
| 2026-10-19 | **config-cleanup**: 읽는 코드가 없던 `SMTP_*`(`SMTPSettings`)·`UPLOAD_*`(`UploadSettings`)·`SESSION_EXPIRE_SECONDS` 를 삭제했다(남은 `.env` 줄은 `extra="ignore"` 로 무시). 세션·토큰 만료의 정본은 README 표 하나다. 사용처 없는 설정 필드가 다시 생기지 않게 계약 테스트를 더했다. |
| 2026-10-19 | **admin-session-hardening**: 관리 세션을 서명 쿠키에서 Redis 서버 세션으로(세션 ID 회전·즉시 폐기·절대/미사용 만료, `ADMIN_SESSION_*`), 로그인 이후 모든 상태 변경 요청 CSRF·POST 로그아웃, 날짜 필터 기간 연산(§10.3·§10.4). `itsdangerous` 의존성 제거. |
| 2026-10-19 | **security-ops-hardening**: 모든 엔진에 `hide_parameters=True`(정본 `ENGINE_SAFETY_OPTIONS`, §8.1). 접속 로그 보존 기간 `ACCESS_LOG_RETENTION_DAYS` 와 beat 배치 삭제(§7.1·§11). 관리 로그인 폼 CSRF 토큰, 관리 목록 `created_at` 날짜 필터(§10.3). |
| 2026-10-13 | **log-redaction-fixes**: 로그 마스킹이 예외 traceback·체인·`stack_info`·`Bearer` 토큰까지 덮고 uvicorn CLI·Celery 워커 핸들러에도 붙는다(§5). Starlette `HTTPException` 의 헤더를 응답에 싣는다(§9). Redis 최소 버전 7.0 을 명령에서 도출해 기동 시 확인한다(§6). 커버리지 하한 기본 0(§13). |
| 2026-09-17 | **문서 일관성 정리**: 개발 가이드를 `DEVELOPMENT.md` 로 이름을 바꾸고, 재구성 때 지웠던 HTML 안내서 2종(`server-lifecycle-guide.html`·`feature-development-guide.html`)을 현행 코드·이 문서와 맞춰 복원했다(표·목록 원문은 Markdown 이 소유). 코드 변경: blog·reply·sns·user 쓰기 핸들러를 "DTO 검증 → commit" 순서로 맞췄다. |
| 2026-09-17 | **문서 재구성**: README 의 로깅·접속 로그·요청 처리·앱 규약 상세, `server-lifecycle-guide.html` 의 설정·lifespan·종료 추적, 버전 가이드(`docs/project-guide/v1.0.0/`)의 현행 사실을 이 문서로 모았다. 코드와 대조해 로그 포맷·파일 핸들러 조건·미사용 설정, 프록시 헤더 신뢰 설정, 배포 게이트, 라우트 수를 바로잡았다. 코드 변경 없음. |
| 2026-09-17 | lifespan 이 `manage_application_resources()`(Redis PING 필수·DEBUG DDL·역순 정리)로 옮겨진 것을 반영하고, `env.py` 예시를 실제 코드로 정정했다. |
| 2026-08-25 | 초기화 훅을 `__init__.py` import 부수효과에서 `apps.py` 의 `ready()` + `install_hooks()` 로 바꾼 것을 반영했다(runtime-lifecycle ADR-006). 세션 예시를 정식 이름으로 바꿨다. |
| 2026-08-12 | **Django 스타일 앱 자동 등록 도입**: `app/core/registry.py` 의 `AppRegistry` 가 라우터·모델·`admin_views` 를 결선하고, `main.py` 의 명시 `include_router` 와 중앙 `ADMIN_VIEWS` 목록을 없앴다. "파일 부재는 선택, 잘못된 계약은 오류" 를 `AppContractError` 로 고정하고 `scripts/new_app.py` 를 도입했다. |
| 2026-08-11 | 기능 폴더를 `app/features/` 로 확정하고 SQLAdmin `ModelView` 소유권을 각 기능 `admin.py` 로 옮겼다. 핸들러 커밋 방식에 맞춰 트랜잭션 설명을 정정했다. |
| 2026-06-23 ~ 07-01 | 최초 작성. 수동 등록과 자동 발견 사이를 오간 초기 설계 기록. |
