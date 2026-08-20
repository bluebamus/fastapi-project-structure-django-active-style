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

### Round 7 — 2026-08-19 (base SHA: `99b6bdc`) — Phase 6 Raw Base
- **트리거:** Phase 5 완료 후 사용자 승인.
- **검수 범위:** Raw SQL 데이터 접근 계층 신설(ORM 과 독립).
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 6 한정) 4 □ 5 □
- **신설:**
  - `RawCRUDBase` — primitive 4개. 결과 의미를 계약으로 고정하고 애매한 축약을 전부
    예외로 만든다: `fetch_one` 은 복수 행에서 `MultipleResultsFound`(=`first()` 금지),
    `fetch_scalar` 도 복수 행에서 실패, `execute` 는 commit 하지 않고 rowcount 를
    `int | None` 로 돌려주며 드라이버 미지원 표시(`-1`)를 성공 건수로 공개하지 않는다.
  - 입력 계약 — `TextClause` 만 수용(문자열 금지), multi-statement 거부,
    `ensure_identifier()` 로 코드 소유 allowlist 를 통과한 식별자만 허용.
  - `RawRepositoryBase` — 관측 파사드. `query_name`(keyword-only 필수)·소요 시간·
    성공/실패·예외 타입만 기록하고 SQL 본문과 파라미터 값은 남기지 않는다.
- **설계 정정 1건(mypy 가 잡음):** 처음에는 `RawRepositoryBase` 가 `RawCRUDBase` 를
  **상속**하게 두었는데, 하위 클래스가 primitive 에 없는 **필수** 인자(`query_name`)를
  요구해 Liskov 위반이 됐다. mypy 가 7건으로 지적했고, 상속 대신 **합성**(primitive 를
  소유)으로 바꿨다. 타입 문제일 뿐 아니라 실제로도 "RawCRUDBase 를 받는 함수" 에 넘기면
  호출이 깨지는 구조였다.
- **테스트 범위 정정 1건:** 로그 비노출 테스트가 처음에는 caplog 전체를 봤는데, 이는
  aiosqlite/SQLAlchemy 가 DEBUG 에서 스스로 찍는 SQL·파라미터까지 잡아 실패했다.
  그건 이 Base 의 책임이 아니라 로깅 파이프라인의 SQL noise filter 몫이므로
  (ledger F-018, Phase 1-R2 이월) 검사 범위를 `raw_repository` 로거로 좁히고 그 사실을
  테스트에 명시했다.
- **MySQL 통합 검증(Phase 5 하네스 위):** rowcount 실측, `bindparam(expanding=True)` 로
  `IN` 확장, 주입 시도가 값으로만 처리됨, multi-statement 가 드라이버 도달 전 거부됨,
  그리고 **Phase 2 의 read-only 계약이 Raw 경로에도 걸리는지**(DML 차단 + SELECT 허용)를
  실제 MySQL 에서 확인했다 — 두 Phase 가 따로 통과하고 합쳐서 새는 경우를 막는다.
- **신규 finding:** 0 (신설 계층이라 기존 계약 위반 없음)
- **게이트 결과:** 전체 suite **497 passed**(Phase 5 458 + 신규 39, skip·deselect 0) ·
  `-m mysql` **17 passed** · `-m "not mysql"` 480 passed ·
  ruff check/format · mypy 150 files · bandit 0 issues · alembic single head ·
  라우트 인벤토리 19 paths / 31 operations 불변
- **수렴 판정:** `NOT CONVERGED` (Open Fix 7건: F-004·F-005 + 이월 F-016~F-020)

### Round 8 — 2026-08-19 (base SHA: `364ac4e`) — Phase 7 catalog (ORM 예제)
- **트리거:** Phase 6 완료 후 사용자 승인.
- **검수 범위:** 신규 기능 catalog 전 계층 + 자동배선 경계.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 7 한정) 4 □ 5 □
- **의미:** Phase 3~6 에서 만든 Base 를 **신규 기능에 처음 적용**하는 자리였다. 그래서
  CRUD 동작보다 "그 계약이 실전에서 그대로 서는가" 를 봤다.
- **구현:** 모델(mixin 조합)·migration(`c3d5e7a91b02`)·Admin·Repository·Service·
  Dependency·DTO·View·router. 라우트 5 operations / 2 paths, prefix `/v1/catalog`, tag `Catalog`,
  operation ID 는 지침서 표와 1:1 일치. **`main.py` 무수정**으로 자동 발견·마운트됐다(C-1).
  인벤토리 19 → **21 paths / 36 operations**.
- **신규 finding 3건:**
  - **F-026(HIGH)** — 생성기로 앱을 만든 직후 catalog 테이블이 metadata 에 **등록되지 않았다**.
    원인은 `AppModule.import_models()` 가 패키지만 import 해서 등록이 각 앱
    `models/__init__.py` 재export 한 줄에 걸려 있던 것. scaffold 로 만든 모든 앱이
    같은 함정에 빠지는 구조였다. 관례 모듈도 함께 import 하도록 근본 지점을 고쳤다.
  - **F-025(MED)** — 생성기 dependency 템플릿이 `yield` 뒤 commit 과 deprecated alias 를
    가르치고 있었다. `scripts/` 가 Phase 2 AST 스캔 범위 밖이라 빠져나갔다.
  - **F-027(LOW, Open)** — 지침서 §2.1 의 속성 명명(`db_session`)과 실제 코드(`session`)의
    불일치. 전역 rename 이라 이 Phase 범위 밖으로 두고 기록했다.
- **지침서와 의도적으로 다르게 간 것 1건:** 예시가 쓰는 `UUIDTimestampModel` 대신 Phase 3 에서
  확정한 mixin 조합(`UUIDPrimaryKeyMixin`+`CreatedAtMixin`+`UpdatedAtMixin`)을 썼다.
  저장소의 기존 5개 모델이 모두 그 형태이므로 일관성을 택했다.
- **갱신한 골든 4종:** registry 앱 집합, route inventory, Admin 관리 모델 집합, 스키마 스냅샷.
  이 넷이 함께 바뀐 것 자체가 자동배선이 실제로 동작했다는 증거다.
- **쓰기 계약:** 응답 DTO 검증을 **commit 앞**에 두었다(지침서 §3.7). commit 뒤 검증은 만료된
  속성 재조회로 lazy I/O 를 유발하고, 그 실패는 "이미 커밋됐는데 500" 이 된다. 기존 blog 는
  commit 뒤 검증이라 이 부분은 catalog 가 지침서를 따랐다.
- **게이트 결과:** 전체 suite **520 passed**(Phase 6 497 + 신규 23, skip·deselect 0) ·
  ruff check/format · mypy 167 files · bandit 0 issues · `alembic heads` 단일(`c3d5e7a91b02`) ·
  MySQL 통합에서 신규 revision 의 head → base → head 왕복과 모델 대조까지 통과
- **수렴 판정:** `NOT CONVERGED` (Open Fix 8건: F-004·F-005·F-027 + 이월 F-016~F-020)

### Round 9 — 2026-08-19 (base SHA: `40cf36a`) — Phase 8 reports (Raw 예제)
- **트리거:** Phase 7 완료 후 사용자 승인.
- **검수 범위:** 신규 기능 reports 전 계층 + Raw 계약의 실전 적용.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑(Phase 8 한정) 4 □ 5 □
- **의미:** Phase 6 에서 만든 Raw Base 를 **신규 기능에 처음 적용**하는 자리였다.
  그래서 집계 숫자보다 "그 계약이 실전에서 그대로 서는가" 를 봤다.
- **구현:** 원본 모델 `SalesOrder`(집계 전용 모델 없음)·migration(`d4e6f8b12c34`)·
  읽기 전용 Admin·`SalesReportRawRepository`·Service·read-only Dependency·DTO·View·router.
  라우트 1 operation, prefix `/v1/reports`, tag `Reports`, operation ID `getDailySalesReport`.
  **`main.py` 무수정**으로 자동 발견·마운트됐다(C-1). 인벤토리 21 → **22 paths / 37 operations**
  — 계획서 §11 의 최종 목표치와 정확히 일치한다.
- **이 Phase 의 핵심 검증 — 기간 경계:** 집계 SQL 을 흔한 실수인 `created_at <= :end_date`
  로 바꿔 보니 MySQL 통합 4건이 깨졌다("종료일 후반부 주문이 누락됐습니다" 포함).
  `created_at` 은 시각이고 파라미터는 날짜라 `<=` 는 종료일을 통째로 날린다. 이 결함은
  SQLite 에서도 조용히 통과하고 운영에서 "어제 매출이 0" 으로만 드러난다.
- **신규 finding 4건 (전부 같은 라운드에 Fixed):**
  - **F-028(MED)** — 생성기 CLI 가 앱을 만들고도 종료 코드 1 로 죽었다(cp949 × em dash).
    "성공했는데 실패로 보이는" 실패라 체이닝이 조용히 끊긴다.
  - **F-029(MED)** — 지침서 §6 이 요구하는 Raw SQL 정적 검사가 없었다. Phase 6 은 런타임
    계약만 세웠고, 기능이 SQL 을 소유하기 시작한 지금 비로소 실효를 갖는다.
  - **F-030(LOW)** — MySQL 하네스의 기대 테이블 집합이 Phase 5 에 머물러 예제 테이블의
    downgrade 가 검증되지 않고 있었다.
- **SCN-RAW-002(Raw 쓰기):** 운영 HTTP endpoint 를 만들지 않고 테스트 전용 Service/UoW 가
  writer session 의 commit/rollback 을 소유한다. rowcount 실측, 성공 commit 1회, 실패 시
  예외 전파 + DB 상태 불변, read-only 세션의 Raw DML 차단을 MySQL 에서 확인했다.
- **갱신한 골든 4종:** registry 앱 집합(8개), route inventory, Admin 관리 모델 집합,
  스키마 스냅샷. 이 넷이 함께 바뀐 것 자체가 자동배선이 동작했다는 증거다.
- **판단 1건:** 기능 테스트는 MySQL 방언에 의존하는 **한 지점만**(`daily_sales`) 대체하고
  실제 SQL 은 MySQL 통합이 확인한다. 운영 SQL 을 테스트 편의로 문자열 치환하지 않았다.
- **게이트 결과:** 전체 suite **560 passed**(Phase 7 520 + 신규 40, skip·deselect 0) ·
  `-m mysql` 28 passed(skip 0) · ruff check/format · mypy 185 files · bandit MEDIUM 이상 0 ·
  `alembic heads` 단일(`d4e6f8b12c34`) · 인벤토리 22 paths / 37 operations, operation ID 37 고유
- **수렴 판정:** `NOT CONVERGED` (Open Fix 8건: F-004·F-005·F-027 + 이월 F-016~F-020)

### Round 10 — 2026-08-19 (base SHA: `5639b16`) — Phase 9 문서/OpenAPI/최종 게이트
- **트리거:** Phase 8 완료 후 사용자 승인.
- **검수 범위:** 공개 문서 계약, 공급망, 검증 스크립트, 그룹 수렴 판정.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑(ORM/Raw delivery 한정 — 아래 판정 참고)
- **F-004 해소:** auth 의 `UserResponse` 를 `AuthUserResponse` 로 개명. 다만 개명만으로는
  같은 실수가 재발하므로, **component key 의 `__` 자체를 금지**하는 규칙 검사를 세웠다.
  `__` 이름은 공개 계약을 내부 디렉터리 구조에 묶어 파일 이동만으로 클라이언트를 깬다.
- **F-005 해소:** 유령 태그 `Analytics` 제거, `Auth`/`Catalog`/`Reports` 추가, 구현이 끝난
  User/Blog/Reply/SNS 의 "(예정)" 설명 교체. 검사는 **양방향**이다 — 쓰는 태그는 전부
  선언돼야 하고 선언한 태그는 전부 쓰여야 한다. 한쪽만 보면 유령 태그가 계속 쌓인다.
- **DOC-003 이행:** 프로젝트 소유 schema 12개의 필드 description 과 요청 DTO 10개의
  examples 를 채웠다. FastAPI 생성 schema(`HTTPValidationError` 등)는 우리 소유가 아니라
  명시적 집합으로 제외했다(접두사 제외는 우리 DTO 를 실수로 면제시킨다).
- **검증 스크립트:** `scripts/review_gate.py` — 6그룹. 규칙을 전부 `문자열 -> 문제 목록`
  순수 함수로 두어 **일부러 취약한 입력**으로 검출력을 증명한다(46 tests). 통과만 보는
  게이트는 고장나도 초록이다. CI 는 이 파일을 호출하기만 한다 — 판정 규칙이 두 곳으로
  갈리면 "CI 에서만 되는" 상태와 "내 컴퓨터에서만 되는" 상태가 동시에 생긴다.
- **신규 finding 4건 (전부 같은 라운드에 Fixed):**
  - **F-032(HIGH)** — 의존성 취약점 검사가 없었고, 붙여 보니 **12건**이 나왔다.
    starlette·sqladmin·aiomysql·pytest 상향으로 12 → 0. Bandit 은 소스만 보므로
    이 종류는 기존 게이트로는 영원히 안 드러난다.
  - **F-033(MED)** — Action 이 이동 가능한 태그로, 테스트 이미지가 태그로 고정돼 있었다.
  - **F-031(MED)** — 자식 프로세스 출력을 인코딩 미지정으로 읽어 **테스트 결과가 콘솔
    설정에 좌우**됐다. 게이트를 실제로 돌리지 않았으면 드러나지 않았을 항목이다.
  - **F-034(MED)** — README 가 폐기 별칭을 19곳에서 가르치고 있었고, `get_session` 을
    "쓰기용" 으로 설명했다. 그 이름은 Phase 2 이후 **동적 라우팅** 별칭이라, 문서를
    따라 한 쓰기가 승인되지 않은 경로로 나간다.
- **F-027 이관:** 사용자 결정으로 Accept-out-of-scope → R-011. 동작을 결정하는 Dependency
  함수 이름은 Phase 2 에서 끝났고, 남은 것은 내부 속성 표기다.
- **재현 기준선 갱신:** `uv.lock` SHA-256
  `2CBBBFA5BE0E257904A23F4CC220654EA6B14E5FCEEE34367563E35ECF256D40`
  (Phase 0 의 `D1BC64A8...` 에서 변경 — 사유는 F-032, R-013 에 기록).
- **게이트 결과:** 전체 suite **621 passed**(skip·xfail·deselect 0) · `-m mysql` 28 passed ·
  ruff check/format · mypy · bandit MEDIUM 이상 0 · `alembic heads` 단일(`d4e6f8b12c34`) ·
  pip-audit 취약점 0 · 문서 경로·환경변수 기계 검사 통과 ·
  인벤토리 **22 paths / 37 operations**, operation ID 37 고유, component key `__` 0
- **CI 실전 검증(2026-08-19, run `32227295666`):** 브랜치를 push 해 GitHub Actions 에서
  **처음으로 실제 실행**했다. 지금까지 CI 는 로컬 재현으로만 확인한 상태였다.
  gate job — review_gate 5그룹 통과, `pytest -m "not mysql"` 593 passed.
  mysql job — digest 로 고정한 이미지 pull → healthy, `pytest -m mysql` **28 passed / skip 0**,
  `review_gate --group tests` 로 전체 suite skip·deselect 0 통과. 두 job 모두 success.
  부수 관측: SHA 고정 때문에 Action 이 Node 20 대상 버전에 묶였다(R-014).
- **수렴 판정:** ORM/Raw delivery 범위는 **CONVERGED**. Open Fix 5건이 남아 있으나 전부
  F-016~F-020 으로, 계획서 §8 이 **독립 작업(Runtime/lifecycle)** 으로 분리한 Phase 1-R2
  트랙이다. 이 그룹의 계약(ORM/Raw 데이터 접근·예제·문서·게이트)에는 Open Fix 가 없다.

### Round 11 — 2026-08-19 (base SHA: `50cf194`) — 이월 결함 해소(연쇄)

- **트리거:** 별도 작업 그룹 `docs/crp/groups/runtime-lifecycle/` 의 Round 1 완료.
- **검수 범위:** 이 그룹의 이월 결함 F-016~F-020 상태 전환만. 코드는 그 그룹이 변경했다.
- **결과:** 5건 전부 **Closed**. 계획서 §8 이 "Runtime/lifecycle 독립 작업" 으로 분리했던
  트랙이 완료되면서, 이 그룹의 **Open Fix 가 0** 이 됐다.
- **확인:** 그 그룹의 변경은 C-1(ORM/Raw Base·예제 기능 diff 0)을 기계 검증으로 지켰고,
  라우트 인벤토리 22 paths / 37 operations 와 alembic head `d4e6f8b12c34` 도 불변이다.
  즉 이 그룹의 산출물은 그대로다.
- **수렴 판정:** `CONVERGED` — delivery 범위뿐 아니라 **이월분까지 포함해** Open Fix 0.

### Round 12 — 2026-08-20 (base SHA: `092b394`) — 재검수(문서 정합성만)

- **트리거:** 사용자 재검토 요청. 전체 게이트·수치 재측정.
- **재측정:** review_gate 6그룹 통과 · **698 passed**(skip/xfail/deselected 0) ·
  22 paths / 37 operations · alembic head `d4e6f8b12c34` · 작업 트리 clean ·
  `main` == `origin/main` == `092b394`. 전부 기록과 일치.
- **발견:** charter §3 인수 기준 2건이 **미체크로 남아 있었다** — Round 11 의 `CONVERGED`
  선언과 표면상 모순. 내용을 대조하니 둘 다 *실질은 충족*이었고 체크만 누락된 것이었다.
  - "불변식 구조 증거" 항목은 v0.1 당시 **INV-1~9** 기준 문구였는데 이후 불변식이 21개로
    늘었다. §2-3 의 각 INV 가 지목한 검사 파일 12종이 전부 실재함을 확인했다
    (INV-1 → `tests/test_router_registration.py`, INV-3 → `tests/test_read_path_no_commit.py`
    포함). 범위 문구를 INV-1~21 로 맞추고 닫았다.
  - "질의 수준 준수" 항목은 절차 자기평가다. Celery 실행 모델을 사용자 결정(REQ-009)으로
    올린 것 외에는 기본값+고지로 처리했고 각 라운드 로그에 남아 있어 닫았다.
- **왜 놓쳤나:** Round 11 직후의 잔재 정리(`0704961`)가 `checklist.md` 만 대상으로 했고
  `charter.md` §3 은 보지 않았다. 같은 그룹 안에 체크박스가 있는 파일이 둘인데 한쪽만
  닫은 것이다. 남은 두 파일 형식(`design-baseline.md` §0)의 미체크는 **질의 수준 선택지의
  비선택 항목**이라 정상이다.
- **변경:** `charter.md` 만 수정(v0.2). 코드·테스트·설정 diff 0.
- **수렴 판정:** `CONVERGED` 유지 (Open Fix 0). 이번 라운드는 신규 결함 0, 문서 정합성 정정 1.

### Round 13 — 2026-08-20 (base SHA: `8e9eaf9`) — R-014 해소(공급망 갱신)

- **트리거:** 잔여 리스크 R-014 의 승계 조건 도달. GitHub 이 Node 20 대상 Action 을
  강제 실행으로 처리 중이라, 방치하면 우리가 아니라 **외부 시계**가 CI 를 끊는다.
- **교체:** `actions/checkout` v4(`11d5960a`) → **v7.0.1**(`3d3c42e5`),
  `astral-sh/setup-uv` v5(`d4b2f3b6`) → **v10.0.1**(`20cfd1bf`). 둘 다 `using: node24`.
  SHA 고정 원칙(F-033)은 유지 — 태그로 되돌리면 `supply` 그룹이 잡는다.
- **파괴적 변경 대조:** checkout 은 major 릴리스에 breaking 항목이 없다. setup-uv 는
  major 5개를 건너뛰므로 v6~v10 의 breaking 섹션을 전부 읽고 우리 사용 형태와 대조했다 —
  캐시 기본값 변경(v6)은 `cache-dependency-glob` 을 명시해서, `server-url` 제거(v7)는
  쓰지 않아서, `prune-cache` 기본값(v9)은 캐시 크기만 바꿔서, 민감 이벤트 캐시 비활성(v10)은
  트리거가 push·pull_request·workflow_dispatch 뿐이라 해당 없음.
- **신규 결함 F-035(LOW):** 교체하며 읽은 `ci.yml` **첫 줄**이 존재하지 않는 charter
  docs/crp/groups/fastapi-standard-restructure/charter.md — 삭제된 그룹 — 를 가리키고 있었다.
- **근본 원인:** 문자열만 고치면 같은 종류가 계속 썩는다. 검사 쪽을 보니 두 구멍이었다 —
  `check_doc_paths` 의 확장자 목록에 **`.md` 가 없었고**(문서가 문서를 가리키는 참조는
  아예 검사 대상이 아니었다), `check_docs` 의 대상에 **워크플로 파일이 없었다**.
  둘 다 넓혔고, 기존 문서에서 새로 걸리는 항목은 **0건**이었다 — 공짜로 넓힌 셈이다.
- **fail-on-revert:** 참조를 되돌리자 `tests/scripts/test_review_gate.py` 2건 실패 +
  게이트 `docs` 그룹 실패. 복원 후 전부 통과.
- **게이트 결과:** review_gate 6그룹 통과 · 전체 **701 passed**(698 + 3, skip·xfail·deselect 0) ·
  라우트 22 paths / 37 operations 불변 · alembic `d4e6f8b12c34` 불변 ·
  애플리케이션 동작 코드(`app/`, `main.py`, `config.py`, `migrations/`) **diff 0**
- **관측:** 게이트 통과 직후 로컬 MySQL 컨테이너가 내려가 재측정에서 28건이 skip 됐다.
  R-010 이 기록한 함정이 실제로 재현된 것이다. 컨테이너를 되살려 재측정했고, skip 은
  조용히 통과하지 않고 사유와 함께 드러났다 — 그 설계가 의도대로 작동했다.
- **수렴 판정:** `CONVERGED` 유지 (Open Fix 0).

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
| 7 | 0 | 0 | 0 | 0 | 0 (신설 계층) | NOT CONVERGED (Open Fix 7) |
| 8 | 0 | 1 | 1 | 1 | 3 (2 Fixed / 1 이월) | NOT CONVERGED (Open Fix 8) |
| 9 | 0 | 0 | 2 | 1 | 3 (전부 같은 라운드에 Fixed) | NOT CONVERGED (Open Fix 8) |
| 10 | 0 | 1 | 3 | 0 | 4 (전부 같은 라운드에 Fixed) | CONVERGED (delivery 범위 Open Fix 0 / 이월 5는 Phase 1-R2 트랙) |
| 11 | 0 | 0 | 0 | 0 | 0 (이월 5건 Closed) | **CONVERGED** (Open Fix 0 — 이월분 포함) |
| 12 | 0 | 0 | 0 | 0 | 0 (문서 정합성 정정 1) | **CONVERGED** (Open Fix 0) |
| 13 | 0 | 0 | 0 | 1 | 1 (같은 라운드에 Fixed) | **CONVERGED** (Open Fix 0) |
