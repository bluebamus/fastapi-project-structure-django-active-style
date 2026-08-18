# Ledger — orm-raw-repository (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(→residual-risk) / **Wont-fix**(오탐).
> 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(코드 위치) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-5 (동일 registry 재사용) | Fix | **Fixed** | `app/core/db/session.py:227-230` 이 `import_all_models()` 로 모델을 재-discovery. `main.py:70` 의 `create_db_tables()` 호출 경로. | Phase 1 완료. `import_all_models()` 호출 제거 + 빈 metadata 거부 가드. 회귀: `tests/core/test_create_db_tables.py`(3) — 수정 전 RED 확인. |
| F-002 | MED | 2-1 지원 구성(PK 타입 보존) | Fix | Open | `app/core/repositories/crud_base.py:59` — `session.get(self.model, str(id))` 로 PK 를 문자열 강제 변환. | Phase 3. PK generic 도입과 함께 제거. int PK 조회가 드라이버/방언에 따라 깨질 수 있다. |
| F-003 | HIGH | INV-4 (설정 무관 read-only 보장) | Fix | Open | 가드가 `app/core/db/router.py:141-147` 의 `RoutingSession.get_bind()` 안에만 존재. `session.py:147`(라우터 on) 만 이 클래스를 쓰고 `:149`(라우터 off) 는 평범한 `async_sessionmaker` 를 쓴다. `:184` `BackgroundSessionLocal` 도 항상 비보호. | Phase 2. `DB_ROUTER_ENABLED=false` 와 백그라운드 세션에서 `mark_read_only()` 가 **무력**. |
| F-004 | MED | INV-8 (OpenAPI 스키마명) | Fix | Open | component schemas 31개 중 2개가 모듈 경로형: `app__features__auth__schemas__auth_schema__UserResponse`, `app__features__user__schemas__user_schema__UserResponse`. | Phase 9. auth/user 의 `UserResponse` 이름 충돌로 FastAPI 가 모듈 경로를 붙임. 명시적 스키마명 부여로 해소. |
| F-005 | LOW | INV-8 (tag 일관성) | Fix | Open | `tags_metadata` 선언 = `[Analytics, Blog, Health, Home, Reply, SNS, User]`. `Analytics` 선언·미사용, `Auth` 사용·미선언. | Phase 9. `Analytics` 제거 + `Auth`/`Catalog`/`Reports` 추가. |
| F-006 | HIGH | 2-2 위협 모델(무인증 Admin 의 운영 반입 차단) | Fix | **Fixed** | `config.py` 에 ENV 기반 배포 안전성 게이트가 아예 없었음(staging/production 에서 `ADMIN=true`·`DEBUG=true`·placeholder secret·와일드카드 CORS 가 전부 통과). | **Phase 0 서술 정정**: 처음에는 "authentication_backend 미주입" 을 결함으로 적었으나, 2026-08-12 에 "SQLAdmin 인증 백엔드 미부착 = 영구 비목표" 로 확정돼 있었다(ADR-005). 인증 주입은 요구사항 회귀이므로 취소하고, 올바른 방어선인 fail-fast 로 재정의해 구현했다. 회귀: `tests/core/test_deployment_safety.py`(13). |
| F-007 | MED | 2-1 지원 구성(MySQL 통합) | Fix | Open | `compose.test.yaml` 부재. `.github/workflows/ci.yml` 에 MySQL service/통합 단계 없음(pytest 단계만 존재, skip/xfail 0 게이트는 이미 있음). | Phase 5. MySQL 없이 전부 skip 된 초록은 C-4 위반이므로 인프라 선행 필요. |
| F-008 | MED | C-9 / INV-5 (발견과 결선의 분리) | Fix | **Fixed** | 기능 `__init__.py` 6개가 라우터·모델을 eager import 해, `discover()` 만으로 라우팅 트리와 DB 모델 **29개 모듈**이 메모리에 올라왔다. `home/access_log_sink.py` 는 모듈 레벨에서 `background_session`·서비스까지 끌어왔다. | Phase 1 에서 발견. init 경량화 + sink 의 DB import 를 호출 시점으로 이동. 회귀: `tests/core/test_import_boundary.py`(서브프로세스로 실제 경계 측정, 2). |
| F-009 | HIGH | charter 3 인수기준(자원 회수) | Fix | **Fixed** | `lifespan` 의 정리 코드가 `yield` **뒤에만** 있어, startup 실패(테이블 생성 실패 등) 시 `drain()`/`dispose_engine()` 에 도달하지 못했다 — 기동 재시도마다 커넥션이 누적된다. | Phase 1 에서 발견. try/finally 로 전환. 회귀: `tests/test_lifespan.py`(3) — 수정 전 실패 경로 RED 확인. |
| F-010 | MED | C-5 (로그 보존) | Fix | **Fixed** | `migrations/env.py` 의 `fileConfig()` 가 기본값 `disable_existing_loggers=True` 로 동작해 migration 이 돌 때마다 기존 앱 로거가 조용히 꺼졌다. | Phase 1 에서 발견. 플래그 명시. 회귀: `tests/core/test_alembic_logging.py`(AST 검사 + 동작 검증, 2). |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
- Phase 6~8 의 Raw Base / catalog / reports 는 "미구현 신규 범위"이므로 결함이 아니라
  checklist 와 development-plan §10 에서 추적한다.
-->
