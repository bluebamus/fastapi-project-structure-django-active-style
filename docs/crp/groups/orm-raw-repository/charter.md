# Charter — orm-raw-repository  (Charter v0.1 / 2026-08-18)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항·불가침 제약과 모순될 수 없다.

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 앱 레지스트리 | `app/core/registry.py` | 소스 | `enabled_apps` / `discover` / `install_routers` / `import_models` / `install_admin` |
| 진입점·수명주기 | `main.py` | 소스 | Phase 1 대상 (registry 재사용, `/ready`, drain) |
| DB 세션·엔진 | `app/core/db/session.py` | 소스 | `create_db_tables()` 재-discovery 제거 대상 |
| DB 라우터·read-only | `app/core/db/router.py` | 소스 | Phase 2 DML guard 대상 |
| 모델 레지스트리 | `app/core/db/models_registry.py` | 소스 | `import_all_models()` — Phase 1 에서 호출 제거 |
| ORM Base | `app/core/models/models_base.py` | 소스 | Phase 3 mixin·PK generic |
| ORM Repository | `app/core/repositories/crud_base.py`, `repository_base.py` | 소스 | Phase 3~4 |
| Raw Repository | `app/core/repositories/raw_crud_base.py`, `raw_repository_base.py` | 소스 | Phase 6 완료 — primitive 4개 + 관측 파사드 |
| 예제 기능(ORM) | `app/features/catalog/**` | 소스 | Phase 7 완료 — 상품 CRUD 5 operations |
| 예제 기능(Raw) | `app/features/reports/**` | 소스 | Phase 8 완료 — 일별 매출 리포트 1 operation |
| 기존 기능 | `app/features/{auth,blog,home,reply,sns,user}/**` | 소스 | 회귀 보존 대상 |
| Admin | `app/features/admin.py`, 기능별 `admin.py` | 소스 | 인증 백엔드 미주입(F-006) |
| 설정 | `config.py`, `.env.example` | 설정 | staging/production fail-fast |
| 마이그레이션 | `migrations/**`, `alembic.ini` | 설정 | single head 유지 |
| 문서 | `docs/orm-raw-repository/2026-08-13/**` | 문서 | 설계·계획 기준선 |
| CI·테스트 인프라 | `.github/workflows/ci.yml`, `compose.test.yaml` | 설정 | Phase 5 완료 — gate/mysql 2개 job |
| MySQL 통합 테스트 | `tests/integration/**` | 테스트 | 전용 컨테이너(3310) 하네스 |
| 검증 스크립트 | `scripts/review_gate.py`(신규) | 소스 | Phase 9 결정적 게이트 |
| 테스트 | `tests/**`, `app/features/*/tests/**` | 테스트 | 기준선 271 |

- 총 테스트 수(기준선): **271** (GATE 3 기대치, 신규분 누적)
- 라우트 인벤토리(기준선): **18 paths / 30 operations** → Phase 1 후 19/31 → 최종 22/37

## 2. 계약 (Contract)

### 2-1. 지원 구성
- Python 3.14.4 · `uv.lock` 고정 · SQLite(단위) + MySQL(통합, Phase 5 이후)
- `DB_ROUTER_ENABLED` = true / false **양쪽 모두** 지원하며 동작 계약이 동일해야 한다.
- 환경: development / staging / production / test

### 2-2. 위협 모델
- 방어한다: Raw SQL 인젝션(바인딩 강제), read-only 세션의 DML, 로그·오류의 secret/SQL/DSN 노출,
  staging/production 의 안전하지 않은 DEBUG·placeholder secret·무인증 Admin·와일드카드 CORS.
- 방어하지 않는다: 애플리케이션 레벨 권한 모델(RBAC), 네트워크 경계, DB 서버 자체 보안,
  parser 없이 판별 불가능한 CTE 내부 DML(→ residual-risk R-001).

### 2-3. 불변식 (Invariants)
- INV-1: `main.py` 에 기능별 `include_router()` 가 없다. 신규 기능은 자동 발견으로만 결선된다. (검사: AST 규칙 + 자동배선 테스트)
- INV-2: SQL 문자열/`text()` 는 Repository 계층 밖에 존재하지 않는다. (검사: AST 규칙)
- INV-3: Repository / Dependency 는 `commit()` 을 호출하지 않는다. (검사: AST 규칙 + 트랜잭션 경계 테스트)
- INV-4: read-only 로 표시된 세션은 `DB_ROUTER_ENABLED` 값과 무관하게 ORM/Core/Raw DML 을 거부한다. (검사: router on/off 매트릭스 테스트)
- INV-5: runtime 은 한 번 `discover()` 한 동일 `AppRegistry` 인스턴스를 모델·라우터·Admin·startup 에 재사용한다. (검사: discovery 호출 횟수 테스트)
- INV-6: ORM Base 와 Raw Base 는 상속 관계가 없다. (검사: `issubclass` 단정 테스트)
- INV-7: 사용자 입력이 SQL 문자열에 보간되지 않는다 — 바인딩 파라미터만. (검사: AST 규칙 + 인젝션 테스트)
- INV-8: OpenAPI component 스키마명에 모듈 경로형 `__` 가 없고 operationId 는 누락·중복이 없다. (검사: 스냅샷 검증)
- INV-9: 전체 suite 의 skip/xfail/deselected 가 0 이다. (검사: CI `ci.yml` 기존 게이트)
- INV-10: DB Session Dependency 의 정식 이름은 `*_db_session` 이며, 기존 이름은 **같은 객체**를 가리키는 alias 로만 존재한다. 저장소 안(`app/**`, `tests/**`)에서는 정식 이름만 쓴다. (검사: `tests/core/test_session_dependency_names.py` 의 동일성 단언 + AST 스캔)
- INV-19: Raw primitive 의 결과 의미는 고정이다 — `fetch_one`(0행 None/복수행 오류), `fetch_all`(0행 빈 sequence), `fetch_scalar`(0행·NULL 모두 None/복수행 오류), `execute`(commit 없음, rowcount `int | None`, `-1` 비공개). (검사: `tests/core/test_raw_crud_base.py` + `tests/integration/test_raw_primitives_mysql.py`)
- INV-20: Raw 계층은 `TextClause` 만 받고 multi-statement 를 거부하며, 식별자는 코드 소유 allowlist(`ensure_identifier`)를 통과한 값만 쓴다. (검사: 같은 파일)
- INV-21: Raw Repository 로그에는 `query_name`·소요 시간·성공/실패·예외 타입만 남긴다. SQL 본문과 파라미터 값은 남기지 않는다. (검사: `tests/core/test_raw_repository_base.py`)
- INV-18: MySQL 통합 테스트는 **실제로 실행**되어야 한다. MySQL 부재로 전부 skip 된 초록은 실패로 처리한다. gate job(`-m "not mysql"`)과 mysql job(`-m mysql` + 전체 suite)은 정확히 상보 관계여서 어느 쪽에서도 실행되지 않는 테스트가 없다. (검사: `ci.yml` 의 두 판정 단계)
- INV-15: `BaseRepository` 의 공개 표면은 8개(create/get_by_id/get_by_id_or_raise/get_all/count/exists/update/delete), `CRUDBase` 는 primitive 5개(+`_pk`)로 고정한다. 고급 조회는 기능 Repository 가 소유한다. (검사: `tests/core/test_repository_contract.py` 표면 단언)
- INV-16: Repository 는 호출자가 넘긴 mapping 을 변경하지 않으며 PK 를 임의로 주입하지 않는다. (검사: 같은 파일)
- INV-17: 예외 detail 과 로그에 드라이버 오류 원문을 담지 않는다. (검사: 같은 파일)
- INV-12: 공통 Base 는 단일 컬럼 PK 만 지원하며 기본 이름은 `id` 다. PK 는 Repository 계층을 지나며 **타입이 변환되지 않는다**. 다른 이름은 `pk_attr`, 복합 PK 는 기능 Repository 로 분리한다. (검사: `tests/core/test_pk_generic.py`)
- INV-13: 공통 컬럼(`id`/`created_at`/`updated_at`)은 mixin 에서 온다. 모델이 같은 컬럼을 복사 정의하지 않는다. (검사: `tests/core/test_models_base_mixins.py`)
- INV-14: 모델 리팩터링은 스키마를 바꾸지 않는다. (검사: `tests/core/test_schema_snapshot.py` 골든 대조 + 기존 `tests/core/test_migration_chain.py::test_migrated_schema_matches_models`)
- INV-11: read-only 세션에서 Raw SQL 은 default-deny 로 판별한다 — SELECT 로 시작하고 잠금을 잡지 않는 단일 문장만 허용한다. (검사: `tests/core/test_read_only_guard.py` 의 문장 매트릭스)

### 2-4. 비목표
- `main.py` 의 기능별 명시 `include_router()` / 중앙 router·Admin 목록
- 자동발견 제거 또는 수동 installed-app 목록
- ORM/Raw 만능 Base 통합, reports 를 ORM 조회로 전환
- shutdown 시 table drop, FastAPI 에서 Celery 소유 자원 종료
- API Redis cache / Redis readiness / JWT lifecycle 확장 (`/ready` 의 DB 검사는 범위 내)

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [ ] `pytest` 전량 실행·통과 (기준선 271 + 신규분), skip/xfail/deselected 0
- [ ] `ruff check .` · `ruff format --check .` · `mypy .` · `bandit -ll -q -r app main.py config.py` 클린
- [ ] `alembic heads` single head
- [ ] 라우트 인벤토리가 Phase 별 기대치와 정확히 일치 (18/30 → 19/31 → 22/37)
- [ ] 불변식 구조 증거: INV-1~INV-9 각각에 AST 규칙 또는 실행 테스트 1개 이상 연결
- [ ] MySQL marker 테스트가 **실제 실행**되고 수집 건수 ≥ 1, skip 0 (CI artifact 로 증명)
- [ ] 문서의 경로·심볼·환경변수가 코드에 실재하는지 기계 검사 통과
- [ ] ledger 의 Open Fix 0 · residual-risk 재평가 조건 기록 완료
- [ ] 질의 수준(design-baseline §0 = 보통)에 맞춘 P/D 질문 깊이 준수

## 4. 변경 이력
- v0.1 (2026-08-18): 최초 작성. Phase 0 기준선 측정값 반영.
