# Run Log — orm-raw-repository (라운드 로그 + 수렴 판정)

## 라운드 기록

### Round 0 — 2026-08-18 (base SHA: `76aed3c1aea2d3f1754f650ba631c8d853562cec`)
- **트리거:** 사용자 요청 REQ-002 — "docs/orm-raw-repository/ 설계·개발계획서를 참고로 작업 진행".
- **검수 범위:** Phase 0 기준선 전수 측정 (코드 변경 없음).
- **GATE 통과:** 0 ☑ 1 □ 2 □ 3 □ 4 □ 5 □
- **측정 결과 (artifact: `baseline/`):**
  - `env.txt` — commit `76aed3c`, branch `main`, Python 3.14.4, `uv.lock` sha256 `d1bc64a8…c9d7b8`,
    `pyproject.toml` sha256 `f4eb895b…22022022`, `alembic heads` = `b2f1a9c0d3e4 (head)` 단일
  - `pytest.txt` — **271 passed** (skip/xfail/deselected 0)
  - `survey.txt` — OpenAPI **18 paths / 30 operations**, 정규화 sha256
    `4ce7f6b6e931358029b265f8946ae931f0d873a92c018f009c6981d8944ae98a`,
    operationId 누락 0 / 중복 0, component schemas 31개
  - `openapi.json` — 정렬 고정 스냅샷(골든)
  - registry 자동 발견 앱 6개 `[auth, blog, home, reply, sns, user]`,
    metadata 테이블 5개 `[blog_posts, replies, sns_posts, user_access_logs, users]`,
    Admin ModelView 5개 `[PostAdmin, ReplyAdmin, SnsPostAdmin, UserAccessLogAdmin, UserAdmin]`
  - `CRUDBase` 메서드 4개(`_get/_add/_update/_delete`), `BaseRepository` 공개 메서드 28개
  - CI: `.github/workflows/ci.yml` 에 pytest + skip/xfail 0 게이트 존재, **MySQL service 없음**,
    `compose.test.yaml` 없음, `scripts/` 에 `review_gate.py` 없음(`new_app.py` 만 존재)
  - SQL 로깅: `session.py:82,111,170` 모두 `echo=False` (redaction 미구현 → R-007)
  - `/admin`: `authentication_backend` 미주입 (`app/features/admin.py:71` 주석만) → F-006
- **신규 finding(심각도별):** CRIT 0 · HIGH 3 · MED 3 · LOW 1
- **신규 Fix(계약 위반):** 7 건 → ledger F-001 ~ F-007
- **수렴 판정:** `NOT CONVERGED` (Open Fix 7건, Phase 1~9 미착수)
- **잔여 위험 변화:** R-001 ~ R-007 최초 등록.
- **깊이 주석:** 이번 라운드는 *측정·기록 전용*이며 소스 코드를 변경하지 않았다. F-001~F-007 은
  모두 계획서가 사전 예고한 항목이며, 실제 코드 위치를 확인해 확정한 것이다(신규 발견이 아니라 확증).
  F-004(모듈 경로형 스키마명 2건)와 F-005(tags 불일치)는 계획서에 개수·대상이 명시돼 있지 않았고
  이번 측정에서 처음 구체적으로 특정했다.

### Round 1 — 2026-08-18 (base SHA: `2804f6c`) — Phase 1 Runtime/lifecycle hardening
- **트리거:** REQ-002 승인 — Phase 1 전체 착수(사용자 확인 완료).
- **검수 범위:** runtime/lifecycle 경계 (main.py · db/session.py · registry 경계 · logging · config).
- **GATE 통과:** 0 ☑ 1 ☑ 2 □ 3 □ 4 □ 5 □
- **처리한 Fix:** F-001, F-006(재정의), F-008, F-009, F-010 → 전부 Fixed.
- **신규 finding:** F-008(MED), F-009(HIGH), F-010(MED) — Phase 1 작업 중 발견해 같은 라운드에서 처리.
- **요구사항 회귀 차단 1건:** Phase 0 의 F-006 서술("authentication_backend 주입")이 2026-08-12 확정
  결정(Admin 인증 = 영구 비목표)을 뒤집는 방향이었다. 구현 전에 `config.py` 주석에서 발견해 ADR-005·C-8 로
  승계하고, 방어선을 fail-fast 로 재정의했다. **코드로 옮기기 전에 잡았다.**
- **변경 요약:**
  - `db/session.py` — `create_db_tables()` 의 `import_all_models()` 제거, 빈 metadata 거부 가드 추가
  - `config.py` — `validate_deployment_safety()` 추가(import 시점 실행). staging/production 에서
    DEBUG·ADMIN·placeholder secret·와일드카드 CORS 를 **한 번에 모두** 보고하고 기동 거부. 메시지에 값 미포함
  - `app/utils/logs/filters.py` — `RedactingFilter` 추가, `config.py`/`setup.py` dictConfig 에 결선
  - `migrations/env.py` — `fileConfig(..., disable_existing_loggers=False)`
  - `main.py` — `/ready` 추가(DB 왕복 1회, 실패 시 503·정보 비노출), lifespan 정리를 try/finally 로 이동
  - `app/features/*/__init__.py` 6개 경량화, `home/access_log_sink.py` DB import 지연
  - 골든 인벤토리 `tests/test_route_inventory.py` 에 `/ready` 반영
- **계약 변경 2건(테스트 갱신):** `tests/utils/test_logs.py` 핸들러 필터 기대치 `["context"]` → `["context","redact"]`;
  `app/features/home/tests/test_home_config.py` 의 `home.router` 재노출 단언 → 경량화 계약 단언으로 교체
  (의도인 "home 라우터가 /api 에 마운트된다" 는 보존).
- **게이트 결과:** pytest **315 passed**(기준선 271 + 신규 44), skip/xfail/deselected 0 · ruff check 통과 ·
  ruff format 통과 · mypy 148 files 통과 · bandit 무이슈 · `alembic heads` 단일 · 인벤토리 **19 paths / 31 operations**(Phase 1 목표치 일치)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4건: F-002, F-003, F-004, F-005, F-007 중 Phase 2~9 대상)
- **잔여 위험 변화:** R-007 **해소**(구조적 redaction 도입). R-008 신규 등록(Celery 종료 대상 없음).

### Round 2 — 2026-08-18 (base SHA: `b6d1aa2`) — Phase 2 read-only 안전성
- **트리거:** 사용자 요청 "Phase 2 진행해줘".
- **검수 범위:** read-only 계약 경계 (`db/router.py`, `db/session.py`) + Dependency 명명 전면 전환.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **처리한 Fix:** F-003 → Fixed.
- **변경 요약:**
  - 집행 지점 이동 — `RoutingSession.get_bind()` 안에만 있던 차단을 `Session` 클래스
    이벤트(`before_flush`, `do_orm_execute`)로 옮겼다. sessionmaker·엔진과 무관하게
    적용되므로 `DB_ROUTER_ENABLED=false` 와 `BackgroundSessionLocal` 에서도 동일하게 막힌다.
  - 중앙 API `is_read_only()` / `assert_writable()` 도입.
  - Raw SQL 은 default-deny 판별(`_text_is_readable`) — 주석 제거 후 SELECT 로 시작하고
    잠금(`FOR UPDATE` / `LOCK IN SHARE MODE`)을 잡지 않는 **단일** 문장만 허용.
    `WITH`·저장 프로시저·multi-statement·판별 불가 문장은 거부.
  - Dependency 정식 명명 도입(workflow-guide §2.1): `get_read_only_db_session`,
    `get_writer_db_session`, `get_routed_db_session`, `get_background_db_session`,
    `background_db_session`. 기존 이름은 **동일 객체 alias** 로 유지해
    `dependency_overrides` 키를 보존했다.
  - 저장소 내 호출부 103건(26개 파일)을 정식 이름으로 전환하고, 재발을 AST 스캔으로 고정.
- **검증 설계:** 라우터 on/off 를 fixture 로 parameterize 해 같은 계약을 양쪽에서 검사한다
  (ORM flush / Core insert·update·delete / Raw DML·DDL / 잠금·CTE·multi-statement 거부 /
  ORM·Raw SELECT 허용 / 쓰기 세션 대조군 / 차단 후 row count 불변). 테스트 모델은 별도
  `DeclarativeBase` 를 써서 공유 metadata 를 오염시키지 않는다(workflow-guide §14).
- **자체 결함 1건(같은 라운드에서 교정):** 호출부 일괄 rename 이 방금 작성한 명명 테스트의
  **문자열 리터럴까지** 바꿔 alias 표가 canonical→canonical 로 붕괴했다(검사가 자기 자신을
  무력화). AST 가드가 이를 드러냈고, 표를 조각 합성으로 바꿔 같은 사고가 재발하지 않게 했다.
- **신규 finding:** 0 (F-003 외 신규 계약 위반 없음)
- **게이트 결과:** pytest **385 passed**(Phase 1 315 + 신규 70), skip/xfail/deselected 0 ·
  ruff check/format · mypy 148 files · bandit 0 issues · `alembic heads` 단일 ·
  라우트 인벤토리 **19 paths / 31 operations**(Phase 1 대비 불변, 골든 테스트 통과)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4건: F-002·F-004·F-005·F-007 → Phase 3/9/9/5)
- **잔여 위험 변화:** R-001 문구를 "구현된 default-deny" 로 정정(읽기 전용 CTE 도 함께 막히는
  대가를 명시). R-009 신규 — `session.info` 는 보안 경계가 아니며 운영은 read-only credential 을
  최종 방어선으로 둔다.

### Round 3 — 2026-08-19 (base SHA: `cbb147f`) — Phase 1-R 잔여 정리
- **트리거:** 사용자 요청 "남은 작업 정리" → 정리 중 **Phase 1 완료 보고가 부정확했음을 발견**.
  Phase 1 은 계획서 §10 의 요약 줄만 보고 수행했고, 상세 사양인 **§8** 의 항목들이 남아 있었다.
  사용자가 권장안(잔여 상위 5건 선처리 → Phase 3)을 승인해 이 라운드를 열었다.
- **검수 범위:** 계획서 §8 전 항목을 현재 코드와 1:1 대조.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **신규 finding 10건 등록:** F-011(HIGH) · F-012~F-013(MED) · F-014~F-015(LOW) → 이번 라운드 Fixed.
  F-016~F-020 은 인프라성이라 **Phase 1-R2 로 이월**하고 Open 으로 추적한다(프로세스 밖에 두지 않는다).
- **처리 요약:**
  - F-011 `TRUST_PROXY_HEADERS`(기본 false) — 전달 헤더는 신뢰 proxy 설정이 있을 때만 채택
  - F-012 access/refresh 서명 키 동일 사용 거부
  - F-013 `/ready` 4건 사양 정렬 — `getReadiness`, `HealthResponse` 200 / `ErrorResponse` 503,
    **writer** `SELECT 1`, 2초 timeout
  - F-014 전역 예외 핸들러 — 응답 detail 항상 None, 로그는 route template
  - F-015 `ADMIN=false` lazy import 회귀 테스트(서브프로세스 + 대조군)
- **기존 계약 테스트가 잡은 것 1건:** `test_every_config_field_is_documented_in_env_example` 가
  신규 `TRUST_PROXY_HEADERS` 의 `.env.example` 누락을 즉시 잡았다. 문서화 후 통과.
- **fail-on-revert 확인:** F-014 의 누출을 일부러 되돌리자 테스트가 실패했고, 복원하니 통과했다.
- **게이트 결과:** pytest **401 passed**(Phase 2 385 + 신규 16), skip/xfail/deselected 0 ·
  ruff check/format · mypy 148 files · bandit 0 issues · alembic single head ·
  라우트 인벤토리 19 paths / 31 operations 불변
- **수렴 판정:** `NOT CONVERGED` (Open Fix 9건: F-002·F-004·F-005·F-007 + 이월 F-016~F-020)

### Round 4 — 2026-08-19 (base SHA: `f270945`) — Phase 3 ORM 모델/Base
- **트리거:** 승인된 권장안의 두 번째 단계.
- **검수 범위:** 공통 모델 계층(`models_base.py`, 5개 기능 모델)과 Repository PK 계약.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 3 한정) 4 □ 5 □
- **처리한 Fix:** F-002 → Fixed.
- **발견:** mixin 은 `models_base.py` 에 정의만 되어 있고 **어떤 모델도 쓰지 않았다**.
  5개 모델이 동일한 `id`/`created_at`/`updated_at` 정의를 각자 복사해 두고 있었다 —
  한쪽만 고치면 조용히 어긋나는 구조.
- **변경 요약:**
  - `UUIDPrimaryKeyMixin` / `CreatedAtMixin` / `UpdatedAtMixin` 으로 재구성, 기존
    `UUIDMixin`·`TimestampMixin` 은 동일 객체 alias 로 유지
  - 5개 모델을 mixin 조합으로 전환. `user_access_logs` 는 `UpdatedAtMixin` 을
    상속하지 않아 없던 컬럼이 새로 생기지 않는다
  - `CRUDBase[ModelType, PrimaryKeyType]`(PEP 696 기본값 `str`) + `pk_attr` + `_pk` 도입.
    기존 선언 `BaseRepository[Model]` 도 그대로 유효하다
  - `_get()` 의 `str(id)` 제거 — PK 를 선언된 타입 그대로 전달
  - `BaseRepository` 의 `self.model.id` 10곳을 `self._pk` 로, `id: str` 시그니처를
    `PrimaryKeyType` 으로 관통. 5개 기능 Repository 는 `[Model, str]` 로 명시
- **schema diff 0 증명:** 리팩터링 **이전** 스키마 서명을 `baseline/schema.json` 골든으로
  떠 두고 전환 후 대조(6건 통과). 여기에 더해 기존
  `test_migration_chain.py::test_migrated_schema_matches_models` 도 통과한다.
- **자체 결함 1건(같은 라운드에서 교정):** PK 테스트용 더미 모델을 공유 `Base` 에 붙여
  `Base.metadata` 를 오염시켰고, 마이그레이션 대조 테스트가 즉시 깨졌다. 지침 §14 대로
  별도 `DeclarativeBase` 로 분리했다. **기존 테스트가 제 실수를 잡은 사례.**
- **mypy 가 잡은 것 2건:** `_pk` 의 Any 반환, `_get` 에 `str` 을 넘기던 `BaseRepository`
  내부 호출. 후자는 시그니처가 아직 `id: str` 로 못박혀 있던 진짜 누락이었다.
- **게이트 결과:** pytest **436 passed**(Phase 1-R 401 + 신규 35), skip/xfail/deselected 0 ·
  ruff check/format · mypy 148 files · bandit 0 issues · alembic single head ·
  라우트 인벤토리 19 paths / 31 operations 불변
- **수렴 판정:** `NOT CONVERGED` (Open Fix 8건: F-004·F-005·F-007 + 이월 F-016~F-020)

### Round 5 — 2026-08-19 (base SHA: `d6ca983`) — Phase 4 ORM Repository
- **트리거:** 사용자 승인 후 Phase 4 착수.
- **검수 범위:** `CRUDBase` / `BaseRepository` 전 표면과 그 호출부.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 4 한정) 4 □ 5 □
- **사용처 조사(계획서가 정한 첫 단계):** 공개 메서드 28개 중 **20개는 프로덕션·테스트
  호출부가 0건**이었다. `exists` 의 테스트 12회는 전부 `Path.exists()` 오탐이었고,
  `update`/`delete` 의 일부 hit 도 `dict.update()` / `session.delete()` 오탐이었다.
  실제로 이전이 필요한 것은 `get_one` 2곳뿐이었다.
- **STOP 이행:** 제거 목록을 사용자에게 제시하고 승인받은 뒤 삭제했다.
- **처리 순서(계획서 §4):** 사용처 조사 → 호출부 전환 → 제거 → 계약 구현.
  호출부가 0건이라 `get_one` 외에는 호환 wrapper 단계가 불필요했다.
  - `auth_service.get_user_by_id()` 의 `get_one(id=...)` 는 PK 조회라 `get_by_id()` 로 동등 대체
  - `user_repository.get_by_username()` 은 기능 Repository 가 직접 소유하도록 이관
- **신규 finding 4건:** F-021(MED) · F-022(MED) · F-023(HIGH) · F-024(LOW) → 전부 같은 라운드 Fixed.
  특히 **F-023 은 드라이버 오류 원문이 API 응답으로 나가던 C-5 위반**이다.
- **표면 축소 결과:** `BaseRepository` 28 → **8**, `repository_base.py` 1012 → 439행.
  `CRUDBase` 는 `_update`(= `_add` 별칭) 를 걷어내고 계획서가 정한 primitive
  (`_get`/`_add`/`_delete`/`_flush`/`_refresh`)로 정리했다.
- **자체 결함 1건:** 신규 계약 테스트가 `User` 를 함수 안에서 import 해 `create_all` 시점에
  `users` 테이블이 없었다 — 단독 실행 시에만 깨지는 순서 의존이었다. 모듈 최상단 import 로 교정.
- **게이트 결과:** pytest **453 passed**(Phase 3 436 + 신규 17), skip/xfail/deselected 0 ·
  ruff check/format · mypy 148 files · bandit 0 issues · alembic single head ·
  라우트 인벤토리 19 paths / 31 operations 불변
- **수렴 판정:** `NOT CONVERGED` (Open Fix **8건**: F-004·F-005·F-007 + 이월 F-016~F-020)

### Round 6 — 2026-08-19 (base SHA: `823fa59`) — Phase 5 MySQL 테스트 인프라
- **트리거:** 사용자 제안 — "WSL 에 직접 컨테이너를 구축 후 진행하면 되지 않나".
- **판단 정정:** 직전 라운드에서 나는 Windows 셸의 PATH 에 docker 가 없다는 이유로
  "로컬 검증 불가" 라고 결론내고 Phase 7 선행을 권했다. **성급했다.** WSL 안에는
  docker 29.6.1 이 있었고, sibling 저장소들이 이미 같은 패턴으로 테스트 컨테이너를
  쓰고 있었다(`fastapi-passive-mysql-test` 등). 계획서 순서대로 Phase 5 를 진행했다.
- **검수 범위:** MySQL 통합 인프라 신설 + CI 마커 경계.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 5 한정) 4 □ 5 □
- **처리한 Fix:** F-007 → Fixed.
- **재사용:** sibling(passive-style)의 `compose.test.yaml` / `tests/integration/conftest.py`
  패턴을 그대로 이식했다. 포트만 3310 으로 바꾼 것이 아니라 **DB·계정 이름도 이 저장소
  전용**으로 두었다 — 격리는 포트가 아니라 자격증명으로 보장한다는 그쪽의 실전 근거를 따랐다.
- **sibling 의 버그는 베끼지 않았다:** passive-style 의 mysql job 은 `-m mysql` 이 항상
  만드는 `deselected` 를 실패 조건으로 grep 해서, 성공해도 실패로 판정된다. active-style
  에서는 `skipped` 만 판정하고 deselect 는 정상 결과로 둔다.
- **CI 구조:** gate job 은 `-m "not mysql"` 로 돌고 SKIP 판정에서 `deselected` 를 뺀다.
  mysql job 이 compose 를 띄우고 (1) `-m mysql` 을 skip 0 으로, (2) **전체 suite** 를
  skip·deselect 0 으로 검증한다. 계획서 §10 의 "전체 suite skip/xfail/deselected 0" 은
  MySQL 이 떠 있는 이 job 에서만 성립하므로 거기서 한 번 전수 확인한다.
- **로컬 실측 결과:** MySQL 8.4.11 컨테이너에 대해
  `pytest -m mysql` **5 passed(skip 0)**, 전체 suite **458 passed(skip·deselect 0)**.
  Alembic chain 은 MySQL 에서 head → base → head 왕복이 모두 성공했고,
  적용 결과가 모델 metadata 와 일치함(`compare_metadata` diff 0)까지 확인했다.
- **삽질 기록:** 컨테이너가 반복적으로 정지했다. 원인은 Windows 쪽 `wsl.exe` 프로세스가
  없으면 WSL 배포판이 통째로 내려가는 것이었고, 배포판 안에서 `nohup` 으로 붙잡는 것은
  소용없었다(배포판 종료 시 함께 죽는다). 증상이 "방금 5 passed 였는데 전부 skip" 이라
  테스트 결함으로 오인하기 쉽다 — `compose.test.yaml` 주석과 residual-risk R-010 에 기록했다.
- **신규 finding:** 0
- **게이트 결과:** ruff check/format · mypy 148 files · bandit 0 issues · alembic single head ·
  라우트 인벤토리 19 paths / 31 operations 불변
- **수렴 판정:** `NOT CONVERGED` (Open Fix 7건: F-004·F-005 + 이월 F-016~F-020)

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 3 | 1 | 7 | NOT CONVERGED |
| 1 | 0 | 1 | 2 | 0 | 3 (전부 같은 라운드에 Fixed) | NOT CONVERGED (Open Fix 5 → Phase 2~9) |
| 2 | 0 | 0 | 0 | 0 | 0 (F-003 해소) | NOT CONVERGED (Open Fix 4 → Phase 3·5·9) |
| 3 | 0 | 1 | 6 | 3 | 10 (5 Fixed / 5 이월) | NOT CONVERGED (Open Fix 9) |
| 4 | 0 | 0 | 0 | 0 | 0 (F-002 해소) | NOT CONVERGED (Open Fix 8) |
| 5 | 0 | 1 | 2 | 1 | 4 (전부 같은 라운드에 Fixed) | NOT CONVERGED (Open Fix 7) |
| 6 | 0 | 0 | 0 | 0 | 0 (F-007 해소) | NOT CONVERGED (Open Fix 7) |
