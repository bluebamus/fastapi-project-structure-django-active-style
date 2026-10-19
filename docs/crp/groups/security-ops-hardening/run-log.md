# Run Log — security-ops-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `a1625fe`) — 계획·조사
- **트리거:** 사용자 요청 REQ-001(보안 결함, 접속 로그 보존 1년·`.env` 설정, 토큰 15분 유지, 관리 로그인 CSRF, 관리 목록 날짜 필터).
- **검수 범위:** `app/core/db/session.py`·`migrations/env.py`(엔진 생성), home 접속 로그 기능·`app/celery/app.py`, `app/features/auth/admin_auth.py`·`app/features/admin.py`·로그인 템플릿, 기능별 `admin.py`, sqladmin 0.32 소스(`application.py` 로그인 경로, `templating.py`, `filters.py`, `models.py` 필터 적용부), celery 의 beat 모듈(`Beat.init_loader`).
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **조사:** 엔진 생성 지점은 session.py 3곳(writer·`_create_read_engine`·background)과 Alembic `engine_from_config` 1곳, 모두 `hide_parameters` 없음 — SQLite 고유 제약 위반의 예외 문자열에 이메일·해시가 그대로 보였다. Celery·스크립트 전용 엔진은 없다(F-006). sqladmin GET `/admin/login` 은 컨텍스트 없이 템플릿을 그린다 → 템플릿 전역 함수로 토큰을 싣는다. 연산 필터는 `{param}_op` 가 있을 때만 `get_filtered_query(query, operation, value, model)` 를 부른다. beat 는 시작 시 `loader.init_worker()` 로 include 를 import 한다 → 기능 `tasks.py` 의 스케줄 등록이 보인다.
- **신규 finding:** CRIT 0 · HIGH 1 · MED 2 · LOW 1 (F-001~F-004) · 수용 1(F-005) · 해당 없음 1(F-006)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 4)

### Round 1 — 2026-10-19 — REQ-001 구현 (브랜치 `feat/security-ops`)
- **Fix:** F-001(`282ba25`) · F-002(`771d061`) · F-003·F-004(`65a335f` — 로그인 테스트 파일을 함께 바꿔야 해 한 커밋) → **Fixed**. F-005 → ADR-005 로 수용.
- **설계:** ADR-001(정본 `ENGINE_SAFETY_OPTIONS`), ADR-002(보존 서비스·두 단계 DELETE·배치 커밋·기능이 beat 등록), ADR-003(synchronizer token, 레이트 리밋 전 bytes `compare_digest`), ADR-004(`LocalDateFilter`), ADR-005(15분·권한 회수 지연 유지).
- **동작이 바뀐 기존 테스트:** `tests/test_admin_login.py` 의 `_login` 이 로그인 화면에서 토큰을 꺼내 함께 보낸다(새 `csrf_token` 헬퍼 — MySQL 로그인 테스트도 import). `test_failed_login_is_400_with_one_indistinguishable_message` 의 "실패 응답에 세션 쿠키 없음" 단언은 "로그인 상태가 아님(`/admin/` 302)" 으로 바꿨다 — 세션이 이제 CSRF 토큰을 담으므로 실패 응답에도 쿠키가 실린다(사용자 id 는 없다). `test_login_replaces_any_existing_session_content` 는 세션·본문에 같은 토큰을 넣는다. `_filter_params` 는 날짜 필터에 연산 3종 + 잘못된 입력 1건을 넣고, 대조군 수는 14 → 42(= 14 + 7 뷰 × 4). 그 밖의 기존 테스트는 바꾸지 않았다.
- **DB 접속 없음:** 새 테스트는 in-memory/파일 SQLite·fakeredis·mock 만 쓰고 lifespan 을 돌리지 않는다. 엔진 계약 테스트는 MySQL URL 엔진 객체의 속성만 본다(연결 없음).

### fail-on-revert (Round 1)
대상 파일을 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\active\security-ops\`)에 복사해 두고 결함을 되살린 내용을 넣어 돌린 뒤 복사본으로 복원했다.

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| session.py·env.py 를 main 으로(옵션 상수만 `{}` 로 남김) | `tests/core/test_hide_parameters.py` | 6 failed / 1 passed(대조군) — 예외 문자열·로그 파이프라인에 값 노출, 엔진 3개 `hide_parameters` False, 생성 지점 4곳 미펼침 |
| 리포지토리 `<` → `<=` | `test_access_log_retention.py` | 1 failed(`test_only_rows_older_than_the_cutoff_are_deleted`) |
| 배치별 `commit()` 제거 | 〃 | 1 failed(`test_deletes_in_batches_and_commits_each_batch`) |
| 보존 0 단락 제거 | 〃 | 1 failed(`test_zero_retention_deletes_nothing`) |
| 설정 `ge=0` 제거 | 〃 | 1 failed(`test_negative_retention_is_rejected_by_service_and_settings`) |
| beat 등록 제거 | 〃 | 1 failed(`test_purge_task_is_scheduled_daily_at_0330_local_time`) |
| provider 가 설정 대신 365 고정 | 〃 | 1 failed(`test_provider_uses_the_configured_retention`) |
| 태스크가 provider 대신 직접 생성 | 〃 | 1 failed(`test_purge_task_builds_its_service_through_the_home_provider`) |
| admin_auth.py·admin.py·login.html 을 main 으로 | `tests/test_admin_login.py -k "csrf or token or 403"` | 10 failed / 10 |
| 기능 `admin.py` 7개를 main 으로(날짜 필터 없음) | `tests/test_admin_login.py -k "filter or date"` | 3 failed(뷰 계약·실제 목록 좁힘·대조군 수) |
| `on` 상한 `<` → `<=` | `tests/core/test_admin_filters.py` | 1 failed |
| `before` `<` → `<=` | 〃 | 1 failed |
| 시작 경계를 UTC 자정으로 | 〃 | 6 failed |
| 끝 경계를 시작 + 24시간으로(DST 무시) | 〃 | 1 failed(DST) |
| 날짜 형식 정규식 제거 | 〃 | 1 failed(잘못된 입력 `20261019`·`2026-10-19T00:00`) |
| 모르는 연산 무시 제거 | 〃 | 1 failed(`equals`) |
| 기본 시간대를 UTC 로 | 〃 | 1 failed(`test_default_timezone_is_the_business_time_zone`) |

### 실제 기동 스모크 (저장소 밖 임시 경로, 환경 변수만 — `.env` 없음)
- uvicorn 소켓 서버에 `create_admin_interface`(운영 조립) + 파일 SQLite(`ENGINE_SAFETY_OPTIONS`) + fakeredis: 로그인 화면 hidden `csrf_token` 200, 토큰 없음 403, 틀린 토큰 403, 올바른 토큰 302, 7개 뷰 × 날짜 연산 3종 + 잘못된 입력 모두 200 — 32/32 PASS.
- beat 기동 경로: 새 프로세스에서 `celery.apps.beat.Beat(app=celery_app).init_loader()` 전 `beat_schedule={}` → 후 `home.purge_expired_access_logs`(`crontab 30 3 * * *`, timezone `Asia/Seoul`).

### 검사 수치 (최종)
- `pytest -m "not mysql"`: **1231 passed / 44 deselected / skip 0**(1190 → +41: hide_parameters 7, 보존 9, 날짜 필터 13, 관리 로그인 CSRF 10·날짜 필터 2) — 저장소 안, 그리고 `.env` 없는 저장소 밖 사본(`git archive` + 작업 트리 변경분, `uv sync --frozen`) 양쪽 같은 결과. 경고 1건은 기존 `httpx`/`starlette.testclient` 폐기 예고(pyproject 주석에 기록된 것). `-m mysql --collect-only`: 44 수집(43 → +1 `test_batched_purge_respects_cutoff_on_mysql`). MySQL 실행은 CI 몫.
- ruff check·format 클린. mypy(순수 Python 빌드 1.20.2, `--python-executable` .venv) 205 files 0 issues.
- `scripts/review_gate.py`: structure·supply·docs 통과(static 은 같은 도구를 개별 실행, deps 는 네트워크 단계라 생략). alembic heads `a7c3e9f1b2d4` 단일 — 리비전 추가 없음.
- **수렴 판정:** `CONVERGED` — Open Fix 0.
- **잔여 위험 변화:** R-601~R-606 등록. admin-login R-302 부분 해소·R-310 해소, log-redaction-fixes R-401(보존 도입)·R-402(바인드 값 해소), service-hardening R-204(리뷰 R-05 해소)·R-201·R-211(사용자 결정으로 수용).
