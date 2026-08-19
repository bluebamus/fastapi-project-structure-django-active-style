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

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 3 | 1 | 7 | NOT CONVERGED |
| 1 | 0 | 1 | 2 | 0 | 3 (전부 같은 라운드에 Fixed) | NOT CONVERGED (Open Fix 5 → Phase 2~9) |
| 2 | 0 | 0 | 0 | 0 | 0 (F-003 해소) | NOT CONVERGED (Open Fix 4 → Phase 3·5·9) |
| 3 | 0 | 1 | 6 | 3 | 10 (5 Fixed / 5 이월) | NOT CONVERGED (Open Fix 9) |
