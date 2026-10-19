# Run Log — logging-overhaul (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지.

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `ede6e1c`) — 계획·조사
- **트리거:** 사용자 결정(포맷 C·날짜+크기+보관 일수·DSN id/비밀번호와 `.env` 비밀값 원문·프로세스별+에러 파일) + 감독자 명세 L1~L9.
- **현재 흐름(조사 결과):**
  - 설정: `build_dictconfig()` 가 root 에 콘솔(`TzFormatter`, `LOG_CONSOLE_FORMAT`) + staging/production 이면 queue → `RotatingFileHandler`
    2개(`{date}_app.log`·`{date}_error.log`, `{date}` 는 **구성 시각**에 한 번). 레벨은 root 하나, 필터는 context·redact·sql_noise.
  - `python main.py`: `uvicorn.run(log_config=setup_uvicorn_logging())` — uvicorn 로거 3개에 자기 콘솔 핸들러(propagate=False),
    접속 줄은 `TzAccessFormatter` 전용 형식. uvicorn 줄은 root 의 파일 핸들러에 가지 않았다.
  - `uvicorn main:app`: CLI 가 `LOGGING_CONFIG` 로 uvicorn 기본 핸들러를 먼저 붙이고, 앱 import 의 `configure_logging()` 이
    `adopt_external_handlers()` 로 마스킹 필터만 달았다 — 형식은 uvicorn 기본(R-803).
  - Celery: `worker_hijack_root_logger` 가 root 핸들러를 비우고 자기 핸들러를 단다 → 우리 queue 핸들러가 사라져 **워커 파일 로그 없음**
    (F-005). `on_setup_logger` 는 마스킹 필터만 달았다 — 형식은 Celery 기본, `celery.task` 는 TaskFormatter.
  - 헤더: `_app_from_path(pathname)` — 설치된 라이브러리는 모두 `ext`.
  - 마스킹: DSN 정규식이 사용자명 1자 이상을 요구 → `redis://:pw@host` 의 비밀번호가 그대로 남음(base 에서 재현, F-007). 사용자명은 남김.
  - 재사용한 것: `TzFormatter`·`ContextFilter`·`RedactingFilter`(+`redact()` 정본)·`SQLNoiseFilter`·bounded queue/listener·`console_enabled()`·
    필수 필드 검사를 얹은 기존 형식 validator·"남은 키 무시" 계약 테스트·`_isolated_loggers`/`_capture` 테스트 헬퍼.
- **신규 finding:** HIGH 1(F-007), MED 4(F-001·F-005·F-006·F-008), LOW 3(F-002~F-004). 스모크에서 LOW 1(F-009) 추가.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 8)

### Round 1 — 2026-10-19 — REQ-001 구현 (브랜치 `feat/logging-overhaul`)
- **Fix:** F-001~F-009 → **Fixed**. ADR-001~ADR-008.
- **동작이 바뀐 기존 테스트(의도된 변경):**
  - `test_log_settings_wiring.py` — `test_uvicorn_log_config_follows_console_and_date_format` → `test_uvicorn_lines_follow_console_and_date_format`
    (접속 줄도 같은 형식), `test_console_disabled_drops_uvicorn_log_config_handlers` 삭제(함수 삭제), `test_celery_worker_console_handler_follows_setting`
    → `test_celery_task_logger_handlers_go_to_root`, 파일 이름 `app.log`, 사용자 형식 수용 테스트에 필수 필드.
  - `test_log_redaction.py` — uvicorn·Celery 경로 테스트가 root 핸들러에서 마스킹을 확인하도록, 접속 줄 기대값(`200 OK` → 프로젝트 형식의 `… 200`),
    DSN 인자 기대값(`mysql://***:***@h/db`).
  - `test_logs.py` — `test_uvicorn_config_isolates_three_loggers` 삭제(→ `test_web_paths_share_one_format_on_console_and_file`), 파일 핸들러 단언.
  - `test_queue_logging.py` — `test_uvicorn_log_config_does_not_replace_root_handlers` 삭제(→ `test_python_main_passes_no_uvicorn_log_config`).
  - `tests/core/test_settings_contract.py` — 남은 키 무시 목록에 `LOG_BACKUP_COUNT`·`LOG_APP_FILENAME`·`LOG_ERROR_FILENAME`.
- **새 테스트:** `tests/utils/test_logging_overhaul.py` 36개 함수·63건(매개변수 포함). 구현 전 실행에서 모두 실패(RED)를 확인한 뒤 구현했다.
- **디버깅:** `_access_line(cli=True)` 가 빈 줄 — 테스트가 `uvicorn.access` 만 걷고 부모 `uvicorn`(propagate=False)을 남겼다. 실제
  `configure_logging()` 은 세 로거를 모두 걷는다(경로 테스트가 증명) → 테스트를 실제 동작에 맞춤.
- **DB·Redis 접속 없음**(테스트). 스모크는 fakeredis TCP(127.0.0.1:16480)와 비어 있는 MySQL 포트(16499).

### fail-on-revert (Round 1)
대상 파일을 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\active\logging-overhaul\revert_backup\`)에 복사해 두고, 되돌린 내용을
넣어 돌린 뒤 복사본으로 복원했다(바이트 비교 동일, 복원 후 63 passed).

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| 로깅 코드 9파일을 base(`ede6e1c`)로 | `test_logging_overhaul.py` 전체 | 50 failed, 8 errors (5 passed — 새 핸들러 파일 단독 테스트) |
| DSN 치환을 `\1\2:***@`(사용자명 유지)로 | `test_dsn_masks_both_user_and_password` | 2 failed |
| `SHORT_SECRET_MIN_LENGTH = 0`(모든 값 원문 일치) | `test_short_secret_masked_only_in_user_forms` | 1 failed |
| `configure_logging()` 의 `set_secret_values` 호출 제거 | `test_configure_logging_installs_secret_values`·`test_web_paths_…` | 2 failed |
| `AppLevelFilter.filter` 가 항상 True | `test_app_level_filter_…`·`test_app_levels_end_to_end` | 2 failed |
| `_delete_expired` 즉시 return | `test_retention_keeps_exactly_n_days_…` | 1 failed |
| `adopt_external_handlers` 가 핸들러를 남김 | `test_web_paths_share_one_format_on_console_and_file` | 1 failed |
| Celery 수신자가 root 를 다시 구성하지 않음 | `test_celery_worker_and_task_lines_share_the_format` | 1 failed |
| listener pid 가드 제거 | `test_listener_is_not_restarted_in_the_same_process` | 1 failed |

### 실기동 스모크 (Round 1)
저장소 밖 `…\tmp\active\logging-overhaul\smoke\`, `.env` 없이 환경 변수만(ENV=production, DEBUG=false, 파일 켬, 비밀값은 감시용 문자열).
`uvicorn main:app` · `python main.py` 에 요청 4개(`/health`, 비밀번호가 든 쿼리, `/ready`(DB 없음 → 503), JWT 키가 든 404),
`celery -A app.celery.app worker --pool=solo --without-mingle --without-gossip --without-heartbeat --logfile=…` + `aggregate_access_stats.delay()` 1건.

| 출력 | 로그 줄 | 형식 위반 | 비밀값 원문 | 헤더 |
|---|---|---|---|---|
| `uvicorn main:app` 콘솔 | 21 | 0 | 0 | core·app·uvicorn |
| `python main.py` 콘솔 | 27 | 0 | 0 | core·app·uvicorn |
| `logs/app.log` | 50 | 0 | 0 | core·app·uvicorn |
| Celery 콘솔 | 6 | 0 | 0 | core·celery |
| `logs/celery.log` · `--logfile` | 5 · 5 | 0 | 0 | celery |
| `logs/celery-error.log` | 1(+traceback) | 0 | 0 | celery |

- 스모크에서 F-009(solo 풀의 `worker_process_init`) 를 찾아 고쳤다. fakeredis 에 Lua 가 없어 mingle·gossip·heartbeat 를 껐다(R-906).
- 워커 import 시점 줄 1개가 `app.log` 로 갔다(R-902).

### 검사 (Round 1 최종)
- `ruff check .` 통과 · `ruff format --check .` 350 files · `mypy .` 207 source files 이슈 0
- `pytest -m "not mysql"` 저장소 안: **1400 passed, 44 deselected, skip 0** / `.env` 없는 저장소 밖 클론: **1400 passed, 44 deselected, skip 0**(커밋 `5c6bbe9` 클론, `uv sync --locked`)
- `pytest -m mysql --collect-only`: 44 수집, 오류 0
- `scripts/review_gate.py --group static structure docs`: 통과. supply·deps(네트워크)·tests(MySQL 필요)는 생략.
- alembic 변경 없음.
- **수렴 판정:** `CONVERGED` (Open Fix 0, 잔여 위험 R-901~R-907 등록)
