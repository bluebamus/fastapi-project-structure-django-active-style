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

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 3 | 3 | 1 | 7 | NOT CONVERGED |
| 1 | 0 | 1 | 2 | 0 | 3 (전부 같은 라운드에 Fixed) | NOT CONVERGED (Open Fix 5 → Phase 2~9) |
