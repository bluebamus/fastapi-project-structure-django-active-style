# Checklist — orm-raw-repository (개선 항목 추적판)

> **모든 개선 사항은 여기서 추적된다.** 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다.
> ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-08-18 (Phase 0: 기준선, 코드 무변경)
- [x] 이번 요청을 design-baseline §2(REQ-002)에 기록 + 이전 요구(REQ-001) 충돌 확인 — 충돌 없음
- [x] CRP 그룹 6파일 적재 (`_template` 복사 후 작성)
- [x] 기준선 artifact 생성 — `baseline/{env.txt,pytest.txt,survey.txt,openapi.json}`
- [x] 결함 ledger 착수 — F-001 ~ F-007 등록(전부 코드 위치 확인 완료)
- [x] residual-risk 착수 — R-001 ~ R-007 등록
- [x] run-log Round 0 기록 + 수렴 판정(NOT CONVERGED)
- [x] **STOP: Phase 1 착수 승인** — 사용자 승인 완료(전체 진행)
- [x] Phase 0 커밋 `2804f6c`

## Round 1 — 2026-08-18 (Phase 1: Runtime/lifecycle hardening) — 완료
- [x] (ledger F-001) `create_db_tables()` 재-discovery 제거 + 빈 metadata 거부 — `tests/core/test_create_db_tables.py`
- [x] (ledger F-006, **재정의**) staging/production 배포 안전성 fail-fast — `tests/core/test_deployment_safety.py`
      · ADR-005 로 "Admin 인증 백엔드 = 영구 비목표" 를 승계. `ADMIN` lazy import 는 이미 충족(main.py)
- [x] (residual R-007 → 해소) `RedactingFilter` 로 DSN·secret 마스킹 — `tests/utils/test_log_redaction.py`
- [x] (ledger F-010) Alembic `fileConfig(disable_existing_loggers=False)` — `tests/core/test_alembic_logging.py`
- [x] (ledger F-008) 기능 `__init__.py` 6개 경량화 + sink DB import 지연 — `tests/core/test_import_boundary.py`
- [x] (ledger F-009) lifespan 정리를 try/finally 로 이동(startup 실패 cleanup) — `tests/test_lifespan.py`
- [x] `/ready` 추가 → 라우트 인벤토리 **19 paths / 31 operations** 확인·고정
- [x] Celery 종료: 대상 없음으로 판정하고 residual-risk R-008 에 기록(추측성 코드 미작성)
- [x] Phase 1 게이트 전량 그린: pytest 315 / ruff / format / mypy / bandit / alembic single head
- [x] 요구사항 회귀 0 — design-baseline Active 요구·불가침 제약 위반 없음(회귀 1건은 구현 전 차단)
- [x] run-log 심각도 추세 갱신 + 수렴 판정(NOT CONVERGED)
- [x] residual-risk 갱신(R-007 해소, R-008 신규)
- [x] **STOP: Phase 2 착수 승인** — 사용자 승인 완료

## Round 2 — 2026-08-18 (Phase 2: read-only 안전성) — 완료
- [x] (ledger F-003) 설정 무관 read-only DML guard — `Session` 이벤트로 집행 지점 이동
- [x] 중앙 `is_read_only()` / `assert_writable()` 도입
- [x] Raw SQL default-deny 판별(SELECT 단일문·비잠금만 허용, WITH·multi-statement·판별불가 거부)
- [x] 정식 Dependency 명명 5쌍 도입 + 기존 이름을 동일 객체 alias 로 유지(override 키 보존)
- [x] 저장소 내 호출부 103건(26파일) 정식 이름 전환 + AST 재발 방지 가드
- [x] 라우터 on/off parameterize 검증 52건 통과, 라우트 인벤토리 19/31 불변
- [x] Phase 2 게이트 전량 그린: pytest 385 / ruff / format / mypy / bandit / alembic single head
- [x] run-log Round 2 + residual-risk(R-001 정정, R-009 신규) 갱신
- [x] **STOP: Phase 3 착수 승인** — 사용자 승인(권장안: Phase 1-R 선처리 후 Phase 3)

## Round 3 — 2026-08-19 (Phase 1-R: Phase 1 잔여 상위 5건) — 완료
- [x] (F-011) `TRUST_PROXY_HEADERS` 도입 — 전달 헤더 무조건 신뢰 제거 + `.env.example` 문서화
- [x] (F-012) access/refresh JWT 서명 키 동일 사용 거부
- [x] (F-013) `/ready` 사양 4건 정렬 (`getReadiness` / HealthResponse·ErrorResponse / writer SELECT 1 / 2초 timeout)
- [x] (F-014) 전역 예외 핸들러 raw detail 제거 + route template 로깅 (fail-on-revert 확인)
- [x] (F-015) `ADMIN=false` lazy import 회귀 테스트
- [x] 게이트: pytest 401 / ruff / format / mypy / bandit / alembic single head, 인벤토리 19-31 불변
- [x] 미이행 §8 항목 5건을 F-016~F-020 으로 ledger 등록(프로세스 밖에 두지 않음)

## 이월 — Phase 1-R2 (인프라성, Phase 5 전후 권장)
- [ ] (F-016) `app/core/resources.py` resource manager + background task 종료 계약
- [ ] (F-017) bounded logging queue(QueueHandler/Listener), 파일 I/O 를 event loop 밖, bootstrap 1회
- [ ] (F-018) SQL noise filter + `LOG_SQL_ECHO_ENABLED` opt-in(development/test 한정)
- [ ] (F-019) Celery prefork `worker_process_init/shutdown`, 단일 worker startup DDL 제한
- [ ] (F-020) `home/__init__.py` import-time sink 를 명시적 멱등 init hook 으로 이동

## Round 4 — 2026-08-19 (Phase 3: ORM 모델/Base) — 완료
- [x] `UUIDPrimaryKeyMixin`/`CreatedAtMixin`/`UpdatedAtMixin` 구성 + 기존 이름 alias 유지
- [x] 5개 모델을 mixin 조합으로 전환 (중복 컬럼 정의 제거)
- [x] (F-002) `CRUDBase[ModelType, PrimaryKeyType]` + `pk_attr` + `_pk`, `_get()` str 변환 제거
- [x] `BaseRepository` 의 `self.model.id` 10곳·`id: str` 시그니처를 PK 타입으로 관통
- [x] **schema diff 0** — 사전 골든(`baseline/schema.json`) 대조 + 기존 마이그레이션 대조 테스트
- [x] 게이트: pytest 436 / ruff / format / mypy / bandit / alembic single head
- [ ] **STOP: Phase 4 착수 승인**

## Round 5 — 2026-08-19 (Phase 4: ORM Repository) — 완료
- [x] 사용처 조사 — 28개 중 20개 호출부 0건 확인, 오탐 분리
- [x] **STOP: 제거 목록 사용자 승인**
- [x] `get_one` 호출부 2곳 이전 (auth_service → `get_by_id`, user_repository → 직접 구현)
- [x] 20개 메서드 제거 — 공개 표면 28 → 8, `repository_base.py` 1012 → 439행
- [x] `CRUDBase` primitive 정리 — `_update` 제거, `_flush`/`_refresh` 도입
- [x] (F-021) 입력 mapping 복사 + PK 임의 주입 제거
- [x] (F-022) update/delete 단일 엔티티 선조회, unknown/PK 변경 거부, 빈 PATCH no-op
- [x] (F-023) 예외 detail·로그에서 드라이버 오류 원문 제거
- [x] (F-024) `exists` 를 COUNT → EXISTS 로 교체
- [x] 게이트: pytest 453 / ruff / format / mypy / bandit / alembic single head
- [ ] **STOP: Phase 5 착수 승인**

## 예정 — Phase 5 이후
- [ ] Phase 4 ORM Repository 최소 CRUD·입력 불변성·EXISTS·예외 변환
- [ ] Phase 5 (F-007) `compose.test.yaml` + CI MySQL service, Alembic chain up/down/re-up smoke
- [ ] Phase 6 Raw Base — one/all/scalar/rowcount·binding·query name·예외·read-only 계약
- [ ] Phase 7 catalog(ORM) 예제 자동배선
- [ ] Phase 8 reports(Raw) 예제 자동배선
- [ ] Phase 9 (F-004, F-005) OpenAPI/문서 정리 + `scripts/review_gate.py` + 최종 인벤토리 22/37

> 미닫힘(`[ ]`) 항목이 1개라도 있으면 그 라운드는 GATE 5 Done 이 아니다.
