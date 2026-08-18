<!-- generated-by: gsd-doc-writer -->
# ORM/Raw Repository 고도화 개발 계획

## 1. 목적과 원칙

이 계획은 현재 코드의 Django 스타일 `AppRegistry` 자동 발견·결선을 유지하면서 ORM과 Raw
SQL Repository를 독립 계층으로 고도화한다. 호출 흐름은 View → Dependency → Service →
Repository → `AsyncSession`이며, SQL은 Repository만 소유하고 쓰기 View가 성공 응답 전에
정확히 한 번 commit한다.

핵심 불변식은 다음과 같다.

- 새 기능은 `app/features/*` 규약으로 발견한다. `main.py`에 기능별
  `app.include_router(...)`를 추가하지 않는다.
- runtime에서 한 번 발견한 동일한 `AppRegistry` 인스턴스를 모델, 라우터, Admin과 startup
  준비에 재사용한다.
- runtime/lifecycle hardening과 ORM/Raw Repository 변경은 독립 게이트와 독립 커밋으로
  진행한다.
- ORM Base와 Raw Base는 서로 상속하지 않고 세션·예외·로깅 정책만 공유한다.

## 2. 현재 현황과 교정 방향

| 항목 | 현재 코드 | 계획 |
|---|---|---|
| 앱 발견 | `main.py`가 registry를 만들고 한 번 `discover()` | 유지 |
| 발견 부작용 | 일부 기능 `__init__.py`가 모델·라우터와 sink/DB 모듈을 import | 패키지 init 경량화 후 단계별 import 경계 검증 |
| 모델/라우터/Admin | 같은 registry의 `import_models()`, `install_routers()`, `register_admin(..., registry)` | 유지 |
| 테이블 생성 | `create_db_tables()`가 `import_all_models()`로 다시 discovery | 제거. 준비된 metadata/동일 registry 결과 사용 |
| 라우터 | registry가 `/api`에 자동 마운트 | 수동 `include_router` 금지 |
| 앱 기준선 | auth/blog/home/reply/sns/user 6개 | catalog/reports 자동 추가 |
| 라우트 기준선 | `/health` 포함 18개 경로 골든 인벤토리 | 기존 경로 보존 후 신규 경로 추가 |
| Admin 기준선 | 모델 5개와 ModelView 5개 | 신규 모델별 `admin.py`와 `admin_views` 추가 |
| 테스트 기준선 | commit `76aed3c...`, Python 3.14, lock hash 고정 시 전체 271 tests | artifact와 함께 보존하고 신규 테스트 누적 |
| ORM PK | `CRUDBase._get()`이 `str(id)` 강제 변환 | PK generic 도입과 함께 제거 |
| read-only | router 활성 시 DML 차단, `DB_ROUTER_ENABLED=false`에서는 미보장 | 설정과 무관한 DML 차단 구현 |
| Raw 결과 | 공통 one/scalar/rowcount 계약 없음 | 결과 의미를 명시적으로 고정 |
| MySQL 인프라 | `compose.test.yaml`과 CI의 MySQL service/통합 단계 없음; 일반 품질 게이트 `.github/workflows/ci.yml`은 존재 | Compose를 추가하고 기존 CI workflow를 확장 |

기존 자동배선 테스트는 삭제하거나 느슨하게 만들지 않는다. 발견 순서, 언더스코어 제외,
init hook 멱등성, 중앙 파일 무변경, 라우터 마운트, metadata, Admin 순서·누락·중복,
`ADMIN=false` 지연 import, route inventory를 그대로 유지하고 catalog/reports 기대값만
확장한다.

### 2.1 `fastapi-default-project-structure` 실증 검수 반영

2026-08-18 기준 고도화 구현(commit `db49e9c8d7106b026e2797f7356a0e1d1189056f`)과
결함 원장·373개 테스트를 코드부터 다시 대조했다. 첫 환경에서는 367 passed/6 MySQL skipped였고,
MySQL 8.4가 실제 준비된 재검수 환경에서는 전체 373 passed 및 `pytest -m mysql` 6 passed를
재현했다. 그러므로 “373 collected”와 “MySQL까지 검증 완료”를 같은 의미로 사용하지 않고
환경·selected·executed·skipped를 함께 기록한다.

참조 저장소의 `.github/workflows/ci.yml`에는 MySQL service/Compose 기동이 없다. 깨끗한 runner에서는
통합 6건이 skip된 뒤 skip 0 검사에서 CI가 실패하므로, 결함 원장의 “CI는 항상 MySQL을 기동한다”는
서술은 현재 구현과 불일치한다. 또한 `pytest -m mysql`은 비-MySQL 367건을 정상적으로 deselect하므로
selector 실행의 deselected 수 자체를 0으로 강제하면 안 된다. 현재 lock 환경의
`ruff format --check`도 migration 3개를 재포맷 대상으로 판정했으므로 참조 저장소의 과거
“전 게이트 통과” 기록을 그대로 승계하지 않고 각 명령의 fresh artifact를 남긴다.

설계에 승격할 교훈:

- DEBUG 로그에서 SQLAlchemy/driver가 SQL과 bind secret을 출력할 수 있으므로
  `engine.echo=False` 외에 출력 handler의 SQL noise filter와 end-to-end sentinel 테스트가 필요하다.
- ORM 예외 logger가 exception 객체를 그대로 출력해도 SQL/params가 새므로 Raw뿐 아니라
  ORM/commit/Alembic까지 동일한 redaction 계약을 적용한다.
- Alembic `fileConfig()`는 `disable_existing_loggers=False`로 앱 logger를 보존한다.
- 선두 키워드 기반 TextClause 판별은 CTE DML을 놓친다. unknown은 writer/default-deny이고
  지원 문법을 넓힐 때 parser와 회귀 테스트를 함께 추가한다.
- 무인증 `/admin`, placeholder JWT/session secret, DEBUG와 wildcard credentialed CORS는
  staging/production startup에서 fail-fast한다.
- MySQL 전용 marker 실행 건수와 skip 0을 CI가 별도로 증명한다. MySQL 8.4 인증 dependency,
  `alembic_version`까지 지우는 빈 schema fixture를 포함한다.
- OpenAPI component 이름 충돌, 테스트 모델의 운영 metadata 오염, 검수 스크립트의 실패 출력과
  Windows 인코딩도 독립 회귀 대상으로 둔다.
- 전역 HTTP/App/validation/catch-all 예외 handler도 `exc.detail`, raw input, `str(exc)`와 traceback을
  응답이나 일반 로그에 그대로 남기지 않는 동일한 sentinel/redaction 계약을 적용한다.
- 운영 DB는 인증서 검증 TLS와 migration/writer/reader 최소권한 계정을 사용한다. 접속 기록은
  신뢰 proxy allowlist를 통과한 전달 헤더만 실제 IP로 인정한다.
- catalog/reports 예제는 실제 배포 시 인증/권한 또는 network isolation을 요구하고 `/ready`는
  public ingress에서 제외한다.
- Celery는 JSON serializer/accept-content만 유지하고, CI는 dependency audit·secret scan·Action SHA와
  test image digest 고정을 검증한다.

그대로 채택하지 않을 구현:

- 참조 구현의 `first()/scalar()`, 음수 rowcount 공개, Core UPDATE/DELETE rowcount 기반 단건
  존재 판정은 이 문서의 더 엄격한 cardinality/entity-load 계약보다 약하므로 가져오지 않는다.
- 참조 구현의 CTE DML 오판과 무인증 Admin은 수용된 residual risk였지만, 본 계획에서는 각각
  default-deny와 운영 fail-closed 요구로 강화한다.

## 3. AppRegistry와 startup

runtime 조립 순서는 다음으로 고정한다.

1. `main.py`에서 `registry = AppRegistry()`, `registry.discover()`
2. 같은 인스턴스로 `registry.import_models()`
3. 같은 인스턴스로 `registry.install_routers(app)`
4. `ADMIN=true`일 때 `register_admin(app, engine, registry)`
5. lifespan에서는 이미 채워진 `Base.metadata`와 같은 registry 결과로 테이블 생성 정책 평가

선행 조건으로 기능 `__init__.py`의 모델·라우터 재노출과 import-time sink 등록을 제거하거나
명시적 멱등 init hook으로 옮긴다. `discover()`만 호출했을 때 metadata, engine, sink와 task 수가
변하지 않아야 한다. Runtime worker 안에서는 같은 registry 인스턴스를 재사용하고, 별도
Alembic 프로세스는 같은 알고리즘/정렬 규칙으로 독립 인스턴스를 한 번 만든다는 의미다.

`create_db_tables()`는 `import_all_models()`나 새 `AppRegistry().discover()`를 호출하지
않고 준비된 metadata에 `create_all()`만 수행한다. metadata table 수가 0이면 DB 연결도
시도하지 않는다. Alembic은 별도 프로세스이므로 `migrations/env.py`가 독립 registry를 한 번
발견하는 것은 허용하되 발견→모델 import 순서는 runtime과 같아야 한다.

## 4. ORM 설계

공통 모델은 `Base`, `UUIDPrimaryKeyMixin`, `CreatedAtMixin`,
`UpdatedAtMixin`의 작은 조합으로 구성한다. 기존 모델 전환 후 Alembic schema diff는 없어야
한다.

`BaseRepository[ModelT, PrimaryKeyT]`와 typed `pk_attr`을 정식 계약으로 도입한다. 공통 Base는
단일 컬럼 PK만 지원하며 기본 이름은 `id`다. 다른 이름은 명시적 `pk_attr`을 사용하고 복합 PK는
기능 Repository로 분리한다. 특히
`CRUDBase._get()`은 현재의 `session.get(self.model, str(id))`를 제거하고
`PrimaryKeyT`를 그대로 전달한다. 문자열·UUID·정수·외부 PK가 변형되지 않는 테스트를
추가한다.

`CRUDBase`는 get/add/delete/flush/refresh primitive만 제공한다. `BaseRepository`의 최소
공개 API는 create, get/get-or-raise, list, count, exists, update, delete로 고정한다. 입력
mapping을 복사하여 호출자 dict를 변경하지 않고 Base가 임의로 id를 주입하지 않는다.
고급 eager loading/join/batch는 기능 Repository로 이동하며 기존 API는 사용처 조사 → 호환
wrapper → 호출부 전환 → 제거 순으로 정리한다.

update/delete는 bulk DML이 아니라 먼저 단일 엔티티를 조회한다. update는 unknown/PK 변경을
거부하고 제공된 필드만 적용하며 빈 PATCH는 존재 확인 후 no-op이다. 응답 DTO는 commit 전에
검증하고 필요한 관계를 preload해 commit 뒤 lazy I/O를 금지한다.

## 5. Raw SQL 설계

`RawCRUDBase`와 `RawRepositoryBase`를 ORM 계층과 독립적으로 추가한다. 입력은
`TextClause`와 named bind params를 기본으로 하고 SQL 식별자는 코드 allowlist로 제한한다.
Repository는 RowMapping/scalar/rowcount를 반환하고 Service가 Pydantic DTO로 검증한다.

결과 의미는 다음으로 확정한다.

| API | 의미 |
|---|---|
| `fetch_one` | `mappings().one_or_none()`: 0행 None, 1행 RowMapping, 복수 행 오류 |
| `fetch_all` | `mappings().all()`: 0행은 빈 sequence |
| `fetch_scalar` | `scalar_one_or_none()`: 0행 또는 SQL NULL은 None, 복수 행 오류. 둘을 구분하려면 `fetch_one` 사용 |
| `execute` | DML 전용, commit 없이 `rowcount: int | None` 반환. driver가 미지원하면 None이며 -1을 성공 건수로 공개하지 않음 |

`first()`로 복수 행을 묵인하거나 scalar 복수 행을 버리거나 rowcount를 bool로 축약하지 않는다.
`RawRepositoryBase`는 keyword-only `query_name`, 소요 시간, 성공/실패만 기록하고 SQL
본문과 params는 기록하지 않는다.

SQL은 Repository 소유 상수만 허용하고 외부 값은 named bind, `IN`은
`bindparam(expanding=True)`, 식별자는 immutable allowlist를 쓴다. multi-statement와 요청 기반
동적 SQL은 거부한다. async `execute()` 뒤 buffered result 소비는 동기 API이며 대용량 stream은
별도 API로 분리한다. 하나의 `AsyncSession`을 concurrent task가 공유하지 않는다.

## 6. read-only DML 계약

read-only 보장은 `DB_ROUTER_ENABLED`와 분리한다.

- router on/off 양쪽 세션 팩토리가 공통 guard-capable Session 계층을 사용한다.
- read-only Dependency는 모든 설정에서 session info에 표식을 남긴다.
- ORM flush와 Core Insert/Update/Delete는 `ReadOnlyRoutingError`로 차단한다.
- 모든 session 실행 경계에서 중앙 `is_read_only()`/`assert_writable()`를 적용한다. Raw
  `execute`만 막지 않고 fetch API의 TextClause DML, 직접 `session.execute()`, `FOR UPDATE`,
  저장 프로시저와 multi-statement 우회도 거부한다.
- router on/off × ORM/Core/Raw DML을 매개변수화해 차단하고 SELECT 허용을 검증한다. session
  표식은 애플리케이션 방어선이므로 배포 환경은 read-only credential/transaction도 사용한다.
- leading `WITH` 등 분류 불가능한 TextClause는 writer로 보내고 read-only에서는 차단한다.
  CTE DML/SELECT, leading comment, `FOR UPDATE`, `CALL`, DDL, multi-statement를 fixture로 고정한다.

따라서 기본값 `DB_ROUTER_ENABLED=false`에서도 read-only는 실제 쓰기 방지 계약이다.

## 7. catalog/reports 예제와 자동결선 영향

### catalog

ORM 상품 모델, migration, Repository, Service, Dependency, DTO, CRUD View, router와
`admin.py`/`admin_views`를 추가한다. GET은 read-only, 변경 API는 writer session과 응답
전 1회 commit을 사용한다.

라우트는 `GET/POST /api/v1/catalog/products`와
`GET/PATCH/DELETE /api/v1/catalog/products/{product_id}` 다섯 개다. Product Admin은
create/edit/delete/details/export 허용으로 고정한다.

### reports

매출 원본 모델/테이블, migration, `admin.py`/`admin_views`,
`SalesReportRawRepository`, Service, DTO, 집계 View와 router를 추가한다. 모델은
metadata/migration/Admin의 스키마 소유권용이며 집계 조회는 Raw SQL로 구현한다. Raw DML은
불필요한 운영 API 대신 테스트용 Service/UoW가 writer session의 commit/rollback을 소유하고
Repository는 rowcount와 예외만 반환하는 workflow로 rowcount, commit/rollback,
read-only 차단을 검증한다.

리포트 라우트는 `GET /api/v1/reports/sales/daily` 하나이며 SalesOrder Admin은
create/edit/delete 금지, details/export 허용의 read-only 운영 정책을 쓴다.

두 기능은 각각 `catalog_router`, `reports_router` 규약으로 자동 마운트한다.
`main.py`, 중앙 router 목록, 중앙 Admin 목록을 수정해 연결하지 않는다. 다음 테스트를 함께
갱신한다.

- 실제 registry 앱 집합과 신규 앱 자동발견
- route inventory의 기존 경로 보존 및 catalog/reports 경로 추가
- 두 모델의 metadata/Alembic 등록
- 각 기능 `admin.py` 존재, `admin_views` 계약, 등록 순서·누락·중복 없음
- 관리 모델 기대 집합, Admin CRUD/보안 정책
- 신규 앱을 만들어도 중앙 파일이 바뀌지 않는 기존 자동배선 테스트

## 8. Runtime/lifecycle 독립 작업

`app/core/resources.py`의 resource manager로 startup 실패와 정상 shutdown의 cleanup을
통합한다. fallible start 뒤 cleanup을 등록하지 않고 자원별 context manager 또는 start 전
등록한 멱등 cleanup을 사용한다. 현재 import-time engine은 1차 단계에서 manager가 생성하지
않고 종료만 소유한다. background task는 admission을 닫고 done 예외를 소비하며 timeout 후
cancel하고 done/pending 모두 await한 뒤 추적 집합을 비운다.
그 후 writer/reader/background engine을 dispose하고 마지막에 bounded logging queue를
flush/stop한다. 파일 logging I/O는 event loop 밖에서 실행한다. Celery worker의 event
loop/pool은 FastAPI lifespan이 아니라 worker shutdown signal이 정리한다.

queue logging은 `python main.py`뿐 아니라 `uvicorn main:app` import 경로에서도 bootstrap과
uvicorn logger handoff가 한 번만 일어나야 한다. Celery는 prefork만 지원 대상으로 선언하고
`worker_process_init`에서 child engine/loop를 만들며 `worker_process_shutdown`에서 멱등 정리한다.
개발 startup DDL은 단일 worker에서만 허용한다. Celery는 worker 전용 engine/sessionmaker
factory를 추가하고 `worker_process_init`에서 부모로부터 상속된 pool을 폐기한 뒤 child handle로
재바인딩하며 shutdown 소유권을 테스트한다. `/ready`는 `GET /ready`, `Health` tag,
`getReadiness`, writer `SELECT 1`, 2초 timeout, `HealthResponse` 200/표준 오류 503으로 Phase 1에
포함하고 Redis 연계만 제외한다.

queue handler에는 SQL noise filter를 붙여 SQL/driver DEBUG·INFO를 기본 차단하되 WARNING 이상은
유지한다. `LOG_SQL_ECHO_ENABLED` 같은 opt-in은 development/test에서만 허용한다. ORM/Raw/commit
오류 log는 exception 원문 대신 type/code와 안전한 context만 남긴다. Alembic은 기존 logger를
비활성화하지 않는다. staging/production startup은 DEBUG, placeholder/equal JWT key, 무인증
ADMIN과 wildcard credentialed CORS를 거부하고 `ADMIN=false`에서 admin 모듈 lazy import를 검증한다.
글로벌 예외 handler도 안정적인 error code와 path template만 기록하고 raw detail/input을 제거한다.
신뢰 proxy 설정 없이 전달 헤더를 접속 IP로 사용하지 않으며, Celery serializer는 JSON-only로
고정한다. `/ready`와 예제 API의 ingress/auth 정책도 배포 검증에 포함한다.

이 작업에는 동일 registry/metadata 재사용과 `create_db_tables()`의 중복 discovery 제거를
포함한다. ORM/Raw Base 및 예제 기능 변경과 섞지 않고 lifecycle/background/logging/Celery
테스트, 기존 271 tests, Ruff, format, mypy 통과 후 독립 커밋한다.

## 9. MySQL 테스트 인프라

현재 `compose.test.yaml`과 CI의 MySQL service/통합 단계가 없다. 기존
`.github/workflows/ci.yml`의 Ruff·format·mypy·bandit·pytest·Alembic head 게이트는 유지하면서
다음을 추가한다.

- healthcheck와 격리된 test DB/user를 가진 `compose.test.yaml` 생성. host publish는
  `127.0.0.1`로 제한하고 승인된 MySQL 8.4 image digest를 사용
- 로컬과 CI에서 동일 service/환경 변수 사용
- 기존 CI workflow 확장: 설치 → MySQL health → Alembic migration → MySQL integration →
  기존 전체 테스트/정적 검사
- migration upgrade/downgrade, MySQL 전용 집계 SQL, one/scalar/rowcount와 transaction 검증
- CI run별 고유 database/schema, 명시적 Alembic target, 성공/실패 로그 수집과 항상
  `docker compose down -v`; 동일 DB 병렬 실행 금지
- strict `mysql` marker와 CI selector `-m mysql` 사용. selected/executed 건수 1 이상 및 선택된
  테스트의 skip/xfail 0을 별도 판정한다. 비-MySQL 테스트의 selector `deselected`는 예상값으로
  기록하고 실패 조건으로 사용하지 않으며 full suite 전 MySQL을 healthy 상태로 기동
- MySQL 8.4 인증에 필요한 `cryptography` 등 driver dependency를 lockfile에 고정하고 실제
  handshake로 검증
- staging/production DB는 CA 검증 TLS를 사용하고 migration/writer/reader 계정을 분리한다.
  test compose의 고정 자격증명은 test 전용으로만 허용하며 artifact/로그에는 실제 secret을 넣지 않는다.
- migration fixture는 metadata table뿐 아니라 `alembic_version`과 실제 schema object 전체를
  제거한 빈 database를 사용
- 신규 revision별 immediate `down_revision` downgrade → head 재-upgrade. 기존 revision은
  재작성하지 않고 운영 장애는 기본 forward-fix

SQLite는 빠른 단위 테스트용으로 유지하지만 MySQL 방언과 rowcount 승인 근거로 사용하지 않는다.

## 10. 단계와 독립 게이트

### Phase 0. 기준선

commit/Python/lock hash, 271 tests 실행 artifact, registry 6개 앱, Admin 5개 모델, 기존 18개
route inventory, Alembic single head와 정규화한 OpenAPI hash를 기록한다.
SQL log sentinel, 운영 설정 거부, 현재 `/admin` 인증 상태, CI MySQL 실행 여부를 함께 기록하고
결함 ledger와 residual-risk를 시작한다.
현재 cold-cache mypy는 219개 파일 중 8개 파일/29건 오류이므로 Phase 0 결함으로 등록하고,
Phase 1 진입 전에 0건으로 닫는다. 테스트 271 passed만으로 기준선이 green이라고 표현하지 않는다.

### Phase 1. Runtime/lifecycle hardening

경량 feature init, resource manager, logging, drain, `/ready`, Celery 종료, registry 재사용과
table discovery 제거를 구현한다.
이 단계 route inventory는 `/ready`를 추가한 19 paths/31 operations다.
SQL log redaction/Alembic logger 보존과 staging/production fail-fast 보안 설정도 이 단계에서
독립 승인한다. 전역 예외 sanitization, trusted-proxy 처리, JSON-only Celery 직렬화와
`/ready` 내부 노출 정책도 같은 runtime/security gate에서 검증한다.
runtime 전용 게이트 통과 후 독립 커밋한다.

### Phase 2. read-only 안전성

router 설정 독립 DML guard와 정식 read-only/writer Dependency 이름을 도입한다. 기존 이름은
호환 alias로 유지한다. router on/off 테스트 통과 후 독립 커밋한다.

### Phase 3. ORM 모델/Base

mixin과 PK generic을 도입하고 `CRUDBase._get()`의 str 변환을 제거한다. schema diff 0,
PK 타입, 기존 API 테스트 통과 후 독립 커밋한다.

### Phase 4. ORM Repository

최소 CRUD, 입력 불변성, EXISTS, 예외 변환과 호환 wrapper를 구현한다. ORM 전체 회귀 후
독립 커밋한다.

### Phase 5. MySQL 통합 기반

`compose.test.yaml`과 기존 CI의 MySQL service/통합 단계를 먼저 추가한다. migration과 Raw
기능이 아직 없으므로 이 단계의 smoke는 service health와 **기존 Alembic chain의 head
upgrade/downgrade/re-upgrade**까지만 수행한다. Raw SQL gate는 Phase 6에서 시작한다.
`pytest -m mysql`의 수집/실행 건수 1 이상과 skip 0을 CI artifact로 남기며, MySQL이 없어서
모두 skip된 초록 결과는 실패로 처리한다. selector가 비-MySQL 테스트를 deselect한 수는 별도
정보로 기록하며 실패 판정에는 사용하지 않는다.

### Phase 6. Raw Base

one/all/scalar/rowcount, binding, query name, 예외와 read-only 계약을 구현한다. SQLite 단위
테스트와 실제 MySQL Raw primitive 통합 게이트를 모두 통과한 뒤 독립 커밋한다.

### Phase 7. catalog ORM 예제

catalog의 모델/migration/Admin/계층/라우터와 inventory 테스트를 추가한다. 자동배선, SQLite
migration chain, MySQL migration과 전체 회귀 통과 후 독립 커밋한다.

### Phase 8. reports Raw 예제

reports의 원본 모델/migration/Admin/Raw Repository/Service/DTO/라우터를 추가한다. MySQL 전용
집계 SQL, Raw DML, rowcount와 read-only 차단 통합 테스트 통과 후 독립 커밋한다.

### Phase 9. 문서/OpenAPI/최종 게이트

태그, operation ID, DTO 예시, 오류 응답과 schema snapshot을 갱신하고 다음을 실행한다.
`Health`는 유지하고 `Auth`/`Catalog`/`Reports`를 추가하며 미사용 `Analytics`를 제거한다.
User/Blog/Reply/SNS의 “미구현/예정” 설명도 현재화한다. 최종 inventory는
22 paths/37 operations다.
OpenAPI component key의 모듈 경로형 `__`를 금지하고 각 문서의 경로·심볼·환경변수가 실제
코드에 존재하는지 기계 검사한다. Open Fix 0과 residual-risk의 미검사 영역/재평가 조건을
확인한다. dependency vulnerability/secret scan, GitHub Action SHA, container digest와 예제 API의
인증·network isolation 결정을 확인한 뒤 완료한다.

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy .
.\.venv\Scripts\python.exe -m bandit -ll -q -r app main.py config.py
.\.venv\Scripts\python.exe -m pytest --collect-only -q
alembic heads
```

checked-in 검증 스크립트를 로컬과 CI가 공유한다. 전체 suite는 skip/xfail/deselected 0을
요구하고 MySQL marker 선택 실행의 deselection은 별도 결과로 기록한다.
검증 스크립트는 실패 출력과 non-zero exit 자체를 테스트하고 Windows/POSIX 모두 UTF-8로
동작해야 한다. 핵심 정적 규칙은 AST로 구현하며 fail-on-revert fixture로 유효성을 증명한다.

## 11. 테스트 매트릭스

| 영역 | 필수 검증 |
|---|---|
| 회귀 | 기존 271 tests와 API/OpenAPI 계약 |
| 자동배선 | 동일 registry, 중앙 파일 무변경, catalog/reports 모델·router·Admin |
| ORM | PK 타입 보존, CRUD, 입력 불변성, 예외, transaction |
| Raw | 0/1/복수 row, NULL scalar, rowcount, binding, DTO, injection |
| read-only | router on/off의 ORM/Core/Raw DML, CTE/unknown/default-deny와 SELECT 허용 |
| Admin | 신규 admin.py/admin_views, 순서·누락·중복·CRUD/보안 |
| route inventory | 기존 18개 보존과 신규 method/path 고정 |
| lifecycle | startup 실패 cleanup, cancel/await, dispose, logging 종료 |
| MySQL/CI | compose health, migration chain, MySQL SQL/rowcount |
| 로그 보안 | SQL/driver/ORM failure sentinel 비노출, Alembic 후 logger 생존 |
| 오류 경계 | HTTP/App/validation/catch-all raw detail/input/traceback 비노출 |
| 운영 설정 | DEBUG/placeholder secret/무인증 Admin/CORS fail-fast, ADMIN lazy import, DB TLS/최소권한 |
| 네트워크 | trusted proxy header, `/ready` 내부 노출, 예제 API auth/isolation |
| 공급망 | lockfile 취약점·secret scan, Action SHA, MySQL image digest |
| 검수장치 | AST 규칙, fail-on-revert, UTF-8 실패 출력, Open Fix 0/residual-risk |

## 12. 비목표

- `main.py`의 기능별 명시 `include_router()` 또는 중앙 router/Admin 목록
- 자동발견 제거 또는 수동 installed-app 목록
- View/Service의 SQL 실행, Repository/Dependency 내부 commit
- ORM/Raw 만능 Base 통합
- 사용자 입력을 Raw SQL 문자열에 보간
- reports를 ORM 조회로 바꾸는 것
- shutdown table drop, FastAPI에서 Celery 소유 자원 종료
- API Redis cache/Redis readiness 또는 JWT lifecycle 확장(`/ready`의 DB 검사는 범위에 포함)

## 13. 완료 기준

- 기존 271 tests와 모든 신규 테스트, Ruff, format, mypy, Bandit, Alembic single-head와 MySQL
  gate가 통과하고 full suite의 skip/xfail/deselected가 0이다.
- SQL/driver/ORM/commit/Alembic 로그와 오류 응답에 sentinel secret, SQL, params, DSN이 없다.
- staging/production에서 안전하지 않은 DEBUG, secret, Admin, CORS 설정이 startup을 통과하지 못한다.
- MySQL marker 테스트가 실제 실행되고 OpenAPI schema name, 문서 경로·심볼·환경변수 검사가
  통과하며 Open Fix 0과 residual-risk가 기록된다.
- exception sentinel, trusted proxy, DB TLS/최소권한, JSON-only Celery와 공급망 검사가 통과하고
  예제 API 및 `/ready`의 운영 노출 정책이 fail-closed다.
- catalog/reports가 `main.py` 수정 없이 자동 발견·라우팅·모델·Admin 결선된다.
- runtime의 동일 registry가 재사용되고 `create_db_tables()`는 discovery를 반복하지 않는다.
- 신규 모델별 `admin.py`/`admin_views`, route inventory, Admin 테스트가 확장된다.
- 기존 자동배선 테스트가 유지된다.
- PK generic 도입 후 `CRUDBase._get()`이 PK를 문자열로 바꾸지 않는다.
- Raw one/scalar/rowcount 의미가 SQLite와 MySQL 검증에서 문서와 일치한다.
- `DB_ROUTER_ENABLED=false`와 true 모두 read-only ORM/Core/Raw DML을 차단한다.
- 신규 `compose.test.yaml`과 CI가 MySQL migration/Raw 통합 테스트를 재현한다.
- runtime/lifecycle과 ORM/Raw 작업이 독립 게이트·커밋으로 추적된다.
