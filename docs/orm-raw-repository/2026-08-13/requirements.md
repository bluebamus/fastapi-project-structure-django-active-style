<!-- generated-by: gsd-doc-writer -->
# ORM/Raw Repository 고도화 요구 명세서

## 1. 문서 정보

| 항목 | 값 |
|---|---|
| 문서 목적 | ORM 및 Raw SQL 데이터 접근 방식의 구조·동작·품질 요구사항 정의 |
| 적용 프로젝트 | `fastapi-project-structure-django-active-style` |
| 기준 구조 | `AppRegistry` 자동 발견·결선 및 Dependency → Service → Repository 흐름 |
| 관련 계획서 | `docs/orm-raw-repository/2026-08-13/development-plan.md` |
| 관련 지침서 | `docs/orm-raw-repository/2026-08-13/workflow-guide.md` |
| 상태 | 코드 재검수 완료 요구사항 기준선 (`pytest --collect-only`: 271 tests) |

## 2. 목표

본 작업은 현재 프로젝트의 FastAPI 워크플로우를 유지하면서 다음 두 데이터 접근 방식을
일관된 구조로 제공해야 한다.

1. SQLAlchemy ORM 모델 기반 CRUD 및 도메인 조회
2. SQLAlchemy `text()` 기반 Raw SQL 조회 및 변경

두 방식은 Repository 구현만 달라야 하며 다음 항목은 동일해야 한다.

- Dependency Injection과 객체 조립
- Service 유스케이스 실행
- read-only/writer DB session 선택
- 트랜잭션 경계
- Pydantic 입력·응답 검증
- 버전별 라우터 구성과 `AppRegistry` 자동 결선
- OpenAPI/Scalar 문서 품질
- 예외 처리, 테스트 및 정적 검사 기준

## 3. 용어

| 용어 | 정의 |
|---|---|
| View | FastAPI path operation 함수. HTTP 계약과 유스케이스 호출을 담당한다. |
| Dependency | FastAPI `Depends`로 세션과 Service를 생성·조립하는 함수다. |
| Service | 비즈니스 규칙과 유스케이스 순서를 담당한다. |
| Repository | ORM 또는 Raw SQL 데이터 접근을 담당한다. |
| ORM Base | `CRUDBase`와 이를 상속하는 `BaseRepository` 계층이다. |
| Raw Base | `RawCRUDBase`와 이를 상속하는 `RawRepositoryBase` 계층이다. |
| DTO | 외부 요청·응답 계약을 표현하는 Pydantic 모델이다. |
| 쓰기 View | DB 상태를 변경하는 POST/PUT/PATCH/DELETE path operation이다. |
| 조회 View | DB 상태를 변경하지 않는 GET/HEAD path operation이다. |
| AppRegistry | `app/features` 직계 하위 앱을 알파벳순으로 발견하고 같은 목록으로 모델·라우터·Admin을 결선하는 단일 출처다. |
| AppModule | 발견된 앱 하나의 패키지, `/api` prefix 및 선택 구성요소 계약을 표현한다. |

## 4. 요구사항 해석 및 보강 결정

### 4.1 View에서 비즈니스 코드 실행

원 요구사항의 “비즈니스 코드는 View에서 실행한다”는 다음 의미로 확정한다.

> View는 Dependency로 주입받은 Service의 비즈니스 유스케이스를 호출하여 실행한다.
> 비즈니스 규칙 자체는 Service에 작성하고 SQL은 Repository에 작성한다.

View에 직접 작성할 수 있는 코드는 다음으로 제한한다.

- HTTP 파라미터와 요청 본문 수신
- Service 유스케이스 호출
- 쓰기 성공 후 응답 전 commit 호출
- 반환값의 Pydantic 응답 변환
- HTTP 상태와 OpenAPI 메타데이터 선언

### 4.2 공통 모델 상속

모든 ORM 모델은 `Base` 계층을 사용해야 하지만 모든 테이블에 동일한 컬럼을 강제하지
않는다. 공통 필드는 작은 mixin으로 조합한다.

- 일반 변경 가능 엔티티: UUID PK + created/updated timestamp
- 생성 후 불변 로그: UUID PK + created timestamp
- 외부 시스템 PK 사용 테이블: 해당 PK 정책을 명시적으로 예외 처리

### 4.3 Scalar 문서의 계약 출처

ORM 모델은 DB 매핑 계약이며 Scalar API 문서의 직접 계약이 아니다. Scalar 문서는
FastAPI View와 Pydantic DTO가 생성한 OpenAPI schema를 기준으로 한다.

- ORM 응답: ORM 객체 → `from_attributes=True` Pydantic 응답 DTO
- Raw 응답: `RowMapping` → 명시적 `dict` 변환 → Pydantic 응답 DTO
- ORM 컬럼 comment는 Pydantic 설명을 대체하지 않는다.

### 4.4 Raw SQL 사용 원칙

Raw SQL은 ORM을 우회하기 위한 일반 기본값이 아니다. 다음 상황에서 선택한다.

- 복잡한 집계, 윈도 함수, CTE 또는 DB 최적화 쿼리
- ORM 표현보다 SQL 계약이 더 명확한 리포트
- 실행 계획을 기준으로 관리해야 하는 성능 민감 조회
- 기존 DB의 저장 프로시저 또는 DB 전용 기능 연계

일반 단일 테이블 CRUD는 ORM Repository를 우선한다.

### 4.5 JWT 인증 적용 범위

프로젝트의 기본 인증 방식은 JWT를 전제로 하지만 이번 ORM/Raw Repository 및 lifecycle
고도화 작업에는 JWT 인증 기능의 신규 적용이나 확장을 포함하지 않는다. 현재 인증 동작은
호환성 기준선으로만 보호한다.

현재 access/refresh token 발급·만료·타입 검증과 refresh 재발급은 구현된 호환성
기준선이다. 영속적 rotation/reuse detection, revoke/logout, 권한 모델과 보안 저장 방식만
별도의 후속 요구 명세에서 정의한다.

### 4.6 Redis 적용 범위

API용 Redis client, cache, session 저장소와 readiness 연계는 이번 작업에 포함하지 않고 JWT와
마찬가지로 후속 요구 명세로 분리한다. 기존 Celery broker/backend의 Redis 설정과 동작은
변경하지 않는다.

### 4.7 Active-style 자동 결선 기준선

이 프로젝트는 명시적 중앙 목록이 아니라 `app/core/registry.py`의 컨벤션 기반 자동 발견을
이미 사용한다. 런타임은 `main.py`에서 하나의 `AppRegistry`를 생성해 `discover()`와
`import_models()`를 실행한 뒤, 동일 인스턴스로 `install_routers(app)`와
`register_admin(app, engine, registry)`를 수행한다.

- 앱 패키지: `app/features/<name>/`
- 라우터: `app/features/<name>/api/routers/router.py`의 `<name>_router`
- 모델: `app/features/<name>/models` 패키지
- Admin: `app/features/<name>/admin.py`의 `admin_views: list[type]`
- 선택 모듈 부재는 허용하지만, 모듈 내부 import 실패나 export 계약 위반은 기동 실패다.
- 현재 lifecycle의 `create_db_tables()` 경로는 `import_all_models()`를 통해 중복 재탐색한다.
  목표 상태에서는 runtime 내부의 모델·라우터·Admin·lifecycle이 `main.py`의 같은 registry
  결과를 재사용한다. 별도 Alembic 프로세스는 동일한 발견 규칙으로 자체 registry를 한 번만
  구성한다.
- 현재 기능 패키지의 일부 `__init__.py`는 모델·라우터를 import하고 `home`은 import 시점에
  sink/DB 모듈까지 초기화한다. 따라서 `discover()` 자체가 무부작용이라는 전제는 현재 코드와
  다르다. Runtime gate의 선행 작업으로 기능 `__init__.py`를 경량화하고, 모델·라우터 import는
  각각 `import_models()`/`load_router()`에서만 일어나게 한다. init hook은 명시적·멱등적으로
  호출하며 `discover()` 단독 실행 전후의 metadata와 장기 자원 수가 같음을 테스트한다.

### 4.8 `fastapi-default-project-structure` 재검수 추가 결정

2026-08-18에 참조 저장소 commit `db49e9c8d7106b026e2797f7356a0e1d1189056f`를 코드와
CI 설정부터 다시 검수했다. 로컬에서 MySQL 8.4가 실제 실행 가능한 상태에서는 전체 373건과
`pytest -m mysql`의 선택된 6건이 모두 통과했다. 그러나 참조 저장소의
`.github/workflows/ci.yml`은 MySQL service나 Compose 기동 단계가 없으므로 깨끗한 GitHub runner에서는
6건이 skip되고, 바로 뒤의 skip 0 검사에서 실패한다. 따라서 결함 원장의 “CI는 항상 MySQL을
기동한다”는 서술은 구현 증거로 인정하지 않는다. 같은 commit의 현재 lock 환경에서
`ruff format --check`도 Alembic migration 3개를 재포맷 대상으로 판정하므로 “전 품질 gate 통과”
기록은 명령·도구 버전·실행 artifact로 다시 증명해야 한다.

추가 결정:

- MySQL 검수는 service 기동, health 확인, 선택된 테스트 수, 실제 실행 수와 teardown까지 하나의
  CI 계약으로 구현한다. `pytest -m mysql`이 비-MySQL 테스트를 deselect하는 것은 정상이며,
  이 selector의 `deselected` 수 자체를 실패 조건으로 사용하지 않는다.
- 전역 HTTP/App/validation 예외 처리도 Repository와 같은 비밀정보 비노출 계약을 적용한다.
  `exc.detail`, `str(exc)`, validation input 또는 exception traceback을 응답이나 일반 운영 로그에
  그대로 기록하지 않는다.
- 운영 DB 연결은 인증서 검증 TLS와 최소권한 계정을 사용한다. migration, writer, reader 계정의
  권한을 분리하고 API runtime 계정에 DDL 권한을 주지 않는다.
- 프록시 전달 헤더는 신뢰한 proxy에서 온 경우에만 사용한다. 임의 클라이언트가 보낸
  `X-Forwarded-For`/`X-Real-IP`를 접속 기록의 실제 IP로 신뢰하지 않는다.
- catalog/reports 예제와 `/ready`는 인증·네트워크 노출 정책을 명시한다. 예제 API를 실제 서비스에
  배포할 때 인증/권한 없이 공개하지 않고, `/ready`는 ingress의 일반 공개 경로에서 제외한다.
- Celery의 기존 JSON-only serializer/accept-content 계약을 회귀 보호하고 pickle/yaml 수용을
  금지한다.
- Bandit만으로 의존성·CI 공급망 위험을 승인하지 않는다. lockfile 기반 취약점 검사, secret scan,
  GitHub Action commit SHA 고정과 MySQL image digest 정책을 별도 gate로 둔다.

## 5. 우선순위

| 등급 | 의미 |
|---|---|
| P0 | 구현 및 배포 전에 반드시 충족해야 하는 구조·보안·정합 요구사항 |
| P1 | 이번 고도화 범위에서 반드시 제공해야 하는 기능·테스트 요구사항 |
| P2 | 호환성을 유지하면서 점진적으로 적용할 품질 개선 요구사항 |

## 6. 아키텍처 요구사항

### AR-001 공통 계층 흐름 [P0]

ORM과 Raw View는 모두 다음 호출 흐름을 준수해야 한다.

```text
View -> Dependency -> Service -> Repository -> AsyncSession
```

수용 기준:

- View가 `AsyncSession`을 직접 주입받지 않는다.
- View와 Service가 `session.execute()`를 직접 호출하지 않는다.
- Repository가 FastAPI `Request`, `Response`, `Depends`를 import하지 않는다.

### AR-002 공통 모듈 위치 [P0]

모든 기능에서 재사용하는 DB, middleware, model base, repository base, service base와 태그
메타데이터는 `app/core` 아래에 둬야 한다.

수용 기준:

- 기능 간 상대 기능 import로 공통 코드를 공유하지 않는다.
- 도메인 SQL과 도메인 규칙을 `app/core`에 두지 않는다.

### AR-003 ORM/Raw Base 분리 [P0]

ORM Base와 Raw Base는 각각 독립적인 상속 계층이어야 한다.

```text
BaseRepository -> CRUDBase
RawRepositoryBase -> RawCRUDBase
```

수용 기준:

- `RawRepositoryBase`가 `BaseRepository`를 상속하지 않는다.
- 하나의 Base 클래스가 ORM 모델과 Raw row를 동시에 반환하지 않는다.
- 공유되는 것은 `AsyncSession`, 공통 예외와 로깅 정책뿐이다.

### AR-004 AppRegistry 기반 라우터 자동 결선 [P0]

라우터는 다음 컨벤션과 결선 순서를 따라 자동 등록해야 한다.

```text
v1/<view>.py -> api/routers/router.py의 <name>_router
             -> AppRegistry.install_routers(app) -> /api
```

수용 기준:

- 라우터 모듈이 있는 앱은 이름과 일치하는 `<name>_router: APIRouter`를 공개한다.
- `AppRegistry.discover()`는 `app/features` 직계 하위의 비-underscore 패키지를 알파벳순으로
  발견한다.
- `main.py`에는 기능별 import 또는 `app.include_router(feature.router, ...)` 중앙 목록이 없다.
- `install_routers()`는 마지막 `discover()` 결과만 사용하며 스스로 재탐색하지 않는다.
- 선택 라우터 모듈이 없으면 건너뛰고, 모듈은 있으나 export가 없거나 타입이 틀리면
  `AppContractError`로 기동을 중단한다.
- 새 앱의 라우터가 자동 마운트되고 앱 제거 시 함께 제거되는지 테스트가 검증한다.

### AR-005 Lifespan Resource Manager [P0]

애플리케이션 프로세스 수명 자원의 생성과 해제는
`app/core/resources.py`의 `manage_application_resources(app, registry)` 한 곳에서 관리해야 한다.

수용 기준:

- `main.py`의 lifespan은 resource manager context를 호출하고 yield하는 조립만 담당한다.
- startup과 shutdown 로직이 기능 모듈 또는 여러 event handler에 분산되지 않는다.
- 실제 생성된 자원을 `app.state.resources`에서 명시적으로 참조할 수 있다.
- cleanup 완료 후 `app.state.resources`가 닫힌 자원을 참조하지 않는다.
- `main.py`에서 이미 `discover()`와 `import_models()`를 완료한 `registry` 인스턴스를 전달한다.
- Resource Manager는 새 `AppRegistry`를 만들거나 `discover()`/`import_models()`를 다시 호출하지
  않는다.
- 기존 AppRegistry 자동 결선 계약을 유지하면서 자원 생성·해제 순서는 명시적으로 관리한다.
- fallible `start()` 뒤 cleanup을 등록하지 않는다. 각 자원은 자체 async context manager로
  시작과 실패 cleanup을 캡슐화하거나, start 전에 안전한 멱등 cleanup을 등록한다.
- 현재 engine은 모듈 import 시 생성되므로 1차 단계의 Resource Manager는 생성자가 아니라
  명시적 종료 소유자다. 추후 engine factory로 전환할 때에만 생성 소유권도 함께 옮긴다.

### AR-006 자원 소유권 [P0]

Resource Manager는 FastAPI API 프로세스가 생성하고 소유한 장기 수명 자원만 관리해야 한다.

수용 기준:

- DB writer, reader, background engine pool을 shutdown에서 dispose한다.
- DB engine 정의가 session 모듈에 남더라도 shutdown 소유자는 Resource Manager 하나다.
- 요청별 `AsyncSession`은 Dependency가 닫는다.
- Celery worker의 broker/backend 연결을 FastAPI lifespan이 닫지 않는다.
- shutdown에서 DB table drop을 실행하지 않는다.
- engine별 dispose는 독립적으로 시도하고 실패를 집계한다. 하나의 dispose 실패가 다른
  writer/reader/background engine cleanup을 막지 않는다.

### AR-007 모델 기반 테이블 생성 조건 [P0]

startup은 모든 모델 모듈을 import한 후 `Base.metadata.tables`의 실제 테이블 수를 기준으로
테이블 자동 생성 여부를 결정해야 한다.

수용 기준:

- metadata table 수가 0이면 DB 연결과 `create_all()`을 시도하지 않는다.
- metadata table 수가 1 이상이고 개발 자동 생성 정책이 활성화된 경우만 생성한다.
- 운영 환경에서는 모델이 있어도 `create_all()`을 실행하지 않고 Alembic을 사용한다.
- 개발 자동 생성은 명시적 설정에서 단일 worker일 때만 허용한다. 다중 worker에서는 startup
  DDL을 거부하고 배포 전 Alembic 또는 별도 init job을 사용한다.
- 모델 파일 존재 여부만으로 생성 여부를 판정하지 않는다.
- 동일 startup에서 모델 discovery/import를 중복 실행하지 않고, `main.py`가 전달한 registry의
  모델 import 결과를 재사용한다.

### AR-008 실패 안전 cleanup [P0]

정상 shutdown뿐 아니라 startup 중간 실패에서도 이미 생성된 자원을 정리해야 한다.

수용 기준:

- startup 전체가 `try/finally` 또는 동등한 async context manager cleanup으로 보호된다.
- 하나의 cleanup 실패 때문에 다른 자원 cleanup이 생략되지 않는다.
- 종료 순서는 background task drain, DB engine dispose, logging queue flush/listener stop이다.
- 자원별 shutdown timeout이 존재한다.

### AR-009 Background task 완전 종료 [P0]

`BackgroundTaskRunner`는 shutdown timeout 후에도 task를 실행 상태로 남겨서는 안 된다.

수용 기준:

- timeout 전 완료된 task 결과를 회수한다.
- timeout 후 pending task에 `cancel()`을 호출한다.
- 취소한 task를 `asyncio.gather(..., return_exceptions=True)` 또는 동등한 방식으로 await한다.
- cancellation이 session context의 rollback/close를 실행할 기회를 보장한다.
- drain 완료 후 추적 task 집합이 비어 있다.
- 모든 task 종료 후 DB를 dispose하고 logging listener를 마지막에 닫는다.

### AR-010 Celery worker async 자원 종료 [P0]

Celery worker process가 소유한 영속 event loop와 DB pool은 worker shutdown signal에서
명시적으로 종료해야 한다.

수용 기준:

- Celery 동기 task wrapper 내부의 DB 호출은 기존 async Service/Repository를 사용한다.
- worker process별 event loop를 재사용한다.
- 지원 pool은 prefork로 제한한다. worker 전용 engine/sessionmaker factory를 두고
  `worker_process_init`에서 부모로부터 상속된 pool을 폐기한 뒤 child handle을 생성·재바인딩한다.
- worker shutdown에서 DB engine/pool을 loop가 살아 있는 동안 dispose한다.
- `shutdown_asyncgens()` 실행 후 event loop를 close한다.
- 종료 후 global loop reference를 `None`으로 초기화한다.
- FastAPI lifespan과 Celery worker cleanup의 소유권이 섞이지 않는다.

## 7. ORM 모델 요구사항

### ORM-MDL-001 공통 Declarative Base [P0]

모든 ORM 모델은 `app/core/models/models_base.py`에서 정의한 `Base` 계층을 사용해야 한다.

수용 기준:

- 독립적인 `DeclarativeBase`가 기능 폴더에 존재하지 않는다.
- 모든 모델이 Alembic과 `Base.metadata`에 등록된다.

### ORM-MDL-002 공통 필드 mixin [P1]

UUID와 timestamp를 반복 선언하지 않고 공통 mixin을 사용해야 한다.

수용 기준:

- `UUIDPrimaryKeyMixin`, `CreatedAtMixin`, `UpdatedAtMixin`으로 책임을 분리한다.
- 반복 조합용 abstract convenience base `UUIDTimestampModel`(UUID+created+updated)과
  `UUIDCreatedModel`(UUID+created)을 제공해 예제와 구현의 이름을 일치시킨다.
- 변경 가능 엔티티는 세 Mixin 조합을, 불변 로그는 UUID와 created 조합만 사용한다.
- 기존 모델 전환 후 Alembic schema diff가 발생하지 않는다.
- 불변 로그 모델은 불필요한 `updated_at`을 강제받지 않는다.

### ORM-MDL-003 PK 타입 계약 [P1]

ORM Repository의 PK 타입 가정을 제네릭 계약으로 표현해야 한다.

수용 기준:

- `BaseRepository[ModelT, PrimaryKeyT]`를 정식 타입 계약으로 사용하고 `pk_attr`을
  `InstrumentedAttribute[PrimaryKeyT]`로 연결한다.
- 기존 문자열 UUID Repository는 `BaseRepository[ModelT, str]`로 명시한다.
- 이번 범위의 공통 Base는 단일 컬럼 PK만 지원한다. 복합 PK는 명시적 기능 Repository로
  분리하고 공통 Base에 전달하면 타입/실행 검증에서 거부한다.
- 기본 `pk_attr`은 `id`이며 다른 이름의 단일 PK 모델은 생성자에서 명시적으로 제공한다.
- 잘못된 모델/PK 조합을 거부하는 mypy negative fixture를 둔다.

### ORM-MDL-004 컬럼 계약 [P1]

모델은 DB 제약과 Python 타입을 일치시켜야 한다.

수용 기준:

- nullability, unique, index, FK와 `Mapped` 타입이 모순되지 않는다.
- DB에서 의미가 있는 컬럼에는 필요에 따라 comment를 제공한다.
- API 필드 설명은 Pydantic DTO에 별도로 정의한다.

### ORM-MDL-005 모델 발견 및 Admin 계약 [P0]

신규 ORM 모델은 AppRegistry 모델 import와 SQLAdmin 자동 결선 계약을 함께 충족해야 한다.

수용 기준:

- 모델은 `app/features/<name>/models` 아래에 두고 공통 `Base`를 사용하여
  `Base.metadata`와 Alembic `target_metadata`에 자동 포함된다.
- 모델을 가진 신규 기능은 `app/features/<name>/admin.py`를 소유하고
  `admin_views: list[type]`에 해당 모델의 `ModelView`를 정확히 하나 노출한다.
- `admin.py`가 없으면 Registry가 선택 구성요소로 건너뛸 수 있으므로, 모델 기능의 Admin 누락은
  `tests/test_admin_wiring.py`와 `tests/core/test_admin_views.py`가 별도로 실패시킨다.
- 같은 `ModelView` 중복 등록, `admin_views` 누락·비-list·비-`ModelView` 항목은
  `AppContractError`로 거부한다.
- 비밀번호 등 비밀 컬럼은 목록·상세·폼·내보내기 모두에서 제외하고, 모델별 생성·수정·삭제
  정책을 명시적으로 검증한다.

## 8. ORM Repository 요구사항

### ORM-REP-001 CRUD primitive 책임 [P0]

`crud_base.py`는 ORM 영속성 primitive만 제공해야 한다.

필수 책임:

- session 저장
- PK 조회
- entity add/delete
- flush/refresh

금지 책임:

- commit/rollback
- HTTP 예외 생성
- eager loading과 도메인 전용 쿼리

### ORM-REP-002 안정적인 공개 CRUD [P1]

`repository_base.py`는 일반 모델에서 반복되는 최소 공개 CRUD를 제공해야 한다.

필수 API:

- create
- get by ID 및 not-found 변형
- pagination list
- count와 exists
- update by ID
- delete by ID

이 목록이 Base의 최소 정식 공개 API다. 기존 이름은 호환 wrapper로만 유지한다.

수용 기준:

- 공개 메서드 이름과 반환 타입이 타입 검사된다.
- 모든 ORM 기능 Repository가 이 Base를 상속한다.
- 기존 API 응답과 상태 코드가 유지된다.
- update는 먼저 엔티티를 조회하고 PK 및 알려지지 않은 필드 변경을 거부한 뒤, 제공된 필드만
  `setattr`하고 flush/refresh한다. 빈 PATCH는 존재 확인 후 no-op으로 처리한다.
- delete도 먼저 엔티티를 조회한 뒤 해당 인스턴스를 삭제한다. 조건 기반 bulk update/delete는
  별도 API이며 단건 CRUD에 섞지 않는다.

### ORM-REP-003 입력 불변성 [P0]

Repository는 호출자가 전달한 `dict`를 변경해서는 안 된다.

수용 기준:

- create/bulk create/update 호출 후 원본 입력과 호출 전 값이 동일하다.
- ID 기본값은 모델 default 또는 복사된 데이터에서 처리한다.
- 입력 불변성 테스트가 존재한다.

### ORM-REP-004 존재 확인 최적화 [P2]

존재 확인은 전체 row count보다 SQL `EXISTS`를 사용해야 한다.

수용 기준:

- `exists`, `exists_by`가 boolean 존재 확인 SQL을 생성한다.
- 반환 타입은 항상 `bool`이다.

### ORM-REP-005 고급 쿼리 분리 [P1]

eager loading, join, partial column, batch와 같은 고급 쿼리는 실제 공통성이 확인된 경우만
Base에 둬야 한다.

수용 기준:

- 도메인 특화 관계명과 컬럼명이 Base에 없다.
- 문자열 관계·컬럼 접근을 신규 public API에서 확대하지 않는다.
- 기능별 쿼리는 해당 기능 Repository의 명시적 메서드가 소유한다.
- 두 개 이상의 실제 기능에서 같은 구현이 확인된 경우에만 별도 Mixin으로 추출한다.

### ORM-REP-006 예외 변환 일관성 [P0]

모든 create/update/delete/bulk 경로는 동일한 DB 예외 변환 정책을 사용해야 한다.

수용 기준:

- 무결성 충돌은 프로젝트 중복 또는 DB 예외로 변환된다.
- 예상하지 못한 SQLAlchemy 오류는 `DatabaseException`으로 변환된다.
- 원본 예외가 exception chaining으로 보존된다.
- 민감한 SQL 파라미터를 사용자 응답에 포함하지 않는다.
- ORM/Raw/commit 경로 모두 외부 응답에는 안정적인 error code, model/query/operation과 안전한
  constraint 분류(duplicate/FK/not-null/check)만 제공한다. SQL, DSN, driver 원문과 params는
  로그 및 응답에 노출하지 않는다.

### ORM-REP-007 점진적 호환성 [P1]

기존 `BaseRepository` public 메서드는 사용처 조사 없이 즉시 삭제하지 않는다.

수용 기준:

- 메서드별 사용처 목록이 작성된다.
- 호환 wrapper → 호출부 전환 → 제거 순서로 변경한다.
- 전환 중 현재 수집 기준선인 271개 테스트와 API contract가 유지된다.

## 9. Raw Repository 요구사항

### RAW-REP-001 RawCRUDBase 제공 [P0]

`app/core/repositories/raw_crud_base.py`를 추가해야 한다.

필수 protected API:

- `_fetch_one(TextClause, params) -> RowMapping | None`
- `_fetch_all(TextClause, params) -> Sequence[RowMapping]`
- `_fetch_scalar(TextClause, params) -> object | None`
- `_execute(TextClause, params) -> int | None`

수용 기준:

- 문자열 SQL보다 `TextClause` 입력을 기본 계약으로 사용한다.
- 결과 형태별 테스트가 존재한다.
- commit/rollback을 수행하지 않는다.
- `fetch_one`은 `mappings().one_or_none()`, `fetch_all`은 `mappings().all()`, `fetch_scalar`는
  `scalar_one_or_none()`을 사용한다. 단건 API의 복수 행은 묵인하지 않고 오류다.
- scalar의 0행과 SQL `NULL`은 모두 `None`이다. 구분이 필요한 쿼리는 `fetch_one`을 사용한다.
- `execute`는 DML 전용이며 driver가 rowcount를 제공하지 않으면 `None`을 반환한다. `-1`을
  성공 건수로 공개하거나 bool로 축약하지 않는다.

### RAW-REP-002 RawRepositoryBase 제공 [P0]

`app/core/repositories/raw_repository_base.py`를 추가해야 한다.

필수 책임:

- RawCRUDBase primitive의 안정적인 public API 제공
- SQLAlchemy 예외의 프로젝트 예외 변환
- keyword-only `query_name`을 받는 쿼리 이름 중심 로깅
- 민감 파라미터 미노출

수용 기준:

- 기능 Raw Repository가 이 Base를 상속한다.
- 도메인 SQL은 Base가 아닌 기능 Repository에 존재한다.
- 기능 Repository가 `feature.use_case` 형식의 안정적인 `query_name` 상수를 전달한다.
- Base는 `query_name`, 소요 시간과 성공/실패만 기록하고 SQL 본문과 params를 기록하지 않는다.

### RAW-REP-003 named parameter 강제 [P0]

모든 외부 값은 named bind parameter로 전달해야 한다.

허용 예:

```python
text("SELECT * FROM sales_orders WHERE user_id = :user_id")
```

금지 예:

```python
text(f"SELECT * FROM sales_orders WHERE user_id = '{user_id}'")
```

수용 기준:

- 사용자 입력을 SQL 문자열에 직접 보간한 코드가 없다.
- 보안 테스트 또는 정적 검사로 대표 injection 입력을 검증한다.
- SQL 본문은 Repository가 소유한 상수로 정의하고 multi-statement와 요청 기반 동적 SQL 생성을
  금지한다. `IN` 목록은 `bindparam(expanding=True)`를 사용한다.

### RAW-REP-004 식별자 allowlist [P0]

테이블명, 컬럼명, 정렬 방향처럼 bind parameter를 사용할 수 없는 식별자는 코드가 소유한
allowlist에서 선택해야 한다.

수용 기준:

- 요청값이 SQL 식별자로 직접 사용되지 않는다.
- 허용하지 않은 정렬 키와 방향은 validation error가 된다.

### RAW-REP-005 결과 타입 및 DTO 경계 [P0]

Raw Repository는 `RowMapping` 또는 scalar를 반환하고 Service가 Pydantic DTO로 검증해야
한다.

수용 기준:

- View가 `Row`, `RowMapping`, `CursorResult`를 직접 반환하지 않는다.
- Raw 결과 컬럼 alias와 DTO 필드가 일치한다.
- 누락 또는 잘못된 타입의 결과가 Pydantic 검증에서 탐지된다.

### RAW-REP-006 DB 방언 관리 [P1]

MySQL 전용 SQL은 명시적으로 관리하고 해당 DB에서 통합 검증해야 한다.

수용 기준:

- MySQL 전용 함수와 문법에 주석 또는 문서 표시가 있다.
- SQLite 테스트 통과만으로 MySQL SQL의 정확성을 승인하지 않는다.
- 최소 한 개의 MySQL 통합 테스트 또는 실행 계획 검증 절차가 있다.
- 로컬과 CI가 동일한 `compose.test.yaml` MySQL service 구성을 사용한다.

### RAW-REP-007 Raw DML 지원 [P1]

Raw update/delete/insert를 사용할 때도 ORM과 같은 트랜잭션 규칙을 적용해야 한다.

수용 기준:

- Raw Repository는 affected row count만 반환하고 commit하지 않는다.
- 쓰기 View가 응답 전에 한 번 commit한다.
- 현재 `get_read_session()`의 DML 차단은 routing session의 `get_bind()`에서 동작하므로
  `DB_ROUTER_ENABLED=false`인 기본 단일 엔진 구성에서는 실효 차단되지 않는다는 기준선을
  테스트로 고정한다.
- 완료 시점에는 `DB_ROUTER_ENABLED` 값과 무관하게 read-only Dependency로 획득한 session의
  Raw DML이 `ReadOnlyRoutingError` 또는 동등한 전용 예외로 차단되어야 한다.
- 라우터 활성 구성만 검사하는 테스트로 완료 처리하지 않고, 최소한
  `DB_ROUTER_ENABLED=false`와 `true` 두 구성을 모두 검증한다.
- read-only 검사는 Raw `_execute()`에만 두지 않고 모든 session 실행 경계에 중앙 적용한다.
  fetch API로 전달한 TextClause DML, 직접 `session.execute()`, `SELECT ... FOR UPDATE`, 저장
  프로시저와 multi-statement 우회도 거부한다.
- `session.info` 표식은 애플리케이션 방어선이지 보안 경계가 아니다. 배포 환경에서는 read-only
  DB 자격증명 또는 transaction read-only 설정을 최종 방어선으로 사용한다.
- public `is_read_only()`/`assert_writable()`을 한 곳에서 제공하고 ORM/Core/Raw가 공유한다.
- 선두 키워드만 보는 판별기는 `WITH ... DELETE/UPDATE` 같은 CTE DML을 읽기로 오판할 수 있다.
  분류할 수 없는 TextClause는 writer로 보내고 read-only session에서는 default-deny한다.
  지원 Raw SELECT/DML 문법의 허용 범위를 문서화하고 CTE DML, leading comment, multi-statement,
  `FOR UPDATE`, `CALL`, DDL을 회귀 테스트에 포함한다. SQL parser 없이 지원 범위를 넓히지 않는다.

## 10. Dependency 및 트랜잭션 요구사항

### TX-001 Dependency 조립 책임 [P0]

Dependency는 세션을 선택하고 Service와 Repository 객체를 조립해야 한다.

수용 기준:

- Dependency가 Service 유스케이스를 실행하지 않는다.
- Dependency가 commit하지 않는다.
- teardown commit 패턴을 사용하지 않는다.

### TX-002 조회 세션 [P0]

조회 View는 `get_read_only_db_session` 기반 read-only Service Dependency를 사용해야 한다.

수용 기준:

- GET/HEAD 경로가 `get_writer_db_session` 또는 `get_routed_db_session`을 사용하지 않는다.
  단, 강한 일관성이 필요한 승인된 예외는 사유와 함께 allowlist로 관리한다.
- 조회 경로의 commit 호출 횟수는 0회다.
- DB Router 활성화 시 reader로 라우팅된다.
- DB Router 비활성화 시에도 read-only 표식이 보존되고 ORM flush 및 Core/Raw
  INSERT·UPDATE·DELETE가 실효 차단되어야 한다. 현재 기준선은 이 조건을 충족하지 않으므로
  ORM/Raw delivery gate 전에 보완한다.

### TX-003 쓰기 세션 [P0]

DB 변경 View와 조회 후 쓰기 유스케이스는 `get_writer_db_session` 기반 Service
Dependency를 사용해야 한다.

수용 기준:

- POST/PUT/PATCH/DELETE의 DB 쓰기가 read session으로 실행되지 않는다.
- 첫 SELECT부터 primary writer에 고정되어 replica lag의 영향을 받지 않는다.
- DB를 쓰지 않는 POST는 이유가 기록된 allowlist로 관리한다.

### TX-004 응답 전 commit [P0]

쓰기 성공은 View 본문에서 응답 반환 전에 정확히 한 번 commit해야 한다.

수용 기준:

- `await service.commit()`이 View의 성공 경로에 존재한다.
- commit 실패 시 클라이언트가 2xx를 받지 않는다.
- 예외 경로는 commit 0회다.
- Repository와 Dependency에 commit 호출이 없다.
- 응답 DTO 검증과 필요한 관계 preload를 commit 전에 완료해 commit 뒤 lazy I/O를 유발하지
  않는다. commit 실패와 cancellation에서는 rollback을 시도하고 세션을 재사용하지 않는다.
- rollback 자체 실패도 원래 예외를 가리지 않으며 사용자에게는 sanitized `DatabaseException`을
  반환한다.

### TX-005 DB session 명명 계약 [P0]

SQLAlchemy `AsyncSession`을 제공하거나 저장하는 애플리케이션 코드는 이름으로 DB 자원임을
명확히 표현해야 한다.

수용 기준:

- 정식 Dependency 이름은 `get_read_only_db_session`, `get_writer_db_session`,
  `get_routed_db_session`, `get_background_db_session`이다.
- 요청 밖 context manager는 `background_db_session`으로 명명한다.
- Dependency 인자와 Service/Repository 생성자 및 속성은 `db_session`을 사용한다.
- `session` 단독 이름은 SQLAlchemy 문맥이 명확한 제한된 내부 지역 변수에서만 허용한다.
- 기존 `get_read_session`, `get_write_session`, `get_session`, `get_background_session`은
  호출부 전환 기간에 deprecated alias로만 유지한다.
- 기존 이름 제거 전 전체 호출부와 Dependency override 테스트가 새 이름으로 전환된다.

## 11. Service 및 View 요구사항

### SVC-001 비즈니스 규칙 위치 [P0]

검증된 요청을 이용한 도메인 상태 전환, 기간 규칙, 중복 정책과 유스케이스 순서는
Service에 위치해야 한다.

수용 기준:

- 동일 유스케이스를 HTTP 외 경로에서 재사용할 수 있다.
- View에 데이터 접근 분기나 복잡한 도메인 조건이 없다.

### VIEW-001 버전별 파일 구성 [P1]

`v1` 이하에 업무 단위 View 파일을 여러 개 둘 수 있어야 한다.

수용 기준:

- 하나의 View 파일이 과도하게 커지면 resource 또는 use case 단위로 분리한다.
- 각 View 파일은 자체 `APIRouter`를 제공한다.
- 같은 버전의 그룹 `router.py`가 일관된 prefix와 tag로 취합한다.

### VIEW-002 ORM/Raw 응답 동등성 [P1]

ORM과 Raw View는 데이터 소스가 달라도 동일한 HTTP 품질 기준을 제공해야 한다.

수용 기준:

- 명시적 `response_model`을 사용한다.
- validation, 오류 상태와 pagination 형식이 프로젝트 기준과 일치한다.
- 내부 ORM 클래스 또는 Raw row가 응답 계약에 노출되지 않는다.

## 12. Scalar/OpenAPI 요구사항

### DOC-001 View 메타데이터 [P0]

모든 공개 path operation은 다음 정보를 제공해야 한다.

- `summary`
- 충분한 `description`
- 프로젝트 전체에서 고유한 `operation_id`
- 성공 `response_model`
- 성공 상태 코드
- 알려진 오류 `responses`
- 적절한 tag

204 응답은 body와 response model을 갖지 않는다.

### DOC-002 파라미터 문서 [P1]

Path, Query, Header와 요청 body는 설명, 실제 validation 제약과 대표 예시를 제공해야 한다.

수용 기준:

- 문서 제약과 런타임 Pydantic/FastAPI 검증이 일치한다.
- UUID, 날짜, pagination과 enum에 대표 예시가 있다.

### DOC-003 Pydantic schema [P0]

모든 외부 요청과 응답은 Pydantic 모델로 정의해야 한다.

수용 기준:

- 입력/출력 모델이 분리된다.
- 외부 노출 필드에 `description`이 있다.
- 주요 DTO에 `json_schema_extra.examples`가 있다.
- 민감 필드가 응답 schema에 포함되지 않는다.
- 공개 schema class 이름은 전역에서 충돌하지 않아야 한다. OpenAPI component key에 모듈 경로가
  합성된 `__` 이름이 나타나면 실패시키고, 충돌하는 DTO는 `AuthUserResponse`처럼 도메인 의미가
  드러나는 고유 이름으로 변경한다.

### DOC-004 태그 메타데이터 정합성 [P0]

`app/core/tags_metadata.py`와 실제 Router tag를 동기화해야 한다.

수용 기준:

- 실제 사용되는 모든 tag가 metadata에 존재한다.
- 사용하지 않는 오래된 tag는 제거하거나 사유가 명시된다.
- `Auth`와 신규 예제 기능 tag가 포함된다.
- 구현 완료 기능에 “미구현/예정” 설명이 남아 있지 않는다.
- 정확한 tag delta는 `Health` 유지, `Auth`/`Catalog`/`Reports` 추가, 미사용 `Analytics` 제거다.
  기존 User/Blog/Reply/SNS 설명도 현재 구현 상태에 맞게 고친다.

### DOC-005 OpenAPI 자동 검증 [P1]

OpenAPI schema에 대한 자동 정합성 테스트를 제공해야 한다.

수용 기준:

- operation ID 중복을 탐지한다.
- tag metadata 누락과 미사용을 탐지한다.
- 204를 제외한 성공 응답의 response schema 누락을 탐지한다.
- ORM 및 Raw 예제 DTO schema가 OpenAPI에 생성된다.

## 13. 시나리오 요구사항

### SCN-ORM-001 상품 CRUD 예제 [P1]

ORM workflow를 설명하는 완결된 상품 CRUD 예제를 제공해야 한다.

포함 범위:

- Product ORM 모델과 migration
- `catalog/admin.py`의 Product `ModelView`와 `admin_views`
- create/list/get/update/delete
- ORM Repository, Service, read-only/writer DB session Dependency
- `v1/products.py`와 그룹 Router
- Pydantic 요청/응답 및 Scalar 문서
- Repository, Service, API, transaction 테스트
- `catalog_products` 실제 Alembic migration과 upgrade/downgrade 검증
- 공개 계약은 `GET/POST /api/v1/catalog/products`와
  `GET/PATCH/DELETE /api/v1/catalog/products/{product_id}`다. operation ID는 각각
  `listCatalogProducts`, `createCatalogProduct`, `getCatalogProduct`,
  `updateCatalogProduct`, `deleteCatalogProduct`로 고정한다. create는 201, delete는 body 없는
  204, get/update의 미존재는 404, 충돌은 409다.
- `ProductAdmin`은 create/edit/delete/details/export를 허용한다. 현재 비밀 필드는 없으며
  향후 추가되는 secret은 list/detail/form/export에서 모두 제외한다.

### SCN-RAW-001 일별 매출 리포트 예제 [P1]

Raw workflow를 설명하는 일별 매출 집계 예제를 제공해야 한다.

포함 범위:

- 집계 결과 전용 ORM 모델 없이 Raw 집계 SQL 사용
- migration/metadata/Admin 스키마 소유권을 위한 `SalesOrder` 원본 모델과
  `reports/admin.py`의 `ModelView`/`admin_views`
- named date parameters
- `SalesReportRawRepository`, Report Service, read-only Dependency
- Pydantic Raw 결과 DTO
- `v1/sales_reports.py`와 그룹 Router
- SQL 결과 mapping, reader routing, API, OpenAPI 테스트
- Raw 원본 `sales_orders` 실제 Alembic migration
- `compose.test.yaml`을 재사용하는 로컬 및 CI MySQL 통합 테스트
- 공개 계약은 `GET /api/v1/reports/sales/daily`, operation ID
  `getDailySalesReport`다. `SalesOrderAdmin`은 create/edit/delete를 금지하고 details/export만
  허용한다. 향후 payment/customer 식별자는 list/export에서 제외한다.

### SCN-RAW-002 Raw 쓰기 검증 예제 [P1]

운영 공개 API가 아니어도 테스트 fixture에서 Raw DML workflow를 검증해야 한다.

수용 기준:

- execute 결과 row count를 검증한다.
- 테스트 UoW의 성공 commit 1회와 실패 예외 전파/rollback을 검증한다.
- read-only DML 차단을 검증한다.
- 운영 HTTP endpoint는 만들지 않는다. 테스트 전용 Service/UoW가 writer session의
  commit/rollback을 소유하며 실패 시 예외 전파와 DB 상태 불변을 검증한다. 따라서 이
  시나리오에는 HTTP “실패 응답” 요구가 없다.

## 14. 비기능 요구사항

### NFR-001 보안 [P0]

- SQL injection 방지 규칙을 위반하는 Raw SQL이 없어야 한다.
- 로그와 사용자 오류 응답에 비밀번호, 토큰, 전체 SQL 파라미터를 기록하지 않는다.
- Pydantic 응답에 비공개 ORM 필드가 포함되지 않는다.
- `engine.echo=False`만으로 로그 안전을 충족했다고 보지 않는다. DEBUG 레벨에서
  `sqlalchemy.engine`, `sqlalchemy.pool`, `aiomysql`, `pymysql`, `aiosqlite` 등 SQL/driver
  logger가 SQL과 bind 값을 내보내는지 end-to-end secret probe로 검증한다.
- SQL echo는 기본 `False`이고 명시적 로컬 진단 opt-in에서만 허용한다. queue 출력 경로에
  SQL noise filter를 적용하되 WARNING 이상 연결 장애 신호는 보존한다.
- ORM/Raw/commit 예외를 기록할 때 exception 객체를 `%s`, f-string 또는 `exc_info=True`로
  그대로 남기지 않는다. normal log에는 안정적인 code/model/query/operation과 sanitized
  constraint 분류만 기록하고 SQL, driver message, params, DSN은 금지한다.
- Alembic `fileConfig()`는 `disable_existing_loggers=False`를 사용해 같은 프로세스의 앱 logger를
  비활성화하지 않는다.
- 글로벌 `HTTPException`, `AppException`, validation 및 catch-all handler는 안정적인 error code,
  예외 타입, path template만 기록한다. `exc.detail`, raw validation input, 요청 body/header,
  `str(exc)`와 traceback은 allowlist 기반 redaction 없이 응답·일반 로그에 기록하지 않는다.
- staging/production DB 연결은 서버 인증서를 검증하는 TLS를 사용한다. plaintext 또는 인증서
  검증 비활성화는 local/test에서만 명시적으로 허용한다.
- migration 계정, writer 계정과 reader 계정을 분리한다. runtime writer는 필요한 DML만,
  reader는 SELECT만 허용하고 DDL·GRANT 권한은 migration 계정에만 둔다.
- Celery task/result serializer와 `accept_content`는 JSON으로 제한하고 pickle/yaml을 허용하지 않는다.

### NFR-002 성능 [P1]

- 목록 API는 무제한 조회를 허용하지 않는다.
- pagination limit 상한을 둔다.
- ORM 관계 조회는 N+1 방지 전략을 기능 Repository에 명시한다.
- Raw 집계 쿼리는 실제 DB 실행 계획을 검토한다.
- 존재 확인은 SQL `EXISTS`를 사용한다.
- 공개 Raw 집계와 목록 조회에는 취소 가능한 query/service timeout을 적용한다. timeout은 안전한
  503/504 계열 오류로 변환하고 session rollback/close가 완료된 뒤 pool로 반환되는지 검증한다.

### NFR-003 타입 안전성 [P1]

- ORM 모델, PK, Repository 반환 타입을 제네릭으로 검사한다.
- Raw 결과가 외부로 나가기 전에 Pydantic validation을 거친다.
- `Any`와 무검증 `dict` 반환을 Base의 공개 계약에서 최소화한다.

### NFR-004 관측성 [P1]

- Repository 오류 로그에 기능, 모델 또는 쿼리 이름을 포함한다.
- Raw SQL 전체 값과 민감 파라미터는 기록하지 않는다.
- 필요 시 느린 쿼리 관측을 위한 실행 시간을 구조화 필드로 남긴다.

### NFR-005 호환성 [P0]

- 기존 공개 API 경로, 응답 schema와 상태 코드를 의도 없이 변경하지 않는다.
- 기존 DB schema는 명시적 migration 없이 바뀌지 않는다.
- 기존 Base Repository 호출부를 점진적으로 전환한다.

### NFR-006 가용성 및 readiness [P1]

- liveness와 readiness의 역할을 분리한다.
- `/health`는 프로세스 생존 여부를 반환한다.
- `/ready`는 writer DB에서 `SELECT 1`을 실행하며 timeout은 2초다.
- 준비 완료는 200, DB 오류 또는 timeout은 503을 반환한다.
- 503 응답에 DSN과 내부 DB 오류 내용을 노출하지 않는다.
- 선택 자원의 미사용 상태를 장애로 판정하지 않는다.
- 필수 자원 startup 실패는 fail-fast한다.
- `/ready`의 writer DB 검사는 이번 범위이며 Redis readiness만 제외한다. shutdown admission을
  닫은 뒤에는 503을 반환하고 route inventory/OpenAPI/sanitization 테스트에 포함한다.
- 공개 계약은 `GET /ready`, tag `Health`, operation ID `getReadiness`다. 성공은 기존
  `HealthResponse`와 같은 `status`/`version` schema로 200을 반환하고 실패는 프로젝트 표준
  오류 schema로 503을 반환한다. Phase 1 완료 시 route inventory는 19 paths/31 operations,
  최종은 catalog collection/item과 reports를 더한 22 paths/37 operations다.

### NFR-007 자원 예산 [P1]

- worker 수와 writer/read/background pool 크기를 곱한 최대 연결 수를 산정한다.
- DB 서버 최대 연결 수를 넘는 설정을 배포 전에 검수한다.
- multi-worker 환경에서 resource manager가 worker별로 실행됨을 문서화한다.
- 검증식은 `api_workers × (writer_pool + Σreader_pools + background_pool) +
  celery_children × celery_pool + migration/admin_reserve <= DB connection budget`이다.
  현재 engine별 `pool_size=20`, `max_overflow=20`은 최대 40이므로 설정화하고 초과 구성을
  startup 또는 배포 검증에서 거부한다.

### NFR-008 lifecycle 관측성 [P1]

- startup/shutdown 단계와 소요 시간을 구조화 로그로 기록한다.
- 발견한 모델 모듈 수와 metadata table 수를 기록한다.
- 자원별 생성·close 성공과 실패를 기록한다.
- DSN password와 secret은 로그에 기록하지 않는다.

### NFR-009 Event loop 비차단 [P0]

비동기 선택지가 있는 I/O와 장시간 CPU 작업은 요청 event loop에서 직접 실행하지 않아야
한다.

수용 기준:

- 모든 공개 FastAPI path operation이 `async def`다.
- DB I/O는 `AsyncEngine`/`AsyncSession`과 async driver를 사용한다.
- bcrypt 같은 고비용 동기 CPU 작업은 `asyncio.to_thread()` 또는 worker로 격리한다.
- worker별 최대 10,000건의 bounded `QueueHandler`/`QueueListener`를 사용한다.
- production/staging 애플리케이션 파일 handler를 제거하고 stdout/stderr로 출력한다.
- Docker, Kubernetes 또는 운영 agent가 저장과 rotation을 담당한다.
- DEBUG/INFO/WARNING은 queue 포화 시 drop하고 counter를 증가시킨다.
- ERROR/CRITICAL은 queue 포화 시 최소 stderr fallback을 사용한다.
- console 및 uvicorn logging도 같은 queue 출력 경로로 통합한다.
- 동기 HTTP client, `time.sleep`, 동기 subprocess, 직접 파일 I/O를 async 함수에서 사용하지
  않는다.
- 짧은 User-Agent/JWT/Pydantic 연산은 측정 근거가 있는 한 동기 실행을 허용한다.
- SQLAlchemy `AsyncConnection.run_sync()`는 동기 DB driver 사용으로 판정하지 않는다.

### NFR-010 운영 안전 기본값 [P0]

개발 편의 기본값이 staging/production에 그대로 승격되지 않도록 startup에서 fail-fast해야 한다.

수용 기준:

- staging/production은 `DEBUG=false`를 강제하고 `/docs`와 `/openapi.json`을 공개하지 않는다.
- placeholder JWT access/refresh/session secret, 서로 같은 access/refresh key, 최소 길이·entropy
  정책 미달 secret을 거부한다. 실제 secret 값은 저장소·로그·오류·OpenAPI에 포함하지 않는다.
- 인증 backend가 없는 `/admin`은 staging/production에서 `ADMIN=false`가 기본이다. 활성화하려면
  SQLAdmin authentication backend 또는 신뢰 가능한 reverse-proxy 인증/네트워크 차단이
  구성되었음을 명시적으로 선언하고 startup 검증을 통과해야 한다. “권장” 경고만으로는 부족하다.
- `ADMIN=false`에서는 sqladmin과 기능별 `admin.py`를 import하지 않고 `/admin`이 404여야 한다.
- `CORS_ALLOW_ORIGINS=["*"]`와 credentials 허용 조합을 설정 검증에서 거부한다.
- DB URL은 문자열 보간 대신 SQLAlchemy `URL.create()` 등 escaping을 보장하는 생성기를 사용하고,
  진단 출력에는 masking된 DSN만 사용한다.
- `X-Forwarded-For`, `X-Real-IP`와 proxy scheme/host는 신뢰 proxy allowlist를 통과한 연결에서만
  사용한다. 직접 인터넷 요청이 해당 헤더로 접속 기록·보안 판단을 위조할 수 없어야 한다.
- `/ready`는 orchestrator/내부 load balancer용 경로이며 public ingress에서 차단하거나 별도
  network policy로 제한한다. 인증 없는 반복 호출이 DB connection probe 증폭기가 되지 않게 한다.
- catalog/reports 참조 API는 local/test 예제로 기본 제한한다. staging/production에서 활성화할
  경우 JWT 인증과 명시적 권한 정책 또는 동등한 network isolation 없이는 startup/deploy gate를
  통과하지 못한다.

### NFR-011 검증 증거와 잔여 위험 [P1]

확률적 코드 리뷰만으로 완료를 선언하지 않고 재현 가능한 증거와 검사하지 않은 범위를 남긴다.

수용 기준:

- checked-in review gate가 pytest, Ruff lint/format, cold-cache mypy, Bandit, Alembic single-head,
  계층 불변식과 기존 OpenAPI contract를 한 번에 실행한다.
- gate는 실패 경로에서도 UTF-8로 상세를 출력하고 비정상 종료 원인을 숨기지 않는다. Windows
  자식 프로세스는 `PYTHONIOENCODING=utf-8` 또는 동등한 명시 설정을 사용한다.
- 문자열 검색으로 Python 구조를 판정하지 않고 AST 또는 실행 기반 검사를 사용한다. 각 핵심
  규칙은 결함 상태를 주입했을 때 실패하는 fail-on-revert 테스트를 가진다.
- 테스트 전용 모델은 별도 `DeclarativeBase`를 사용해 운영 `Base.metadata`와 schema snapshot을
  오염시키지 않는다.
- 결함 ledger는 Open Fix 0을 phase 종료 조건으로 사용하고, residual-risk에는 CTE DML 판별,
  Admin/예제 인증, MySQL skip, 부하·실복제·Celery worker·Scalar UI 미검사 여부와 재평가 조건을
  기록한다. “검사하지 않음”을 “통과”로 표현하지 않는다.
- CI가 MySQL을 직접 기동하고 healthy 상태를 확인한 뒤 선택된 MySQL 테스트를 실제 실행한다.
  selector 실행에서 비-MySQL 테스트의 `deselected`는 정상으로 기록하되, 선택 대상의
  skip/xfail 0과 selected=executed를 별도로 검증한다.
- `uv.lock` 기반 dependency vulnerability scan과 문서·소스·CI artifact secret scan을 실행한다.
  GitHub Actions는 tag가 아니라 검토한 commit SHA로, MySQL test image는 승인된 digest로 고정한다.
- Gate A는 현재 active-style 기준선의 mypy 실패도 숨기지 않는다. 2026-08-18 재실행에서
  219개 파일 중 8개 파일/29건 오류가 확인됐으므로, 기준선 결함으로 ledger에 기록하고 Phase 1
  진입 전에 0건으로 닫는다.

## 15. 테스트 및 품질 게이트

### TEST-001 Base 단위 테스트 [P0]

ORM Base:

- CRUD primitive
- 입력 불변성
- PK 타입 및 not-found
- 예외 변환

Raw Base:

- one/all/scalar/execute 반환
- 빈 결과
- named parameter
- 예외 변환
- commit 미수행

### TEST-002 계층 및 트랜잭션 테스트 [P0]

- View가 올바른 Dependency를 사용한다.
- 조회는 writer session과 commit을 사용하지 않는다.
- 쓰기는 writer session과 응답 전 commit을 사용한다.
- Repository 및 Dependency commit을 탐지한다.
- `DB_ROUTER_ENABLED=false`와 `true` 각각에서 read-only ORM flush와 Raw DML 차단을 검증한다.

### TEST-003 API 통합 테스트 [P0]

- ORM/Raw 성공 응답
- 입력 validation 422
- not-found/conflict/DB 오류
- commit 실패가 2xx가 아님
- Pydantic 응답 계약

### TEST-004 전체 품질 게이트 [P0]

변경 전 수집 기준선은 271 tests다. 테스트 삭제나 수집 누락으로 이 수보다 감소하면 원인을
명시적으로 승인받아야 하며, 다음 명령이 모두 성공해야 한다.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
.\.venv\Scripts\python.exe -m bandit -ll -q -r app main.py config.py
.\.venv\Scripts\python.exe -m pytest --collect-only -q
alembic heads
```

전체 suite는 skip/xfail/deselected 없이 통과해야 한다. marker 전용 MySQL 실행의 deselection은
허용하되 전체 suite 결과와 분리한다. 위 명령과 MySQL 절차는 로컬/CI가 공유하는 checked-in
검증 스크립트 하나로 실행한다.

### TEST-005 Lifespan 자원 관리 [P0]

- 모델 0개이면 table create와 DB 연결 시도가 0회인지 검증한다.
- 모델이 있고 개발 자동 생성 정책이 켜져 있을 때 create가 1회인지 검증한다.
- 운영 정책에서는 모델이 있어도 create가 0회인지 검증한다.
- startup 중 logging listener 등 후속 자원 초기화 실패 시 앞서 준비된 자원이 해제되는지 검증한다.
- 정상 shutdown의 drain/close/dispose 순서를 검증한다.
- cleanup 하나가 실패해도 나머지 cleanup이 실행되는지 검증한다.
- lifespan 재진입 후 task/listener/engine reference 누수가 없는지 검증한다.
- shutdown 후 `app.state.resources`에 닫힌 자원 reference가 남지 않는지 검증한다.
- 단일 monotonic 20초 deadline에서 task 최대 5초, DB dispose 최대 10초, logging 최대 5초와
  cleanup reserve를 배분하는지 검증한다. 단계 timeout의 합만으로 전체 예산을 소진하지 않는다.
- Celery worker cleanup의 별도 10초 제한을 검증한다.
- Resource Manager가 `main.py`에서 발견·모델 import를 마친 기존 `registry` 객체를 그대로
  사용하고, startup에서 추가 `AppRegistry()` 생성이나 재탐색을 하지 않는지 검증한다.

### TEST-006 비동기 runtime 회귀 [P0]

- 모든 공개 path operation이 async 함수인지 검사한다.
- async 함수에서 금지된 동기 I/O 호출을 정적 검사한다.
- production/staging에 애플리케이션 file handler가 존재하지 않는지 검사한다.
- worker별 queue 크기 10,000과 non-blocking `put_nowait()`를 검증한다.
- 저레벨 drop counter, rate limit 및 ERROR/CRITICAL stderr fallback을 검증한다.
- listener startup, 정상 flush/stop, startup 실패 cleanup을 검증한다.
- drain 시작 전에 신규 task admission을 닫고 late spawn을 거부한다. done callback은 task
  예외를 소비하며 drain은 done/pending 모두 gather한 뒤 pending을 취소·await해 최종 집합
  0개를 검증한다.
- Celery 연속 task가 동일한 살아 있는 loop를 재사용하는 기존 테스트를 유지한다.
- Celery worker shutdown 후 engine dispose, async generator shutdown, loop close를 검증한다.

### TEST-007 AppRegistry·모델·Admin 회귀 [P0]

- 기존 `tests/core/test_registry_*.py`, `tests/test_app_autowiring.py`,
  `tests/test_router_registration.py`, `tests/test_admin_wiring.py` 계약을 유지한다.
- 신규 앱 추가만으로 라우터, 모델 metadata와 Admin이 연결되고 중앙 목록 수정이 필요 없음을
  검증한다.
- 모델이 있는 모든 기능에 `admin.py`와 비어 있지 않은 `admin_views`가 있고, 각 모델이 정확히
  하나의 `ModelView`로 관리되는지 검증한다.
- Runtime과 Alembic이 동일한 AppRegistry 발견 규칙을 사용하며 선택 모듈 내부 import 오류를
  숨기지 않는지 검증한다.

### TEST-008 MySQL 통합 환경 [P0]

현재 저장소에는 `compose.test.yaml`이 없다. Raw SQL 방언과 read-only DML을 실제 MySQL에서
승인하기 전에 해당 파일을 신규 제공해야 한다.

수용 기준:

- `compose.test.yaml`에 격리된 MySQL test service, healthcheck, test 전용 database와
  자격증명 주입 방법을 정의한다.
- 로컬과 CI가 같은 compose service 및 같은 Alembic upgrade 절차를 사용한다.
- 통합 테스트는 Raw named binding, 결과 mapping, MySQL 전용 집계 SQL, Raw DML row count,
  rollback/commit 및 read-only 차단을 검증한다.
- SQLite나 mock session 테스트만으로 `RAW-REP-006`과 `RAW-REP-007`을 완료 처리하지 않는다.
- MySQL 전용 테스트는 strict marker `mysql`로 구분하고 CI selector를 `-m mysql`로 고정한다.
  일반 `integration` marker와 섞어 MySQL 미실행을 숨기지 않는다.
- CI run마다 고유 database/schema를 만들고 Alembic target을 명시한다. 성공/실패 모두 compose
  logs를 수집한 뒤 `docker compose down -v`로 제거한다.
- 같은 database의 병렬 실행은 금지한다. xdist 사용 시 worker별 database와 독립
  migration/cleanup을 제공한다.
- strict marker 정책을 유지하고 `mysql` 등록과 CI 선택식의 일치를 검증한다.
- CI는 full pytest 전에 compose MySQL을 healthy까지 기동한다. `-m mysql`에서 selected와
  executed가 각각 1 이상이고 선택 대상의 skip/xfail이 0이 아니면 실패한다. selector가 제외한
  비-MySQL 테스트의 `deselected`는 예상값으로 기록한다. 종료 시 성공/실패와 관계없이 logs를
  수집하고 `down -v`한다.
- MySQL 8.4 `caching_sha2_password` 연결을 위해 사용하는 driver 조합이 요구하면
  `cryptography`를 lockfile에 직접 고정하고 실제 handshake로 검증한다.
- metadata 기반 drop만 사용해 `alembic_version`을 남기지 않는다. migration 왕복 fixture는
  실제 schema의 모든 table/view를 제거한 빈 database에서 시작한다.

### TEST-009 보안 및 검수장치 회귀 [P0]

- 실제 secret sentinel을 DB bind 값으로 실행해 모든 최종 handler/captured log에 나타나지 않음을
  검증한다. ORM/Raw failure log와 exception response도 같은 sentinel로 검사한다.
- `fileConfig()` 실행 전후에 앱 logger가 활성 상태인지 검증한다.
- staging/production placeholder secret, DEBUG, 무인증 ADMIN, wildcard credentialed CORS의
  startup 거부와 `ADMIN=false` lazy import를 검증한다.
- OpenAPI 9개 이상 규칙(operation ID, tag, success/error schema, 204 body, schema name 등)은
  각각 독립적인 fail-on-revert fixture를 가진다.
- review gate 자체의 실패 출력, UTF-8, non-zero exit code와 오류 요약을 테스트한다.
- HTTP/App/validation/catch-all 예외에 secret sentinel을 넣어 응답, queue log, stderr fallback과
  captured traceback 어디에도 원문이 남지 않는지 검증한다.
- 신뢰하지 않은 연결의 `X-Forwarded-For`/`X-Real-IP`가 접속 IP를 바꾸지 못하고, 신뢰 proxy
  allowlist를 통과한 경우에만 전달 헤더가 반영되는지 검증한다.
- Celery가 JSON 외 serializer/content type을 거부하고 production DB TLS·최소권한 설정이 누락되면
  startup/deploy validation이 실패하는지 검증한다.
- dependency audit, secret scan, GitHub Action SHA와 container digest 검사 규칙은 의도적으로
  취약한 fixture에서 실패해야 한다.

## 16. 마이그레이션 요구사항

### MIG-001 기준선 확보 [P0]

변경 전에 다음 기준선을 확보해야 한다.

- `pytest --collect-only` 기준 271 tests와 전체 테스트 결과
- `AppRegistry`의 `discover() → import_models() → install_routers() → install_admin()` 계약 및
  `main.py`의 단일 registry 인스턴스 재사용
- `Base`, `TimestampMixin`, `UUIDMixin`과 Registry 기반 모델 metadata import 계약
- 모델별 `admin.py`/`admin_views` 및 모델당 정확히 하나의 `ModelView` 계약
- `DB_ROUTER_ENABLED=false`에서는 현재 read-only session의 DML 실효 차단이 동작하지 않는
  알려진 갭
- `compose.test.yaml` 및 MySQL 통합 테스트 환경이 현재 없다는 인프라 갭
- cold-cache mypy 기준 219개 파일 중 8개 파일/29건 오류가 있는 정적 타입 기준선 갭
- ORM Base 공개 메서드와 사용처
- 현재 OpenAPI schema
- 현재 Alembic head 및 metadata/schema 비교
- 기준선 commit `76aed3c1aea2d3f1754f650ba631c8d853562cec`, Python `3.14`, `uv.lock`
  SHA-256 `D1BC64A8FC30F2A9C8662FFD038ECEC2E7A548F5934C07D095A39635F0C9D7B8`과
  실행 일시/CI artifact를 기록한다. 271은 감소 감시선이지 유일한 성공 조건이 아니다.

### MIG-002 단계적 적용 [P0]

runtime/lifecycle 변경과 ORM/Raw delivery를 하나의 대형 변경으로 결합하지 않고 개발 계획의
Phase와 다음 Gate를 1:1로 적용한다.

1. **Gate A / Phase 0 — 기준선:** commit/toolchain, 271 tests artifact,
   Registry/Admin/API/OpenAPI, Alembic single head, SQL log sentinel과 운영 설정 실패 기준선을
   고정하고 결함 ledger/residual-risk를 시작한다.
2. **Gate B / Phase 1 — Runtime/Lifecycle:** 경량 feature init, Resource Manager, `/ready`,
   background/logging/Celery 종료, SQL noise filter, Alembic logger 보존과 운영 fail-fast 설정을
   구현하고 runtime/security 품질 gate를 독립 승인한다.
3. **Gate C / Phase 2 — read-only:** 정식 Dependency 이름과 router 설정 독립 DML 차단을 승인한다.
4. **Gate D / Phase 3 — ORM Model/Base:** 기존 모델 mixin schema diff 0과 typed PK를 승인한다.
5. **Gate E / Phase 4 — ORM Repository:** 최소 CRUD/예외/호환 wrapper를 독립 승인한다.
6. **Gate F / Phase 5 — MySQL 기반:** compose/CI, `mysql` marker의 실제 실행, MySQL 8.4 인증
   dependency와 기존 Alembic chain smoke를 독립 승인한다.
7. **Gate G / Phase 6 — Raw Base:** MySQL에서 Raw primitive/result/read-only 계약을 승인한다.
8. **Gate H / Phase 7 — catalog:** Product migration의 MySQL 적용까지 포함한 CRUD/Admin/API를
   독립 승인한다.
9. **Gate I / Phase 8 — reports:** SalesOrder migration/Admin/Raw report와 테스트 UoW를 승인한다.
10. **Gate J / Phase 9 — 최종:** Scalar/OpenAPI/schema name/tag/호환 정리, 문서 경로·환경변수
    실재 검사, Open Fix 0과 명시적 residual-risk를 포함한 전체 품질 gate를 승인한다.

기존 이름과 wrapper의 호환 기간은 릴리스 횟수가 아니라 단계 완료 조건으로 관리한다. 새
API 추가, 전체 호출부 전환, 사용처 0건 확인, 전체 품질 게이트 통과를 각각 독립 커밋으로
완료한 뒤 마지막 독립 단계에서만 제거한다.

### MIG-003 롤백 가능성 [P1]

각 단계는 독립 커밋으로 구성하고 API·DB schema 변경 여부를 명시해야 한다.

수용 기준:

- Raw Base 추가가 기존 ORM 동작과 결합되지 않는다.
- Runtime/Lifecycle 커밋은 ORM/Raw 예제, migration 및 공개 endpoint 추가와 분리한다.
- 모델 mixin 전환은 schema diff가 없으면 코드 단위로 되돌릴 수 있다.
- 호환 메서드는 모든 호출부 전환 전에 제거하지 않는다.
- 각 단계는 prerequisite, API/schema delta, forward migration, immediate `down_revision` 대상,
  검증 명령과 rollback 명령을 가진 manifest를 남긴다.
- 기존 Alembic revision은 재작성하지 않는다. 각 신규 revision을 바로 이전 revision까지
  downgrade한 뒤 다시 head로 upgrade한다. 이는 ephemeral DB 검증이며 운영 장애는 데이터
  보존을 우선해 기본적으로 forward-fix한다.
- deprecated alias/wrapper 제거는 `rg` 사용처 0건과 전체 gate 통과 뒤에만 수행한다.

## 17. 제외 범위

다음은 본 작업의 요구사항이 아니다.

- View에서 직접 SQL 실행
- Service에서 SQL 문자열 생성
- Repository 내부 commit
- AppRegistry와 별개로 동작하는 두 번째 자동 스캔 또는 Repository 자동 discovery
- 기능별 라우터·모델·Admin 중앙 목록을 `main.py`, `migrations/env.py` 또는
  `app/features/admin.py`에 다시 도입하는 변경
- ORM과 Raw 계층을 하나의 만능 Base로 통합
- Raw 결과를 검증 없는 dict로 외부 반환
- 모든 도메인 쿼리를 `app/core`로 이동
- API Gateway 또는 캐시 계층 도입
- 요청하지 않은 공개 API 호환성 파괴
- shutdown 시 DB table 삭제
- API Redis client/cache 및 Redis 의존 readiness 구현(`/ready`의 writer DB 검사는 범위에 포함)
- Celery worker 자원을 FastAPI lifespan에서 제어
- 모든 짧은 CPU 연산을 무조건 thread pool로 넘기는 변경
- JWT access/refresh token 정책, rotation, revoke/logout 또는 권한 체계 구현
- 인증 endpoint rate limit/account lockout, bcrypt 72-byte 초과 입력 정책, JWT algorithm allowlist,
  `extra` claim의 `sub/type/iat/exp` 덮어쓰기 방지와 token replay 방지는 별도 Auth hardening 범위다.
  이번 작업에서는 미해결 residual-risk로 기록하고 악화시키지 않는다.

## 18. 요구사항 추적표

| 구현 단계 | 주요 요구사항 |
|---|---|
| Gate A 기준선 | MIG-001, NFR-005·011, TEST-007·009, 271 tests 실행 artifact |
| Gate B Runtime/Lifecycle | AR-004~010, NFR-001·006~010, TEST-005~007·009 |
| Gate C read-only | TX-001~005, RAW-REP-007, TEST-002 |
| Gate D ORM Model/Base | ORM-MDL-001~005, TEST-001, MIG-002 |
| Gate E ORM Repository | ORM-REP-001~007, SVC-001, TEST-001~002 |
| Gate F MySQL 기반 | TEST-008 인프라·실행 증거 및 기존 migration smoke |
| Gate G Raw Base | RAW-REP-001~007, TEST-001~002, MySQL primitive 통합 |
| Gate H catalog | SCN-ORM-001, Product migration/Admin/API, TEST-003 |
| Gate I reports | SCN-RAW-001~002, SalesOrder migration/Admin/Raw API, TEST-003 |
| Gate J 최종 | VIEW-001~002, DOC-001~005, NFR-011, TEST-004·009, MIG-003 |

## 19. 완료 정의

다음 조건을 모두 만족해야 작업 완료로 판정한다.

- [ ] ORM과 Raw가 동일한 계층 호출 흐름을 사용한다.
- [ ] 모든 ORM Repository가 ORM Base 계층을 사용한다.
- [ ] 모든 Raw Repository가 Raw Base 계층을 사용한다.
- [ ] 하나의 AppRegistry 발견 결과가 모델, 라우터, Admin, lifecycle 전체에서 재사용되고
      기능별 중앙 등록 목록이나 중복 스캔이 없다.
- [ ] 모델 공통 필드 정책이 mixin으로 적용되고 DB schema가 의도 없이 바뀌지 않는다.
- [ ] 신규 ORM 모델마다 기능 소유 `admin.py`와 유효한 `admin_views`가 있으며 각 모델이
      정확히 하나의 `ModelView`로 안전하게 관리된다.
- [ ] 모델이 없으면 startup이 DB table 생성을 위한 연결을 시도하지 않는다.
- [ ] resource manager가 startup 실패와 shutdown에서 모든 소유 자원을 해제한다.
- [ ] background task drain → DB engine dispose → logging listener flush/stop 순서가 보장된다.
- [ ] API logging이 event loop에서 직접 file write/rotation을 수행하지 않는다.
- [ ] SQL/driver/ORM 오류 로그와 오류 응답에 sentinel secret, SQL, bind params, DSN이 없고
      Alembic 실행 뒤에도 앱 logger가 살아 있다.
- [ ] drain timeout 후 pending task가 취소·await되어 추적 집합에 남지 않는다.
- [ ] Celery worker 종료 시 async DB pool과 event loop가 정상 해제된다.
- [ ] View, Dependency, Service, Repository의 책임 위반이 없다.
- [ ] read-only/writer DB session 및 commit 경계가 자동 테스트로 보호되고,
      `DB_ROUTER_ENABLED=false`에서도 ORM flush와 Raw DML이 실효 차단된다.
- [ ] Raw SQL이 named binding과 식별자 allowlist 규칙을 준수한다.
- [ ] ORM/Raw 외부 응답이 모두 Pydantic DTO로 검증된다.
- [ ] ORM 상품 CRUD와 Raw 매출 리포트 예제가 완결되어 있다.
- [ ] `compose.test.yaml` MySQL 환경을 로컬과 CI가 공유하며 Raw SQL·DML 통합 테스트가
      실제 MySQL에서 통과한다.
- [ ] Scalar에서 요청·응답·오류·파라미터·태그 문서가 정확하다.
- [ ] operation ID와 tag metadata 정합성 테스트가 통과한다.
- [ ] OpenAPI component 이름에 모듈 경로형 `__`가 없고 모든 공개 DTO 이름이 고유하다.
- [ ] staging/production의 DEBUG, placeholder secret, 무인증 ADMIN, CORS 보안 설정이 fail-fast한다.
- [ ] MySQL 전용 테스트가 CI에서 실제 실행되며 skip되지 않고 Open Fix가 0이고 미검사 영역이
      residual-risk에 기록된다.
- [ ] Runtime/Lifecycle gate가 ORM/Raw delivery 전에 독립 승인되고 두 범위가 분리된 커밋으로
      추적 가능하다.
- [ ] 테스트 수가 271 미만으로 감소하지 않고 전체 pytest, Ruff, format check, mypy가 통과한다.

## 20. 확정 정책

1. UUID, created, updated 책임은 작은 Mixin으로 분리한다.
2. ORM Repository는 `BaseRepository[ModelT, PrimaryKeyT]`를 정식 계약으로 사용한다.
3. Base에는 최소 CRUD만 두고 고급 쿼리는 기능 Repository로 이동한다.
4. OpenAPI는 규칙 기반 검증을 중심으로 하고 핵심 schema만 snapshot한다.
5. `/ready`는 writer DB `SELECT 1`, 2초 timeout, 성공 200, 실패 503을 사용한다.
6. FastAPI shutdown은 단일 monotonic 20초 deadline 안에서 task 최대 5초, DB 최대 10초,
   logging 최대 5초와 cleanup reserve를 사용한다.
7. Celery worker cleanup timeout은 별도 10초다.
8. logging은 worker별 10,000건 queue와 stdout/stderr 외부 collector 방식을 사용한다.
9. queue 포화 시 저레벨 로그는 drop하고 ERROR/CRITICAL은 제한된 stderr fallback을 사용한다.
10. AppRegistry는 앱 목록의 단일 출처이며 Runtime, Alembic, Admin과 Resource Manager가 같은
    발견 결과를 재사용한다.
11. 신규 ORM 모델은 기능별 `admin.py`와 `admin_views`를 필수로 제공한다.
12. read-only DML 차단은 `DB_ROUTER_ENABLED` 활성 여부와 독립적인 보안·정합 계약이다.
13. Gate A~J를 Phase 0~9와 1:1로 승인하며 MySQL 기반은 Raw Base보다 먼저, catalog와 reports는
    각각 독립 delivery gate로 진행한다.
14. SQL echo와 무인증 Admin은 개발 편의 기능이며 staging/production에서 opt-in이 아니라
    fail-closed 정책을 사용한다.
15. 검수 완료는 테스트 개수나 초록 요약만으로 선언하지 않고 MySQL 실제 실행, fail-on-revert,
    Open Fix 0과 residual-risk 기록으로 증명한다.
