# 아키텍처 문서

이 문서는 현재 아키텍처의 요약·자동 등록 규약을 설명합니다.
코드와 문서 간 불일치가 있으면 코드가 정답이며, 이 문서를 업데이트하세요.

검토 기준: **2026-09-17 현재 작업 트리**. 단계별 실행은 [서버 시작·종료 HTML 안내서](./server-lifecycle-guide.html),
MVC·주입·비동기·신규 기능 작성은 [개발 HTML 지침서](./feature-development-guide.html),
ORM/Raw 코드 읽기 순서는 [워크플로](./orm-raw-workflow.md)에서 확인합니다.

---

## 1. 폴더 분류체계

```
fastapi-project-structure-django-active-style/
├── main.py                          # 진입점: AppRegistry 로 앱 자동 발견·결선 + 앱 설정
├── config.py                        # Pydantic Settings 12종 + validate_deployment_safety()
├── pyproject.toml                   # 의존성 + [tool.uv] package = false
├── .python-version                  # 3.14 (uv 가 인터프리터를 맞춘다)
├── alembic.ini                      # Alembic 설정 (script_location = migrations)
├── compose.test.yaml                # MySQL 8.4 통합 테스트 전용 컨테이너 (포트 3310)
│
├── app/
│   ├── features/                    # 기능 단위 앱 (디렉터리 존재 = 등록 선언)
│   │   ├── admin.py                 # SQLAdmin 조립 진입점 register_admin() — 앱이 아님(파일)
│   │   ├── auth/ blog/ catalog/ home/ reply/ reports/ sns/ user/   # 현재 발견되는 8개 앱
│   │   ├── home/                    # 예시 앱 — 접속 로그
│   │   │   ├── __init__.py          # 앱 패키지 선언 (부수효과 금지 — admin_views 재노출도 금지)
│   │   │   ├── apps.py              # ready() — 부팅 초기화 훅 (선택)
│   │   │   ├── api/routers/
│   │   │   │   ├── router.py        # 앱 루트 라우터 (<name>_router: v1 취합)
│   │   │   │   └── v1/              # 버전별 엔드포인트 (뷰는 HTTP 역할만)
│   │   │   ├── models/              # SQLAlchemy ORM 모델
│   │   │   ├── schemas/             # Pydantic 요청/응답 스키마
│   │   │   ├── services/            # 비즈니스 로직
│   │   │   ├── repositories/        # 데이터 접근 계층
│   │   │   ├── dependencies/        # FastAPI Depends 헬퍼 (Service 구성 — 커밋은 핸들러)
│   │   │   ├── admin.py             # SQLAdmin ModelView + admin_views (모델이 있으면 필수)
│   │   │   ├── exceptions.py        # 기능 예외 (선택)
│   │   │   └── tests/               # 기능 테스트
│   │   └── <name>/                  # 추가 앱은 같은 구조를 따름
│   │
│   ├── core/                        # 프레임워크 인프라 (features 가 의존)
│   │   ├── registry.py              # 앱 자동 발견 (AppModule / AppRegistry)
│   │   ├── resources.py             # ResourceManager + manage_application_resources() (Redis ping·DEBUG DDL·역순 정리)
│   │   ├── exception.py             # 공통 예외 계층 + ErrorResponse
│   │   ├── tags_metadata.py         # OpenAPI 태그 메타데이터
│   │   ├── db/
│   │   │   ├── session.py           # 엔진, 세션 팩토리, 커넥션 풀, background_db_session
│   │   │   ├── router.py            # 읽기/쓰기 라우팅 (RoutingSession)
│   │   │   └── models_registry.py   # 모델 import — AppRegistry 위임 facade
│   │   ├── models/models_base.py    # SQLAlchemy Base (declarative) + Timestamp·UUID Mixin
│   │   ├── repositories/
│   │   │   ├── repository_base.py   # BaseRepository[Model, PK] (ORM)
│   │   │   ├── crud_base.py         # 제네릭 CRUD 메서드
│   │   │   ├── raw_repository_base.py # RawRepositoryBase (Raw SQL, query_name 관측)
│   │   │   └── raw_crud_base.py     # fetch_*/execute primitive + ensure_identifier()
│   │   ├── services/services_base.py # BaseService
│   │   └── middlewares/
│   │       ├── cors_middleware.py
│   │       ├── user_info_middleware.py
│   │       ├── background_tasks.py  # 응답 후 태스크 추적 (누수 방지)
│   │       └── access_log_sink.py
│   │
│   ├── celery/                      # 중앙 Celery (기능별 worker/ 미사용)
│   │   ├── app.py                   # Celery 앱 (include=["app.celery.tasks"])
│   │   ├── tasks.py                 # 중앙 태스크 모듈 (모든 기능 백그라운드 작업)
│   │   ├── task.py                  # run_async() 동기 브릿지
│   │   └── worker_lifecycle.py      # worker 시그널: 상속 pool 분리·loop 정리
│   │
│   └── utils/                       # 순수 유틸 (외부·상위 계층 의존 없음)
│       ├── logs/                    # 구조화 로깅 (get_logger, setup_uvicorn_logging, 파일 queue listener)
│       ├── authenticator/           # 인증 (JWT·bcrypt)
│       ├── pagination/              # 페이지네이션 (순수 dataclass)
│       └── validators.py            # 공통 값 검증
│
├── tests/                           # 횡단 테스트 (core 계약·배선·교차 기능)
│   ├── core/                        # 설정 계약, registry, admin 뷰 정책, Raw SQL 정적 가드, 마이그레이션 체인
│   ├── integration/                 # MySQL 8.4 통합 (pytest -m mysql, compose.test.yaml 필요)
│   ├── scripts/                     # new_app·review_gate 검사
│   └── utils/                       # 로깅·인증·페이지네이션
│
├── scripts/
│   ├── new_app.py                   # Django startapp 대응 앱 생성기
│   └── review_gate.py               # 로컬·CI 공용 검증 게이트 (static·tests·structure·supply·docs·deps)
├── migrations/
│   ├── env.py                       # 런타임과 같은 AppRegistry 로 전 기능 모델 수집
│   └── versions/                    # baseline → user 비밀번호 → catalog → sales_orders
├── .github/workflows/ci.yml         # CI: review_gate 호출 + pytest(-m "not mysql") + MySQL job
└── docs/
    ├── README.md                    # 문서 안내 — 무엇부터 볼지
    ├── guides/                      # 살아 있는 사용자·개발자 가이드
    │   ├── ARCHITECTURE.md          # ← 이 문서 (아키텍처 SSOT)
    │   ├── QUICKSTART.md            # 최소 실행 경로
    │   ├── orm-raw-workflow.md      # ORM/Raw 선택 기준
    │   ├── server-lifecycle-guide.html # 설정·기동·요청·종료 상세 추적
    │   └── feature-development-guide.html # MVC·DI·신규 API/테이블 개발
    └── crp/                         # 검수 이력 (결함 대장·잔여 위험)
```

> 기능 테스트는 `app/features/<name>/tests/`, 횡단 테스트는 최상위 `tests/` 에 둡니다.
> `pytest` 가 양쪽을 모두 수집합니다.

### 의존 방향

```
features → core → utils
```

`core`는 `utils`만 알고, `features`는 `core`를 사용합니다.
업무 기반 `core`가 특정 기능의 Service/Repository에 의존하지 않는 것이 원칙입니다.
다만 `AppRegistry`는 등록을 위해 기능의 hook·model·router·admin 모듈을 동적으로 import합니다.
기능 앱이 미들웨어 등에 붙어야 하면 등록 훅으로 연결합니다(예: `access_log_sink.register_sink()`).

---

## 2. Django 스타일 앱 자동 등록 (AppRegistry)

라우터·모델·Admin 등록에 중앙 목록을 쓰지 않습니다. `app/features/<name>/` **디렉터리
존재 자체가 등록 선언**이고, `AppRegistry` 가 부팅 시 그것을 발견해 결선합니다.

설계의 뼈대는 **발견과 결선의 분리**입니다.

```text
app/features/*
       |
       v
AppRegistry.discover()          ← "어떤 앱이 있는가" (이름 알파벳순, _ 제외)
       |
       +-- install_hooks() ----> 각 앱 apps.py 의 ready()  (발견과 분리 — C-5)
       +-- import_models() ----> Base.metadata ----> DEBUG create_all / Alembic
       +-- install_routers() --> FastAPI.include_router(..., prefix="/api")
       `-- install_admin() ----> Admin.add_view(...)      ADMIN=true 일 때만
```

런타임 main은 한 registry의 발견 결과를 hook·model·router·Admin 조립에 재사용합니다.
Alembic은 별도 프로세스/호출에서 `import_all_models()`가 새 registry를 만들지만 **같은
AppRegistry 발견 규칙**을 사용하며 `ready()`를 실행하지 않습니다. 동일 인스턴스 공유와
동일 발견 규칙 재사용을 구분합니다.

### 2.1 앱 규약

| 경로 | 계약 | 부재 시 |
|---|---|---|
| `<name>/__init__.py` | 앱 패키지 선언. 부수효과를 두지 않는다 | 패키지가 아니므로 발견되지 않음 |
| `<name>/apps.py` | `ready()` — 부팅 초기화 훅 | 초기화 훅 없는 앱으로 정상 처리 |
| `<name>/api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱으로 정상 처리 |
| `<name>/models/` | import 시 `Base.metadata` 등록 | 모델 없는 앱으로 정상 처리 (`auth`) |
| `<name>/admin.py` | `admin_views: list[type]` | Admin 없는 앱으로 정상 처리 |

- home 은 `apps.py` 의 `ready()` 에서 `register_sink()` 로 access-log sink 를 등록합니다.
  `discover()` 는 부작용이 0 이고(C-5), 초기화는 `install_hooks()` 가 명시적으로 호출합니다 —
  import 만으로 상태가 바뀌면 테스트 결과가 실행 순서에 좌우됩니다(ADR-006).
- SQLAdmin ModelView 는 기능이 소유하고(`admin.py`), registry 가 자동 취합합니다. 기능
  `__init__.py` 로는 **재노출하지 않습니다** — 재노출하면 라우터만 필요한 import 에도
  sqladmin 이 딸려 와 `ADMIN=false` 가 무의미해집니다(ADMIN-2).

### 2.2 오류 정책 — 파일 부재는 선택, 잘못된 계약은 오류

자동 등록은 실패를 조용하게 만듭니다. 그래서 **없는 것과 틀린 것을 구분**합니다.

| 상황 | 동작 |
|---|---|
| 선택 모듈 자체가 없다 | 건너뛴다 |
| 선택 모듈 **안의** import 가 틀렸다 | 원래 `ModuleNotFoundError` 를 그대로 올린다 |
| 모듈은 있는데 export 가 없거나 타입이 틀리다 | `AppContractError` 로 기동 실패 |
| 같은 라우터 객체·같은 ModelView 를 두 앱이 내보낸다 | `AppContractError` 로 기동 실패 |

과거 관용 수집(`getattr(module, "admin_views", [])`)은 빈 `admin.py` 를 무신호로 건너뛰어
ADMIN-1 을 낳았습니다. 지금은 파일이 **있는데** 계약이 틀리면 기동이 멈춥니다.

### 2.3 `main.py` — 발견 후 결선

```python
from app.core.registry import AppRegistry

registry = AppRegistry()                  # FastAPI 인스턴스 생성 **전에** 발견 —
registry.discover()                       #   앱 초기화 훅이 미들웨어 설정보다 먼저 끝나야 한다
registry.install_hooks()                  # 각 앱 apps.py 의 ready() — discover 와 분리(C-5)
registry.import_models()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app):   # app/core/resources.py
        yield

app = FastAPI(..., lifespan=lifespan)     # 인스턴스 + 문서 설정 (openapi_url 은 DEBUG 일 때만)
CustomCORSMiddleware(app).configure_cors()
setup_user_info_middleware(app)
_register_exception_handlers(app)         # 4개 글로벌 핸들러

_mounted = registry.install_routers(app)  # 발견된 앱의 <name>_router 를 /api 에 마운트

_add_health_and_docs(app)                 # /health + /ready + (DEBUG 일 때) Scalar /docs
if app_settings.ADMIN:                    # SQLAdmin
    register_admin(app, engine, registry) # app/features/admin.py — 조립 진입점
```

미들웨어·예외 핸들러·문서·lifespan 설정은 계속 `main.py` 가 담당합니다. 별도의
`create_app()` 팩토리·`bootstrap.py` 는 없습니다.

lifespan 본문은 `async with manage_application_resources(app): yield` 한 줄이고, 자원 조립은
`app/core/resources.py`의 `manage_application_resources()`가 담당합니다. 순서는 다음과 같습니다.

1. `app.state.resources` 설정, `logging-queue`(5초)·`db-engines`(10초) 정리 등록
2. `Redis.from_url(redis_settings.REDIS_URL, socket_connect_timeout=5, socket_timeout=5)` 후
   `acquire("redis", ...)` — 정리를 먼저 등록하고 `ping()`. 실패하면 오류 타입만 기록하고 다시 올려
   서버 시작을 중단합니다. 성공해야 `app.state.redis`에 client가 들어갑니다.
3. `background-tasks`(5초) 정리 등록
4. `DEBUG=true`면 `create_db_tables()`(개발용 `create_all`, 30초 guard), 아니면 건너뜀
5. `yield` — 요청 처리 기간. 종료(또는 startup 실패) 시 `resources.close()` 후
   `app.state.redis`·`app.state.resources`를 `None`으로 되돌립니다.

종료는 등록 역순인 background task → Redis client → DB engine → logging queue 순서입니다.
회귀 가드: `tests/test_lifespan.py`(Redis PING 실패 시 startup 중단 + 정리 포함).

`ResourceManager.acquire()`는 cleanup을 먼저 등록한 뒤 start를 호출합니다. `close()`는
멱등이며 등록 역순으로 일반 오류·timeout을 기록하고 다음 정리를 시도합니다.
단, 20초 deadline을 소진하면 남은 자원마다 1초 예비분을 주므로 **엄격한 전체 20초 상한은
아닙니다**. `CancelledError`는 `except Exception`에 잡히지 않아 남은 정리와 state 초기화가
중단될 수 있습니다. Default의 중첩 context manager와 같은 취소 보장으로 읽지 않습니다.
로깅 queue 종료 뒤의 최종 로그도 파일 출력이 보장되지 않습니다.

---

## 3. 새 기능 추가 — 중앙 파일 편집 없음

`app/features/<name>/` vertical slice를 만들고 아래 export 규약·모델·테스트·migration을 완성합니다.
중앙 등록 목록을 편집하지 않는다는 뜻이지 생성기 실행만으로 업무 기능이 완성되는 것은 아닙니다.

### 3.1 절차

```bash
uv run python -m scripts.new_app <name> [--with-admin] [--force]   # Django startapp 대응
```

- 생성물: `api/routers/v1/`·`models/`·`schemas/`·`services/`·`repositories/`·`dependencies/`·`tests/`
  패키지(`__init__.py`), 빈 `<name>_router` 가 있는 `api/routers/router.py`, 예시 주석만 있는
  `dependencies/<name>_dependencies.py`, `--with-admin` 이면 `admin_views: list[type] = []` 인 `admin.py`.
  `models/models.py`·`apps.py`·v1 엔드포인트는 만들지 않습니다.
- 이름은 파이썬 식별자여야 하고 예약어는 거부됩니다. 대상 앱이 이미 있으면 중단하며, 덮어쓰려면
  `--force` 를 명시합니다. `--category` 는 호환용 예약 옵션으로 동작에 영향이 없습니다.
- 라우터: 생성된 `api/routers/router.py` 의 `<name>_router` 에 v1 서브라우터를 include.
- 모델: `models/models.py` 에 두고 `models/__init__.py` 에서 재노출 — `env.py`·`session.py`
  를 손대지 않습니다.
- Admin: `admin.py` 에 ModelView + `admin_views` — 중앙 취합 목록이 없습니다.

`main.py` · `migrations/env.py` · `app/features/admin.py` 는 **열지 않습니다**.
회귀 가드: `tests/test_app_autowiring.py` 가 임시 앱을 만든 뒤 이 파일들의 해시가
변하지 않았음을 확인합니다.

### 3.2 SQLAdmin 조립 구조

`main.py` 는 `ADMIN=true` 일 때 `register_admin(app, engine, registry)` **하나만** 호출합니다.

```text
main.py
  └─ register_admin(app, engine, registry)   외부 진입점 (조립부가 아는 유일한 이름)
       ├─ create_admin_interface(app, engine)  Admin 생성 + /admin 마운트
       └─ registry.install_admin(admin)        발견된 앱의 admin_views 등록
```

| 함수 | 책임 | 아는 것 |
|---|---|---|
| `create_admin_interface(app, engine)` | `Admin` 생성 → SQLAdmin 이 `/admin` 마운트 | 앱·엔진·제목 (향후 `authentication_backend`) |
| `registry.install_admin(admin)` | 발견된 앱의 `admin_views` 를 앱 이름순으로 등록 | 앱 목록과 `add_view` 뿐 |
| `register_admin(app, engine, registry)` | 위 둘을 생성 → 등록 순으로 호출 | 조립 순서 |

> 나눈 이유는 두 책임이 서로 다른 것을 알아야 하기 때문입니다 — 생성 쪽은 앱·엔진을,
> 등록 쪽은 앱 목록만 압니다. 나뉘어 있으면 각각 단독으로 검증할 수 있고, 나중에 인증
> 백엔드를 붙일 자리도 `create_admin_interface()` 하나로 정해집니다(인증 백엔드는 `Admin`
> 생성 인자라 등록 쪽에는 넣을 수 없습니다).
>
> `register_admin` 이 registry 를 **인자로 받는** 것이 계약입니다. 스스로 발견하면 라우터·
> 모델과 다른 앱 집합을 볼 수 있습니다. 회귀 가드: `tests/test_admin_wiring.py`.

### 3.3 Django 와의 대응 범위

| Django | 이 프로젝트 | 판정 |
|---|---|---|
| 앱 registry | `AppRegistry` | 대응 |
| `AppConfig.ready()` | 앱 `apps.py` 의 `ready()` (`install_hooks()` 가 호출) | **역할만** 대응 — 생명주기 보장은 다름 |
| 모델 발견 | 앱 `models` import | 대응 |
| Admin 등록 | 앱 `admin.py` 의 `admin_views` 자동 수집 | 대응 |
| `startapp` | `python -m scripts.new_app <name>` | 대응 |
| URLconf | `<name>_router` 자동 마운트 | Django 에 없는 확장 |
| `INSTALLED_APPS` | 디렉터리 존재가 등록 선언 | **의도적인 차이** |

> Django 호환 계층이 아니며 Django 기반도 아닙니다. 초기화 훅은 프레임워크가 보장하는
> 준비 단계가 아니라 파이썬 import 이므로, 빠르고 멱등적이어야 하며 DB·네트워크 I/O 를
> 하면 안 됩니다.

### 3.4 필수/선택 파일 표

| 파일/디렉토리 | 필수 | 설명 |
|--------------|------|------|
| `__init__.py` | ✅ | 앱 패키지 선언만. 결선은 registry 가 컨벤션 경로에서 직접 한다 |
| `apps.py` | 선택 | `ready()` — 부팅 시 한 번 실행되는 멱등 초기화 훅 |
| `api/routers/router.py` + `v1/` | ✅ | 기능 루트 라우터 + 버전별 엔드포인트 |
| `models/` `schemas/` `services/` `repositories/` `dependencies/` | ✅ | 데이터/로직 계층 |
| `tests/` | ✅ | pytest 테스트 |
| `exceptions.py` | 선택 | 기능 예외 |
| `admin.py` | 선택 | 기능 소유 ModelView + `admin_views` (모델이 있으면 사실상 필수 — `tests/test_admin_wiring.py` 가 강제) |

---

## 4. 요청 처리 & 트랜잭션 경계 (UnitOfWork 미사용)

UnitOfWork 패턴은 사용하지 않습니다. 트랜잭션 경계는 **쓰기 핸들러 본문**이 담당하고,
기능 의존성은 Service 구성만 합니다.

```
Router(view) → Depends(get_<name>_service) → Service(session) → Repository → DB
     ↑ commit() 은 여기서
```

```python
# app/features/<name>/dependencies/<name>_dependencies.py — 구성만 한다
async def get_<name>_service(
    session: AsyncSession = Depends(get_writer_db_session),      # 쓰기용
) -> <Name>Service:
    return <Name>Service(session)


async def get_<name>_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),   # 조회용
) -> <Name>Service:
    return <Name>Service(session)


# app/features/<name>/api/routers/v1/<name>.py — 커밋은 여기서
async def create_<name>(
    payload: <Name>Create,
    service: <Name>Service = Depends(get_<name>_service),
) -> <Name>Response:
    obj = await service.create(payload)
    response = <Name>Response.model_validate(obj)
    await service.commit()          # DTO 검증 후, 응답 반환 전 commit
    return response
```

- 뷰(view)는 HTTP 역할과 **커밋 시점 결정**을 맡습니다: 파라미터 수신 → 주입된 Service 호출
  → DTO 검증 → (쓰기면) `await service.commit()` → 반환. 실제 catalog 생성·수정도 이 순서입니다.
- 예외로 빠져나가면 세션 dependency teardown 이 `rollback()` 합니다.
- 조회 엔드포인트는 `_readonly` 의존성을 써서 `get_read_only_db_session` 을 받고 커밋하지 않습니다.
  replica가 구성되고 DB router가 켜져 있으면 읽기가 replica로 향합니다. read-only 쓰기 차단은
  flush/execute event 검사로 `DB_ROUTER_ENABLED=false`에서도 적용됩니다. 이것은 임의 SQL의
  완전한 보안 sandbox는 아닙니다.
- `Service`는 `BaseService`를, Repository는 ORM이면 `BaseRepository`, Raw이면
  `RawRepositoryBase`를 상속합니다. 두 Base는 서로 상속하지 않습니다.
- 요청 밖(백그라운드/Celery) 세션은 정식 이름 `background_db_session()` 컨텍스트(별도 풀)를 씁니다.
  `app/core/db/session.py` 끝에 남아 있는 옛 별칭들은 신규 코드에서 사용하지 않습니다
  (정식 이름 대응표: `scripts/review_gate.py` 의 `DEPRECATED_SESSION_ALIASES`).

> **왜 의존성이 아니라 핸들러인가.** 이전에는 의존성이 `yield` 이후 커밋했습니다. 그런데
> 기본 request scope의 yield dependency 종료 코드는 **응답 전송 후에** 실행되므로,
> 그곳에서 commit이 실패해도 클라이언트는 이미 `201`을 받을 수 있습니다. function scope는
> 종료 시점이 다릅니다([FastAPI 공식 설명](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)). 핸들러에서 commit하면
> 실패가 응답 코드에 정직하게 반영됩니다. 구조 증거: `tests/test_read_path_no_commit.py`.

---

## 5. Celery 태스크 — 중앙 집중 include

`app/celery/app.py`는 중앙 태스크 모듈 하나만 `include`합니다(기능별 `worker/` 미사용).

```python
celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=["app.celery.tasks"],
)
```

- 모든 기능 백그라운드 태스크는 `app/celery/tasks.py`에 `@celery_app.task`로 정의합니다.
  (예: `home.aggregate_access_stats`)
- 동기 워커에서 async 코루틴 실행: `app/celery/task.py`의 `run_async(coro)`.
- 태스크 내 DB 세션: `background_db_session()` 컨텍스트.
- API 기동은 Celery worker를 자동 실행하지 않습니다. `worker_lifecycle.py`는 init에서 상속된
  sync pool을 분리하고 shutdown에서는 worker loop를 닫습니다. API lifespan의 DB dispose
  경로와 동일한 async 정리를 worker가 실행한다고 가정하지 않습니다.

---

## 6. Alembic 마이그레이션

`migrations/env.py`는 런타임과 **같은 발견 규칙**의 `AppRegistry`를 직접 만들어 전 기능 모델을
수집합니다(`install_hooks()`는 호출하지 않음). 앱의 `models` 패키지와 `models.models` 모듈을 둘 다
import하므로 새 앱 추가 시 이 파일을 손댈 필요가 없습니다.

```python
from app.core.db.session import Base
from app.core.registry import AppRegistry
from config import db_settings

_registry = AppRegistry()
_registry.discover()
_registry.import_models()
target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)
```

`app/core/db/models_registry.py`의 `import_all_models()`는 같은 registry에 위임하는 호환 facade로,
현재 테스트(`tests/core/test_alembic_metadata.py`·`tests/core/test_migration_chain.py`)가 사용합니다.

**DB URL 우선순위** (`DatabaseSettings.ALEMBIC_URL` — `env.py`는 환경변수를 직접 읽지 않음):
1. `ALEMBIC_DATABASE_URL` 설정값 (로컬/CI 오버라이드, SQLite 등)
2. primary DSN(`MYSQL_WRITER_URL`) — 비동기 드라이버(`+aiomysql`)를 동기(`+pymysql`)로 치환

현재 revision 체인: `f4adf0ae24ea`(baseline) → `b2f1a9c0d3e4`(user 비밀번호) →
`c3d5e7a91b02`(catalog_products) → `d4e6f8b12c34`(sales_orders, head).

```bash
uv run alembic revision --autogenerate -m "add <name> model"
uv run alembic upgrade head
```

---

## 7. 환경 및 툴링

| 명령 | 설명 |
|------|------|
| `uv sync` | 의존성 설치 (가상환경 자동 생성) |
| `uv run uvicorn main:app --reload` | 개발 서버 실행 (Redis 필수, `DEBUG=true` 면 MySQL 도 필수) |
| `uv run alembic upgrade head` | DB 마이그레이션 적용 |
| `uv run python -m pytest` | 테스트 실행 (`tests/` + `app/features/*/tests/`) |
| `docker compose -f compose.test.yaml up -d --wait` → `uv run python -m pytest -m mysql` | MySQL 8.4 통합 테스트 |
| `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` | 정적 분석 |
| `uv run python -m scripts.review_gate [--group ...]` | CI 와 같은 검증 게이트 (`--list` 로 그룹 확인) |

`[tool.uv] package = false` — 루트 패키지 빌드 없이 의존성만 설치(flat layout).
Python 은 `requires-python = ">=3.12"`, 저장소 기준 인터프리터는 `.python-version` 의 3.14 입니다.

---

## 8. 변경 이력

아래는 기반 저장소 전환을 포함한 **과거 기록**입니다. 현재 등록 방식은 2절의 AppRegistry이며,
과거의 명시 include_router·중앙 Admin 목록 제거 기록을 현재 사용법으로 읽지 않습니다.

| 날짜 | 변경 내용 |
|------|----------|
| 2026-09-17 | **문서 현행화(docs/guides 이동 후)**: lifespan 이 `manage_application_resources()`(Redis PING 필수·DEBUG DDL·역순 정리)로 옮겨진 것을 §2.3 에 반영, §6 `env.py` 예시를 실제 코드(`AppRegistry` 직접 사용 + `db_settings.ALEMBIC_URL`)로 정정, 생성기 `--force`·생성물 범위, `scripts/review_gate.py`·`tests/integration/`·`compose.test.yaml`·Raw Base 파일을 폴더 트리와 §7 에 추가했다. 코드 변경 없음. |
| 2026-08-25 | **문서 현행화(F-208·F-212·F-213)**: 초기화 훅 서술을 실제 구현에 맞춰 정정했다 — `__init__.py` import-time 부수효과가 아니라 앱 `apps.py` 의 `ready()` 를 `AppRegistry.install_hooks()` 가 호출하고, `discover()` 는 부작용이 0 이다(ADR-006). 폴더 트리·결선 도식·앱 규약표·`main.py` 예시·Django 대응표·필수선택표 6곳을 함께 고쳤다. 아울러 폴더 트리 최상단의 형제 저장소 이름(`fastapi-default-project-structure/`)을 이 저장소명으로, §4 예시의 세션 alias(`get_session`·`get_read_session`)를 정식 이름(`get_writer_db_session`·`get_read_only_db_session`, INV-10)으로 바꾸고 중복된 `### 3.3` 절 번호를 정리했다. 코드 변경 없음. |
| 2026-06-23 | 기능 모델 레지스트리 아키텍처로 전환, 이 문서 최초 작성 |
| 2026-06-23 | 자동 발견 제거, `app/apps.py` 수동 등록 SSOT로 전환 |
| 2026-07-01 | **표준 FastAPI 배선으로 전환**: `AppRegistry`/`bootstrap.create_app()`/`app/apps.py` 제거, 각 앱 `__init__.py`가 `router` 공개 + `main.py`가 명시 `include_router`로 취합. |
| 2026-08-11 | **`app/features/` 명칭 확정 + SQLAdmin 소유권을 기능으로 이전**: 폴더·import·문서 참조 70개 파일 일괄 정정. 과거 중앙 관리자 패키지 삭제 — ModelView 는 모델과 같은 폴더에 있어야 컬럼 변경이 함께 눈에 들어오고 기능 단위 복사·삭제 시 따라온다. `app/features/<name>/admin.py` 가 ModelView 와 `admin_views` 를 소유하고, 신설 `app/features/admin.py` 가 **명시 import** 로 `ADMIN_VIEWS` 에 취합한다(과거 `getattr(module, "admin_views", [])` 관용 수집은 빈 `admin.py` 를 무신호로 건너뛰어 ADMIN-1 을 낳았으므로 복원하지 않음). 회귀 가드 `tests/test_admin_wiring.py` 에 "모델을 가진 기능은 자기 `admin.py` 를 갖는다" 검사 추가. C-7 자격증명 비노출·생성차단 정책과 공개 API 경로·응답 스키마 불변. |
| 2026-08-11 | **문서 드리프트 정정**: §4 와 README 가 P1-3 이전의 "의존성이 `yield` 후 커밋" 을 계속 설명하고 있었다(코드는 이미 핸들러 커밋). §4 예시를 실제 코드(쓰기/조회 의존성 분리 + 핸들러 `await service.commit()`)로 교체하고, `BaseService` 독스트링도 같이 정정. 아울러 재구조화 잔재 정리 — `tests/features/` 잔류분을 `app/features/<name>/tests/` 로 통합, 이동 중 겹친 디렉터리 레벨과 빈 `tests/scripts/` 제거. |
| 2026-08-11 | **Django 배선 제거 (구조는 vertical slice 유지)**: 옛 중앙 목록 순회 → 명시 `include_router`; 기능별 `admin.py` 관용 수집(`getattr(..., "admin_views", [])`) → 중앙 `app/features/admin.py`의 명시 import(`ADMIN_VIEWS`+`register_admin`); `scripts/new_app.py` 제거. 폴더는 실제 코드 기준 `app/features/` 를 유지한다. 모델 등록은 `models_registry` 디렉터리 스캔 유지. 공개 API 경로·응답 스키마·SQLAdmin 보안 정책 불변. |
| 2026-08-11 | **문서 정합성 재정리**: 삭제된 심화·리팩터링 문서 참조, 존재하지 않는 과거 모듈·관리자 경로 참조, 제거된 중앙 목록 설명을 실제 코드 기준으로 정정. |
| 2026-08-12 | **Django 스타일 앱 자동 등록 도입**: 기반 저장소 `fastapi-default-project-structure@a980b71` 을 기준선으로 삼고 자동 등록만 얹었다. 신설 `app/core/registry.py` 의 `AppRegistry` 가 `app/features/*` 를 발견해 라우터(`<name>_router` → `/api`)·모델·`admin_views` 를 결선한다. `main.py` 의 명시 `include_router` 여섯 줄과 `app/features/admin.py` 의 중앙 `ADMIN_VIEWS` 목록 제거, `models_registry` 는 자체 스캔을 버리고 registry 위임 facade 로, `migrations/env.py` 는 런타임과 **같은** registry 를 쓴다. 과거 관용 수집의 실패(ADMIN-1)를 되풀이하지 않도록 "파일 부재는 선택, 잘못된 계약은 오류" 를 `AppContractError` 로 고정했다 — 모듈 내부 import 오류는 원인을 보존해 다시 올리고, 잘못된 export·중복 등록은 기동을 멈춘다. `scripts/new_app.py`(Django `startapp` 대응, 이름 검증·경로 이탈·덮어쓰기 방지) 재도입. 공개 API 경로 18개·ORM 테이블 5개·SQLAdmin 뷰 5개·설정 키 inventory 는 기준선과 실측 일치하며, `ADMIN=false` 에서 sqladmin 미로드 계약도 유지된다. |
