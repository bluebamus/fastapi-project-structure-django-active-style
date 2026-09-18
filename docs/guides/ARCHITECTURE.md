# 아키텍처 레퍼런스

이 저장소가 **실행 중에 어떻게 조립되고 동작하는가**를 한곳에 모은 문서입니다. 폴더 구조,
앱 자동 등록, 설정·로깅, 기동과 종료, 요청 처리, DB 세션, 보안 경계를 다룹니다.

- 설치·실행·API 목록은 [README](../../README.md), 새 기능을 만드는 절차는
  [기능 개발 가이드](./DEVELOPMENT.md)를 봅니다.
- §3~§9 의 흐름을 도식으로 따라가려면 [서버 수명주기 안내서](./server-lifecycle-guide.html)를 엽니다.
  표·목록의 원문은 이 문서입니다.
- 코드와 이 문서가 다르면 **코드가 정답**입니다. 차이를 발견하면 이 문서를 고칩니다.

---

## 1. 폴더 구조와 의존 방향

```text
fastapi-project-structure-django-active-style/
├── main.py                 # 조립: AppRegistry 발견·결선 + 미들웨어·예외·문서·lifespan·Admin
├── config.py               # Pydantic Settings 12종 + validate_deployment_safety()
├── pyproject.toml          # 의존성·도구 설정 ([tool.uv] package = false, pytest env 주입)
├── .python-version         # 3.14 (requires-python 은 >=3.13 — TypeVar default 사용)
├── .env.example            # 설정 전체 목록 (config.py 와 양방향 일치를 테스트가 강제)
├── alembic.ini             # script_location = migrations
├── compose.test.yaml       # MySQL 8.4 통합 테스트 전용 컨테이너 (호스트 포트 3310)
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
│   │   └── middlewares/    # cors · user_info(접속 로그 수집) · background_tasks · access_log_sink
│   ├── celery/             # 중앙 Celery: app.py · tasks.py · task.py(run_async) · worker_lifecycle.py
│   └── utils/              # 순수 유틸: logs · authenticator(JWT·bcrypt) · pagination · validators
├── migrations/             # env.py 가 런타임과 같은 AppRegistry 로 모델 수집 / versions/
├── scripts/                # new_app.py(앱 생성기) · review_gate.py(로컬·CI 공용 게이트)
├── tests/                  # 횡단 테스트: core/ · integration/(MySQL) · scripts/ · utils/ · test_*.py
├── docs/                   # guides/(현행) · specs/(고정 기준선) · crp/(검수 이력)
└── logs/ media/ static/ poc/   # 런타임·예약 디렉터리 (.gitkeep 만 추적)
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
      └─ install_admin()   ──→ Admin.add_view(...)   (ADMIN=true 일 때만)
```

결선 메서드는 마지막 `discover()` 결과만 쓰고 스스로 다시 스캔하지 않습니다. 목록이 둘이면
런타임과 마이그레이션이 서로 다른 앱을 보게 되고, 그 어긋남은 배포 뒤 "운영에만 테이블이
없다" 로 드러납니다. 요구사항 ID(`FR-*`·`NFR-*`·`SEC-*` 등, 코드 주석이 인용)와 설계 근거는
[`docs/specs/django-style-app-automation.md`](../specs/django-style-app-automation.md)에 있습니다.

### 2.1 규약 — registry 가 찾는 다섯 가지

| 경로 | 계약 | 없으면 |
|---|---|---|
| `<name>/__init__.py` | 앱 패키지 선언. **부수효과를 두지 않는다** | 패키지가 아니므로 발견되지 않음 |
| `<name>/apps.py` | `ready()` — 부팅 시 한 번 실행되는 초기화 훅 | 훅 없는 앱 |
| `<name>/api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱 |
| `<name>/models/` | import 시 ORM 모델이 `Base.metadata` 에 등록. 패키지와 `models.models` 모듈을 **둘 다** import 한다 | 모델 없는 앱 (실제 `auth`) |
| `<name>/admin.py` | `admin_views: list[type]` (SQLAdmin `ModelView`) | 관리 화면 없는 앱 |

발견 규칙:

- `app.features` 의 **직계** 하위 패키지만 봅니다(재귀 없음). 이름이 `_` 로 시작하면 제외합니다
  (`__pycache__`, 작업 중인 `_scratch` 등).
- 순서는 **앱 이름 알파벳순**으로 고정입니다. 파일시스템 순서와 무관하게 라우트 등록 순서가
  같습니다. 앱 사이에 로딩 순서 의존을 만들지 않습니다.
- 앱 이름은 파이썬 식별자여야 합니다. `order-items` 같은 디렉터리는 import 할 수 없어 앱이 되지
  못합니다.
- 폴더가 있으면 다음 부팅에 켜집니다. 실험용 코드는 `_` 로 시작하는 이름을 쓰거나
  `app/features` 밖에 둡니다.

### 2.2 오류 정책 — 파일 부재는 선택, 잘못된 계약은 오류

자동 등록은 실패를 조용하게 만듭니다(라우터가 안 붙어도 서버는 뜹니다). 그래서 없는 것과 틀린
것을 구분합니다.

| 상황 | 동작 |
|---|---|
| 선택 모듈(`apps.py`·`router.py`·`models`·`admin.py`) 자체가 없다 | 건너뛴다 |
| 선택 모듈 **안의** import 가 틀렸다 | 원래 `ModuleNotFoundError` 를 그대로 올려 기동 실패 |
| `router.py` 에 `<name>_router` 가 없거나 `APIRouter` 가 아니다 | `AppContractError` 로 기동 실패 |
| `admin.py` 에 `admin_views` 가 없다 / list 가 아니다 / `ModelView` 가 아니다 | `AppContractError` 로 기동 실패 |
| 두 앱이 같은 `APIRouter` 객체나 같은 `ModelView` 를 내보낸다 | `AppContractError` 로 기동 실패 |

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
| `app/core/db/models_registry.py` | `import_all_models()` — registry 에 위임하는 호환 facade (테스트가 사용) |
| `app/features/admin.py` | `register_admin(app, engine, registry)` → `create_admin_interface()`(Admin 생성, `/admin` 마운트) → `registry.install_admin()`(뷰 등록) |

`register_admin` 이 registry 를 **인자로 받는** 것이 계약입니다. 스스로 발견하면 라우터·모델과
다른 앱 집합을 볼 수 있습니다. Admin 인증 백엔드를 붙인다면 자리는 `create_admin_interface()`
하나입니다(`Admin` 생성 인자이기 때문). `ADMIN=false` 면 `sqladmin` 과 기능 `admin.py` 가
**로드조차 되지 않습니다** — 그래서 기능 `__init__.py` 에서 `admin_views` 를 재노출하지 않습니다.

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

- 디렉터리를 지우면 다음 기동에서 라우터·모델·Admin 에서 빠집니다. **DB 테이블과 데이터는
  남습니다** — 보존·이관과 삭제 revision 을 따로 설계합니다.
- 이름을 바꾸면 공개 URL prefix, `<name>_router`, import 경로, Celery 태스크 이름
  (`home.aggregate_access_stats` 형태), migration 참조가 함께 바뀝니다.

| 증상 | 먼저 볼 것 |
|---|---|
| 앱 전체가 안 보인다 | 직계 하위 패키지인지, `__init__.py` 가 있는지, 이름이 식별자이고 `_` 로 시작하지 않는지 |
| 라우터만 없다 | `api/routers/router.py` 경로와 `<name>_router` 이름 |
| migration 이 비었다 | 모델이 `Base` 를 상속하고 `models/` 아래에서 import 되는지 |
| Admin 뷰가 없다 | `ADMIN` 값, `admin_views` 가 `ModelView` 목록인지 |
| 기동 시 `ModuleNotFoundError` | 선택 모듈 **내부**의 잘못된 import |

회귀 가드: `tests/test_app_autowiring.py`(임시 앱 결선 + 중앙 파일 해시 불변),
`tests/test_router_registration.py`, `tests/test_admin_wiring.py`(모델을 가진 기능은 자기
`admin.py` 를 가진다), `tests/core/test_registry_*.py`.

---

## 3. 기동 순서

```text
main:app import
  ├─ config.py import        설정 객체 생성·검증, validate_deployment_safety()
  ├─ app/core/db/session.py   엔진·세션 팩토리 생성 (아직 접속하지 않음)
  ├─ AppRegistry              discover → install_hooks → import_models
  ├─ FastAPI(...)             문서 URL(openapi_url 은 DEBUG 일 때만), lifespan
  ├─ CustomCORSMiddleware(app).configure_cors() → setup_user_info_middleware(app)
  ├─ _register_exception_handlers(app)          4개 글로벌 핸들러
  ├─ registry.install_routers(app)              <name>_router → /api
  ├─ _add_health_and_docs(app)                  /health · /ready · (DEBUG) Scalar /docs
  └─ ADMIN=true → register_admin(app, engine, registry)
ASGI lifespan 진입
  └─ manage_application_resources(app)          Redis ping → (DEBUG) create_db_tables → yield
```

- `python main.py` 는 조립 후 `uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT,
  reload=DEBUG, log_config=setup_uvicorn_logging())` 을 호출합니다. `uvicorn main:app` 으로 띄우면
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
| `timezone_settings` | 로그 시각, 모델 시간 기본값, Celery timezone |
| `app_settings` | 앱 메타데이터, `DEBUG`/`ENV`/`ADMIN`, 직접 실행 host/port |
| `db_settings` | 엔진 URL·라우팅·풀, Alembic URL(`ALEMBIC_URL`), `describe_routing()`(DSN 마스킹) |
| `cors_settings` | `CustomCORSMiddleware.configure_cors()` |
| `log_settings` | `build_dictconfig()` |
| `middleware_settings` | `UserInfoMiddleware` (활성·제외 규칙·`TRUST_PROXY_HEADERS`) |
| `redis_settings` | startup Redis ping client, Celery broker/backend |
| `jwt_settings` | 토큰 서명·검증·수명 |
| `api_settings` · `session_settings` · `smtp_settings` · `upload_settings` | **선언만 있고 앱 코드가 쓰지 않는다.** `session_settings.SESSION_SECRET_KEY` 만 배포 게이트가 검사한다 |

설정 클래스가 있다고 기능이 있는 것은 아닙니다. SMTP 발송·쿠키 세션·업로드 처리·Redis 캐시는
구현돼 있지 않고, `API_VERSION` 을 바꿔도 라우터 prefix(`/v1/...`)는 바뀌지 않습니다.
`LogSettings` 의 `LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 도
현재 로깅 구성에서 읽지 않습니다(§5).

### 4.3 검증

| 검증 | 거부하는 것 |
|---|---|
| `DatabaseSettings._validate_routing()` | 복제 활성인데 라우터가 꺼짐 / replica 목록이 빔 / 잘못된 replica host 표기 |
| `CORSSettings._reject_wildcard_with_credentials()` | 와일드카드 Origin + credentials |
| `SMTPSettings._reject_tls_with_ssl()` | `SMTP_TLS` 와 `SMTP_SSL` 동시 활성 |
| `validate_deployment_safety()` | 아래 배포 게이트 |

**배포 안전 게이트.** `config.py` import 마지막에 `validate_deployment_safety()` 가 실행됩니다.
`ENV` 가 `staging`/`production` 이면 다음을 **한 번에 모아** `RuntimeError` 로 기동을 막습니다
(메시지에는 설정 이름만, 값은 담지 않습니다).

- `DEBUG=true`
- `ADMIN=true` — 프록시에서 `/admin` 을 막아도 이 검사는 통과하지 못합니다
- placeholder 인 `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` —
  `is_placeholder_secret()` 가 판정한다: 앞뒤 공백 제거·소문자화 후 `change-this` 를 포함하거나 `your-` 로 시작하거나 빈 값.
  옛 예시 파일의 `your-...-change-this` 형식도 여기에 걸린다
- access/refresh 서명 키가 같음
- `CORS_ALLOW_ORIGINS` 에 `*`
- `LOG_SQL_ECHO_ENABLED=true`

`development`/`test` 는 편의 기본값(`DEBUG=true`, `ADMIN=true`)을 그대로 둡니다. 회귀 가드:
`tests/core/test_deployment_safety.py`, 설정과 `.env.example` 의 동기화는
`tests/core/test_settings_contract.py`.

---

## 5. 로깅

- 설정은 `app/utils/logs/config.py` 의 `build_dictconfig()` 한 곳에 있고, 첫 `get_logger()` 가
  `configure_logging()` 으로 한 번 적용합니다.
- 핸들러는 **root 에만** 붙습니다. `get_logger(name)` 은 핸들러 없는 자식 로거를 돌려주고,
  헤더의 `app=` 은 로거 이름이 아니라 **소스 파일 경로**에서 계산합니다. 그래서 새 기능을 추가할
  때 로깅 설정에 손댈 곳이 없습니다. 대가로 앱별·서드파티 로거별 레벨은 따로 줄 수 없습니다.
- 포맷: `[{asctime} {tzname}] {levelname:5} [app={appname}] [{module}:{classname}:{funcName}:{lineno}] {message}`

| ENV | 출력 | 시각 |
|---|---|---|
| `development` | 콘솔 | 로컬 타임존, 밀리초 |
| `test` | 콘솔 | 로컬 타임존 |
| `staging` / `production` | 콘솔 + (`LOG_FILE_ENABLED=true` 면) 회전 파일 `LOG_DIR/{date}_app.log`·`{date}_error.log`(ERROR 이상) | UTC |

파일 핸들러는 root 에 직접 붙지 않고 bounded queue 뒤의 listener 스레드가 씁니다(이벤트 루프가
파일 I/O 로 멈추지 않도록). 크기·보관 수는 `LOG_MAX_SIZE_MB`·`LOG_BACKUP_COUNT`, 파일 임계값은
`LOG_FILE_LEVEL` 입니다. 모든 핸들러에 `RedactingFilter`(DSN 자격증명·`password=`/`token=` 형태
값 마스킹)가 걸리고, SQL/드라이버 잡음은 `LOG_SQL_ECHO_ENABLED=true` 가 아니면 걸러집니다.

**레벨.** 명시값이 `DEBUG` 기반 기본값보다 우선합니다. 레벨은 "최소 심각도" 입니다.

| DEBUG | LOG_LEVEL / LOG_CONSOLE_LEVEL | 콘솔에 나오는 것 |
|---|---|---|
| false | 미설정 / 미설정 | INFO 이상 |
| true | 미설정 / 미설정 | DEBUG 이상 |
| false | DEBUG / DEBUG | DEBUG 이상 (앱은 여전히 DEBUG=false 동작) |
| 무관 | INFO / DEBUG | INFO 이상 — root 가 먼저 거른다 |
| 무관 | DEBUG / INFO | INFO 이상 |

기동 로그의 `(DEBUG=%s)` 는 표시값일 뿐 출력 조건이 아닙니다. 기동 INFO 가 안 보이면
`LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 을 먼저 봅니다. `python main.py` 는 Uvicorn 에
`setup_uvicorn_logging()`(같은 헤더 형식)을 넘기고, `uvicorn` CLI 는 자기 기본 포맷을 씁니다.

```python
from app.utils.logs import get_logger

logger = get_logger("catalog")          # 이름은 출처 구분용 문자열
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
acquire("redis", start=ping, close=aclose, 5s)   ← 정리를 먼저 등록한 뒤 start
register("background-tasks", drain, 5s)
DEBUG=true → create_db_tables()                  ← 30초 guard
yield  (요청 처리 기간)
finally: resources.close(); app.state.redis = None; app.state.resources = None
```

**Redis 는 필수입니다.** `Redis.from_url(REDIS_URL, socket_connect_timeout=5, socket_timeout=5)`
후 `ping()` 이 실패하면 오류 타입만 ERROR 로 남기고 다시 올려 서버 시작을 멈춥니다. `DEBUG` 와
무관하고 끄는 설정은 없습니다. 성공해야 `app.state.redis` 에 client 가 들어갑니다. 기동 순간의
도달 가능성만 확인할 뿐 이후 Redis 상태를 감시하지 않고, `/ready` 도 Redis 를 보지 않습니다.
공통 Redis Dependency 는 없습니다.

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
요청 → UserInfoMiddleware → CORS → 라우터
     → Depends: 세션 generator → get_<name>_service(_readonly) → Service(session) → Repository
     → 쓰기 핸들러 본문이 await service.commit() → 응답 DTO
     → (예외면) 세션 generator 가 rollback 후 재전파 → 글로벌 예외 핸들러
     → UserInfoMiddleware 가 상태·소요시간을 붙여 접속 로그 저장 태스크 제출
```

미들웨어는 CORS → UserInfo 순서로 등록되며, Starlette 는 나중에 등록한 것을 바깥에 둡니다.
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
3. `BackgroundTaskRunner` 는 동시 256개 상한을 넘으면 새 로그를 **버리고** `dropped` 를 셉니다.
   종료 시에는 수락 중단 → 5초 대기 → 남은 태스크 cancel → 취소 완료까지 await 순서로 drain 합니다.
4. sink 는 `background_db_session()`(별도 풀)으로 `UserAccessLogService` 를 조립해 저장하고 명시
   commit 합니다. 요청 세션을 넘기지 않습니다. 저장 실패는 로그만 남기고 응답에 영향이 없습니다.

| 분류 | 필드 |
|---|---|
| 네트워크 | `ip_address`, `forwarded_for`(X-Forwarded-For 원문), `real_ip`(X-Real-IP 원문) |
| User-Agent | `user_agent`, `os_name`, `os_version`, `browser_name`, `browser_version`, `device_type`, `device_brand`, `device_model`, `is_bot` |
| 요청·응답 | `request_path`, `request_method`, `query_string`, `referer`, `accept_language`, `response_status`, `response_time_ms` |
| 식별 | `session_id`(`session_id` 쿠키), `user_id`(`request.state.user_id` 가 있으면) |

`ip_address` 는 `TRUST_PROXY_HEADERS=true` 일 때만 X-Forwarded-For 첫 값 → X-Real-IP 순으로 전달
헤더를 믿고, 기본(false)은 직접 연결 주소를 씁니다. 리버스 프록시 뒤에서만 켜고, 프록시가 외부에서
온 전달 헤더를 지우도록 구성합니다. JWT 인증은 `request.state.user_id` 를 설정하지 않으므로
`user_id` 는 보통 비어 있습니다. `user_access_logs` 는 `ip_address`·`created_at`·`device_type`·
`os_name`·`browser_name`·`session_id`·`user_id` 에 인덱스가 있습니다.

비핵심 로그라서 API 가용성을 로그 완전성보다 우선한 설계입니다. 무손실 감사 로그가 필요하면
내구 큐·재처리·중복 제거를 따로 설계해야 합니다. 개인정보 쪽 한계는 §10.3 을 봅니다.

---

## 8. DB 엔진·세션·라우팅 (`app/core/db/`)

### 8.1 엔진과 세션 팩토리

| 객체 | 용도 | 풀 |
|---|---|---|
| `engine` (= `writer_engine`) | 요청 writer, DDL, `/ready`, SQLAdmin | 20 + overflow 20, timeout 30s |
| `read_engines` | replica SELECT (복제 활성 시) | replica 마다 20 + 20 |
| `background_engine` | 접속 로그·Celery 등 요청 밖 쓰기 | 10 + 10, timeout 60s |

공통: `pool_recycle=280`, `pool_pre_ping=True`, 드라이버 `connect_timeout=10`. 세션 팩토리
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

- 모든 generator 는 `async with` 로 세션을 열고, 전달된 예외면 `rollback()` 후 재전파하며, 끝나면
  닫습니다. **성공 시 자동 commit 하지 않습니다.**
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

1. ORM flush·Core DML → writer
2. 그 밖의 SELECT → reader (라운드로빈). 한 세션이 고른 reader 는 세션 끝까지 유지(pin)
3. `DB_READ_STICKY_AFTER_WRITE=true`(기본) 면 쓰기 뒤 같은 세션의 SELECT → writer
4. reader 가 없으면 writer
5. `SELECT ... FOR UPDATE/SHARE` 같은 잠금 조회, 판별 불가 Raw SQL → writer

복제 지연을 허용할 수 없는 읽기는 writer 세션을 쓰거나 `using_writer(session)` 으로 고정합니다.
sticky 는 세션 내부 정책이라 다음 요청의 read-only 세션까지 지연을 없애지 않습니다.

**read-only 집행**은 라우터가 꺼져 있어도 적용됩니다. 세션 클래스 이벤트(`before_flush`,
`do_orm_execute`)가 read-only 세션에서 ORM flush 와, 읽기로 판별되지 않는 구문을 거부합니다.
판별은 괄호 깊이 0 의 단어만 훑습니다 — 읽기 전용 CTE(`WITH ... SELECT`)는 통과하고, 최상위에
쓰기 키워드가 있는 문장(`WITH ... UPDATE`·`DELETE` 포함)·잠금 조회·multi-statement·따옴표나
괄호가 맞지 않아 판별할 수 없는 문장은 거부합니다. `session.info` 표시는 보안 경계가 아니므로 운영에서는
read-only DB 계정·권한을 최종 방어선으로 둡니다. 회귀 가드: `tests/core/test_read_only_guard.py`,
`tests/core/test_db_router.py`.

---

## 9. 오류 응답과 health / ready

글로벌 핸들러 4종이 모든 오류를 `ErrorResponse{error_code, message, detail}` 로 바꿉니다.

| 예외 | 응답 |
|---|---|
| `AppException` 계열 (`NotFoundException`, `DuplicateException`, `ValidationException`, `DatabaseException`, 기능 예외) | 예외가 정한 상태 코드·`error_code`·`detail` |
| `RequestValidationError` | 422, `detail` 에 `field`·`message`·`type` 목록 |
| Starlette `HTTPException` | 해당 상태, `error_code=HTTP_<status>` |
| 그 밖의 `Exception` | 500 `INTERNAL_SERVER_ERROR`, 고정 메시지, `detail=null` — **DEBUG 여부와 무관** |

500 의 예외 타입·route template·스택은 로그에만 남습니다(경로에 박힌 식별자 대신 template).
Repository 의 DB 오류 변환도 드라이버 원문을 응답에 싣지 않습니다. 회귀 가드:
`tests/test_exception_handler_leak.py`.

| 경로 / 지점 | 의미 | 결과 |
|---|---|---|
| `GET /health` | 프로세스 생존·버전 (DB·Redis 검사 없음) | `{"status":"healthy","version":...}` |
| `GET /ready` | writer 로 `SELECT 1`, 2초 guard | 성공 `status="ready"`, 실패 503 `NOT_READY` (예외 메시지·DSN 없음) |
| `/docs`, `/openapi.json` | `DEBUG=true` 일 때만 | 아니면 404 |
| 설정·registry 오류 | lifespan 이전 조립 실패 | 프로세스 기동 실패 |
| Redis ping·개발 DDL 실패 | startup 실패 | 등록된 자원 정리 후 중단 |
| 커밋 실패 | 쓰기 핸들러 안에서 예외 | 성공 응답 전에 오류 응답 |
| 접속 로그 포화·저장 실패 | 응답과 분리 | 로그 경고, `dropped` 증가 |

`/health` 만으로 DB·Redis 준비를 판단하지 않습니다. 오케스트레이터의 readiness 는 `/ready` 에
걸되, Redis 는 따로 감시합니다.

---

## 10. 인증과 보안 경계

### 10.1 JWT (`auth` 앱, `app/utils/authenticator/`)

- OAuth2 password flow + JWT access/refresh(PyJWT), bcrypt 해시. 자격증명은 `User.hashed_password`
  에 있고 `auth` 는 인증 로직만 갖습니다(모델 없는 앱).
- 토큰에는 종류 클레임(`type`)이 있어 access 자리에 refresh 를(또는 반대로) 넣으면 거부됩니다.
  access 와 refresh 는 서로 다른 키로 서명합니다.
- `refresh` 는 access·refresh 를 **둘 다** 새로 발급합니다. 비활성 사용자(`is_active=false`)는
  로그인과 재발급에서 거부됩니다.
- `get_current_user` 는 Bearer access 토큰을 검증하고 read-only 세션으로 활성 사용자를 읽습니다.
  이 객체를 쓰기 세션에서 직접 수정하지 말고, 쓰기 세션으로 다시 조회합니다.
- **상수 시간 인증:** 사용자가 없거나 해시가 없어도 더미 해시로 bcrypt 검증을 수행해 응답 시간으로
  사용자명 존재를 알아내기 어렵게 합니다(네트워크 변동까지 없애지는 못합니다).
- **논블로킹 해싱:** bcrypt 는 `asyncio.to_thread` 로 이벤트 루프 밖에서 돕니다.

| 설정 | 기본값 |
|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 7 |
| `JWT_ALGORITHM` | HS256 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` (placeholder — staging/production 에서는 게이트가 거부, §4) |

### 10.2 SQLAdmin

- `/admin` 에는 **인증이 없습니다.** 인증 백엔드는 붙이지 않기로 확정한 영구 비목표입니다.
  `ADMIN` 기본값 `true` 는 개발 편의를 위한 의도된 선택이고, staging/production 은 배포 게이트가
  `ADMIN=true` 를 거부합니다.
- `development`/`test` 에서 켜 두면 도달 가능한 누구나 사용자·게시글·댓글·SNS·상품·주문·접속로그를
  조회·수정·삭제하고 CSV 로 내보낼 수 있습니다. 로컬 밖에 노출되는 개발 서버라면 `ADMIN=false`,
  `SERVER_HOST=127.0.0.1`, 프록시 차단을 함께 씁니다(`SERVER_HOST` 기본값은 `0.0.0.0`).
- `User.hashed_password` 는 목록·상세·폼·내보내기 어디에도 나오지 않고, `User` 는 Admin 에서
  생성할 수 없습니다(비밀번호 없는 계정 방지). 구조 증거: `tests/core/test_admin_views.py`.

### 10.3 현재 한계 — 외부 공개 전에 결정할 것

| 항목 | 현재 상태 |
|---|---|
| CRUD 인가 | user·blog·reply·sns·catalog·reports·home 조회 API 에 인증·소유권 검사가 없다. `get_current_user` 를 쓰는 곳은 `/api/v1/auth/me` 뿐이다 |
| 작성자 | 콘텐츠의 `author` 는 요청 본문의 자유 문자열이다 |
| 참조 무결성 | `Reply.post_id` 는 FK 없는 문자열 — 게시글 존재 검증·삭제 전파 정책 없음 |
| 로그인 보호 | rate limit·계정 잠금 없음 |
| 토큰 폐기 | 서버 측 폐기 목록 없음 — 유출된 refresh 토큰은 만료까지 유효(`REFRESH_TOKEN_EXPIRE_DAYS` 로 수명 조절) |
| 접속 로그 개인정보 | `query_string`·`referer`·`session_id` 쿠키를 원문 저장한다. redaction·보존 기간·파기 절차·조회 API 접근 통제가 없다 |
| 쿠키 이름 | `session_id` 가 코드에 고정 — `SESSION_COOKIE_NAME` 은 쓰이지 않는다 |
| CORS | 기본 `CORS_ALLOW_ORIGINS=["*"]`, credentials false (staging/production 은 게이트가 `*` 를 거부) |

---

## 11. Celery (요청 밖 작업)

- `app/celery/app.py` 의 `celery_app` 은 `REDIS_URL` 을 broker/backend 로 쓰고
  `include=["app.celery.tasks"]` 하나만 포함합니다. 기능별 `worker/` 는 두지 않고 모든 태스크를
  `app/celery/tasks.py` 에 `@celery_app.task(name="<app>.<action>")` 로 정의합니다
  (예: `home.aggregate_access_stats`).
- 동기 태스크 안에서 코루틴은 `app/celery/task.py` 의 `run_async(coro)` 로 실행합니다. 워커 프로세스마다
  영속 이벤트 루프 하나를 재사용해, 닫힌 루프에 묶인 async 풀 연결 문제를 피합니다(prefork 순차
  실행 전제 — 다른 pool 을 쓰면 재검증).
- `worker_lifecycle.register_worker_signals()` 가 prefork 자식 초기화에서 상속된 sync 풀을
  폐기(`dispose(close=False)`)하고 루프를 새로 만들며, 종료 시 루프를 닫습니다. async DB dispose 까지
  하지는 않습니다.
- API 기동은 worker/beat 를 띄우지 않고, API lifespan 이 워커 자원을 정리하지도 않습니다.
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
config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)
```

- URL 우선순위(`DatabaseSettings.ALEMBIC_URL`): `ALEMBIC_DATABASE_URL` 설정값 → primary DSN 의
  `+aiomysql` 을 `+pymysql` 로 바꾼 값. `env.py` 는 환경변수를 직접 읽지 않습니다.
- revision 체인: `f4adf0ae24ea`(baseline) → `b2f1a9c0d3e4`(user 비밀번호) →
  `c3d5e7a91b02`(catalog_products) → `d4e6f8b12c34`(sales_orders, head).
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
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` | 정적 분석 |
| `uv run python -m scripts.review_gate [--group ...]` | CI 와 같은 판정. `--list` 로 그룹 확인 |

`pytest` 콘솔 스크립트 대신 `python -m pytest` 를 씁니다(다른 인터프리터를 집은 전례). 게이트 판정용
mypy 는 캐시 없이 돈 결과만 인정합니다.

| 게이트 그룹 | 내용 |
|---|---|
| `static` | ruff check · ruff format --check · mypy · bandit(`app`, `main.py`, `config.py`) |
| `tests` | 전체 pytest(skip·xfail·deselect 0 이어야 통과 — MySQL 필요) + collect-only |
| `structure` | `alembic heads` |
| `supply` | Action SHA 고정 · compose 이미지 digest · 비밀값 스캔 |
| `docs` | README·`docs/guides`·`docs/crp`·워크플로 주석이 가리키는 경로·환경변수 실재, 가르치는 문서의 옛 세션 별칭 금지 |
| `deps` | pip-audit (네트워크 필요) |

CI(`.github/workflows/ci.yml`)는 두 job 입니다: gate job 이 `static structure supply docs deps` 와
`pytest -m "not mysql"`(skip·xfail 0 확인)을, MySQL job 이 `compose.test.yaml` 을 띄워
`pytest -m mysql` 과 `tests` 그룹을 돌립니다.

---

## 14. 변경 이력

| 날짜 | 변경 내용 |
|---|---|
| 2026-09-17 | **문서 일관성 정리**: 개발 가이드를 `DEVELOPMENT.md` 로 이름을 바꾸고, 재구성 때 지웠던 HTML 안내서 2종(`server-lifecycle-guide.html`·`feature-development-guide.html`)을 현행 코드·이 문서와 맞춰 복원했다(표·목록 원문은 Markdown 이 소유). 코드 변경: blog·reply·sns·user 쓰기 핸들러를 "DTO 검증 → commit" 순서로 맞췄다. |
| 2026-09-17 | **문서 재구성**: README 의 로깅·접속 로그·요청 처리·앱 규약 상세, `server-lifecycle-guide.html` 의 설정·lifespan·종료 추적, 버전 가이드(`docs/project-guide/v1.0.0/`)의 현행 사실을 이 문서로 모았다. 코드와 대조해 로그 포맷·파일 핸들러 조건·미사용 설정, 프록시 헤더 신뢰 설정, 배포 게이트, 라우트 수를 바로잡았다. 코드 변경 없음. |
| 2026-09-17 | lifespan 이 `manage_application_resources()`(Redis PING 필수·DEBUG DDL·역순 정리)로 옮겨진 것을 반영하고, `env.py` 예시를 실제 코드로 정정했다. |
| 2026-08-25 | 초기화 훅을 `__init__.py` import 부수효과에서 `apps.py` 의 `ready()` + `install_hooks()` 로 바꾼 것을 반영했다(runtime-lifecycle ADR-006). 세션 예시를 정식 이름으로 바꿨다. |
| 2026-08-12 | **Django 스타일 앱 자동 등록 도입**: `app/core/registry.py` 의 `AppRegistry` 가 라우터·모델·`admin_views` 를 결선하고, `main.py` 의 명시 `include_router` 와 중앙 `ADMIN_VIEWS` 목록을 없앴다. "파일 부재는 선택, 잘못된 계약은 오류" 를 `AppContractError` 로 고정하고 `scripts/new_app.py` 를 도입했다. |
| 2026-08-11 | 기능 폴더를 `app/features/` 로 확정하고 SQLAdmin `ModelView` 소유권을 각 기능 `admin.py` 로 옮겼다. 핸들러 커밋 방식에 맞춰 트랜잭션 설명을 정정했다. |
| 2026-06-23 ~ 07-01 | 최초 작성. 수동 등록과 자동 발견 사이를 오간 초기 설계 기록. |
