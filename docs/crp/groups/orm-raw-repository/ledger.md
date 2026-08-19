# Ledger — orm-raw-repository (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(→residual-risk) / **Wont-fix**(오탐).
> 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(코드 위치) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | HIGH | INV-5 (동일 registry 재사용) | Fix | **Fixed** | `app/core/db/session.py:227-230` 이 `import_all_models()` 로 모델을 재-discovery. `main.py:70` 의 `create_db_tables()` 호출 경로. | Phase 1 완료. `import_all_models()` 호출 제거 + 빈 metadata 거부 가드. 회귀: `tests/core/test_create_db_tables.py`(3) — 수정 전 RED 확인. |
| F-002 | MED | 2-1 지원 구성(PK 타입 보존) | Fix | **Fixed** | `app/core/repositories/crud_base.py:59` — `session.get(self.model, str(id))` 로 PK 를 문자열 강제 변환. | Phase 3 완료. `CRUDBase[ModelType, PrimaryKeyType]`(PEP 696 기본값 str) + `pk_attr` + `_pk` 도입, `_get()` 은 PK 를 그대로 전달. `BaseRepository` 의 `id: str` 10곳도 `PrimaryKeyType` 으로 관통. 회귀: `tests/core/test_pk_generic.py`(9, str/int/UUID/tuple 보존). |
| F-003 | HIGH | INV-4 (설정 무관 read-only 보장) | Fix | **Fixed** | 가드가 `app/core/db/router.py:141-147` 의 `RoutingSession.get_bind()` 안에만 존재. `session.py:147`(라우터 on) 만 이 클래스를 쓰고 `:149`(라우터 off) 는 평범한 `async_sessionmaker` 를 쓴다. `:184` `BackgroundSessionLocal` 도 항상 비보호. | Phase 2 완료. 집행 지점을 `RoutingSession.get_bind()` 에서 **`Session` 클래스 이벤트**(`before_flush` / `do_orm_execute`)로 옮겨 sessionmaker·엔진과 무관하게 적용. 중앙 `is_read_only()`/`assert_writable()` 도입, Raw SQL 은 default-deny 판별. 회귀: `tests/core/test_read_only_guard.py`(52, 라우터 on/off parameterize). |
| F-004 | MED | INV-8 (OpenAPI 스키마명) | Fix | Open | component schemas 31개 중 2개가 모듈 경로형: `app__features__auth__schemas__auth_schema__UserResponse`, `app__features__user__schemas__user_schema__UserResponse`. | Phase 9. auth/user 의 `UserResponse` 이름 충돌로 FastAPI 가 모듈 경로를 붙임. 명시적 스키마명 부여로 해소. |
| F-005 | LOW | INV-8 (tag 일관성) | Fix | Open | `tags_metadata` 선언 = `[Analytics, Blog, Health, Home, Reply, SNS, User]`. `Analytics` 선언·미사용, `Auth` 사용·미선언. | Phase 9. `Analytics` 제거 + `Auth`/`Catalog`/`Reports` 추가. |
| F-006 | HIGH | 2-2 위협 모델(무인증 Admin 의 운영 반입 차단) | Fix | **Fixed** | `config.py` 에 ENV 기반 배포 안전성 게이트가 아예 없었음(staging/production 에서 `ADMIN=true`·`DEBUG=true`·placeholder secret·와일드카드 CORS 가 전부 통과). | **Phase 0 서술 정정**: 처음에는 "authentication_backend 미주입" 을 결함으로 적었으나, 2026-08-12 에 "SQLAdmin 인증 백엔드 미부착 = 영구 비목표" 로 확정돼 있었다(ADR-005). 인증 주입은 요구사항 회귀이므로 취소하고, 올바른 방어선인 fail-fast 로 재정의해 구현했다. 회귀: `tests/core/test_deployment_safety.py`(13). |
| F-007 | MED | 2-1 지원 구성(MySQL 통합) | Fix | Open | `compose.test.yaml` 부재. `.github/workflows/ci.yml` 에 MySQL service/통합 단계 없음(pytest 단계만 존재, skip/xfail 0 게이트는 이미 있음). | Phase 5. MySQL 없이 전부 skip 된 초록은 C-4 위반이므로 인프라 선행 필요. |
| F-008 | MED | C-9 / INV-5 (발견과 결선의 분리) | Fix | **Fixed** | 기능 `__init__.py` 6개가 라우터·모델을 eager import 해, `discover()` 만으로 라우팅 트리와 DB 모델 **29개 모듈**이 메모리에 올라왔다. `home/access_log_sink.py` 는 모듈 레벨에서 `background_session`·서비스까지 끌어왔다. | Phase 1 에서 발견. init 경량화 + sink 의 DB import 를 호출 시점으로 이동. 회귀: `tests/core/test_import_boundary.py`(서브프로세스로 실제 경계 측정, 2). |
| F-009 | HIGH | charter 3 인수기준(자원 회수) | Fix | **Fixed** | `lifespan` 의 정리 코드가 `yield` **뒤에만** 있어, startup 실패(테이블 생성 실패 등) 시 `drain()`/`dispose_engine()` 에 도달하지 못했다 — 기동 재시도마다 커넥션이 누적된다. | Phase 1 에서 발견. try/finally 로 전환. 회귀: `tests/test_lifespan.py`(3) — 수정 전 실패 경로 RED 확인. |
| F-010 | MED | C-5 (로그 보존) | Fix | **Fixed** | `migrations/env.py` 의 `fileConfig()` 가 기본값 `disable_existing_loggers=True` 로 동작해 migration 이 돌 때마다 기존 앱 로거가 조용히 꺼졌다. | Phase 1 에서 발견. 플래그 명시. 회귀: `tests/core/test_alembic_logging.py`(AST 검사 + 동작 검증, 2). |
| F-011 | HIGH | 2-2 위협 모델(입력 신뢰 경계) | Fix | **Fixed** | `app/core/middlewares/user_info_middleware.py:86` 이 `X-Forwarded-For`/`X-Real-IP` 를 **무조건** 접속 IP 로 채택. 프록시 뒤가 아닌 배포에서 클라이언트가 헤더 한 줄로 IP 를 위조하고 접속 로그·IP 기반 조회를 오염시킬 수 있었다. | Phase 1-R. `TRUST_PROXY_HEADERS`(기본 false) 도입, 켠 배포에서만 헤더 채택. `.env.example` 문서화. 회귀: `tests/core/test_client_ip_trust.py`(7). |
| F-012 | MED | 2-2 위협 모델(토큰 서명 분리) | Fix | **Fixed** | access/refresh 서명 키가 동일해도 기동이 통과했다 — 같은 키면 refresh 토큰이 access 로도 검증을 통과한다. | Phase 1-R. `validate_deployment_safety()` 에 동일 키 거부 추가. 회귀: `tests/core/test_deployment_safety.py`(+2). |
| F-013 | MED | 계획서 §8 `/ready` 사양 | Fix | **Fixed** | Phase 1 구현이 사양과 4건 어긋났다: operationId `readinessCheck`(사양 `getReadiness`), 전용 `ReadyResponse`(사양 `HealthResponse` 200 / 표준 오류 503), read-only 세션(사양 **writer** `SELECT 1`), timeout 없음(사양 2초). | Phase 1-R. 4건 모두 사양대로 정렬. 회귀: `tests/test_ready.py`(8). |
| F-014 | LOW | C-5 (오류 응답·로그 비노출) | Fix | **Fixed** | 전역 예외 핸들러가 `DEBUG` 에서 `str(exc)` 를 응답에 실었고(개발 환경 예외에도 DSN·쿼리·입력값이 실린다), 로그에 raw path 를 남겨 경로 식별자가 새어나갔다. | Phase 1-R. 응답 detail 은 항상 None, 로그는 route template. 회귀: `tests/test_exception_handler_leak.py`(3) — 누출을 되돌리면 실패함을 확인(fail-on-revert). |
| F-015 | LOW | 계획서 §8 (ADMIN lazy import 검증) | Fix | **Fixed** | 코드는 이미 lazy 였으나 이를 지키는 테스트가 없어 다음 변경이 조용히 깨뜨릴 수 있었다. | Phase 1-R. 서브프로세스로 `ADMIN=false` 시 sqladmin 미적재 확인 + 대조군. 회귀: `tests/core/test_admin_lazy_import.py`(2). |
| F-016 | MED | 계획서 §8 resource manager | Fix | **Open** | `app/core/resources.py` 부재. 현재는 lifespan try/finally 로 직접 정리하며, 자원별 context manager·멱등 cleanup 등록 구조가 없다. | **Phase 1-R2 로 이월**(인프라성). background task admission 닫기·done 예외 소비·timeout 후 cancel·done/pending await 포함. |
| F-017 | MED | 계획서 §8 bounded logging queue | Fix | **Open** | `QueueHandler`/`QueueListener` 미도입. 파일 logging I/O 가 event loop 안에서 일어나고, `uvicorn main:app` import 경로에서 bootstrap 이 한 번만 되는지 미검증. | **Phase 1-R2 로 이월**. |
| F-018 | MED | 계획서 §8 SQL noise filter | Fix | **Open** | queue handler 의 SQL/driver DEBUG·INFO 차단(WARNING 이상 유지)과 development/test 한정 `LOG_SQL_ECHO_ENABLED` opt-in 이 없다. Phase 1 의 `RedactingFilter` 는 마스킹이지 noise 차단이 아니다. | **Phase 1-R2 로 이월**. F-017 의 queue handler 위에 얹는다. |
| F-019 | MED | 계획서 §8 Celery 생명주기 | Fix | **Open** | prefork `worker_process_init`/`worker_process_shutdown` 에서 child engine/loop 생성·부모 pool 폐기·멱등 정리가 없다. 개발 startup DDL 을 단일 worker 로 제한하는 장치도 없다. | **Phase 1-R2 로 이월**. serializer JSON-only 는 이미 충족(`app/celery/app.py:19-21`). |
| F-020 | LOW | C-9 (발견 단계 부작용) | Fix | **Open** | `home/__init__.py` 의 import-time `register_sink()` 가 남아 있다. 계획서 §3 은 "제거하거나 명시적 멱등 init hook 으로 이동" 을 요구한다. | **Phase 1-R2 로 이월**. 현재도 멱등이고 DB I/O 는 없다(Phase 1 에서 지연 import 로 분리). |
| F-021 | MED | §4 입력 불변성 / PK 소유권 | Fix | **Fixed** | `create()` 가 호출자 dict 에 `data["id"] = str(uuid4())` 를 직접 써넣었다. 호출자 자료구조를 바꾸는 부작용이자, PK 생성 책임을 모델(mixin default)에서 Base 로 끌어온 것이다. 정수 PK·시퀀스·외부 키를 쓰는 모델에서 어긋난다. | Phase 4. 입력을 복사해 쓰고 id 주입을 제거. 회귀: `tests/core/test_repository_contract.py`. |
| F-022 | MED | §4 update/delete 계약 | Fix | **Fixed** | `update()`/`delete()` 가 bulk DML(`update().where()` / `delete().where()`)로 동작해 "없는 행" 과 "변경 없는 행" 을 구분하지 못했고, unknown 필드·PK 변경을 거르지 않았으며 빈 PATCH 의 의미도 정의돼 있지 않았다. | Phase 4. 단일 엔티티 선조회로 전환, unknown/PK 변경 거부, 빈 PATCH 는 존재 확인 후 no-op. |
| F-023 | HIGH | C-5 (오류 응답 비노출) | Fix | **Fixed** | 예외 `detail` 에 `str(e.orig)` / `str(e)` 로 **드라이버 오류 원문**을 담았고, 이 detail 은 `AppException.to_response()` 를 통해 그대로 API 응답으로 나갔다. 제약 이름·컬럼·값 조각이 클라이언트에 노출될 수 있었다. | Phase 4. `_log_db_error()` 로 연산·모델·예외 타입만 남기고 응답 detail 에서 원문 제거. 회귀: 응답 렌더링에 드라이버 문자열이 없음을 단언. |
| F-024 | LOW | §4 exists | Fix | **Fixed** | `exists()` 가 `COUNT(*)` 로 조건에 맞는 행을 끝까지 셌다. | Phase 4. `EXISTS` 로 교체해 첫 행에서 멈춘다. |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
- Phase 6~8 의 Raw Base / catalog / reports 는 "미구현 신규 범위"이므로 결함이 아니라
  checklist 와 development-plan §10 에서 추적한다.
-->
