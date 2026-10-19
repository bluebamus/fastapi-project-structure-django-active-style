# Charter — logging-overhaul  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)과 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 로깅 | `app/utils/logs/config.py`·`filters.py`·`formatters.py`·`handlers.py`(신규)·`queue_logging.py`·`setup.py`·`__init__.py` | 소스 | 경로 통일, 헤더 표, 앱별 레벨 필터, 프로세스별 파일, 날짜+크기 회전·보관, 비밀값 원문 마스킹 |
| 진입점 | `main.py`, `app/celery/worker_lifecycle.py` | 소스 | `log_config=None`, Celery 수신자가 프로세스 종류·root 재구성, prefork listener 재시작 |
| 설정 | `config.py`, `.env.example` | 소스·설정 | `LOG_APP_LEVELS`·`LOG_RETENTION_DAYS` 추가, `LOG_BACKUP_COUNT`·`LOG_APP_FILENAME`·`LOG_ERROR_FILENAME` 삭제, 필수 필드 검사, `LOG_SECRET_SETTINGS`·`log_secret_values()` |
| 테스트 | `tests/utils/test_logging_overhaul.py`(신규), `test_logs.py`·`test_log_redaction.py`·`test_log_settings_wiring.py`·`test_queue_logging.py`, `tests/core/test_settings_contract.py` | 테스트 | "CLI·Celery 기본 출력 불변" 테스트를 "모든 경로 같은 형식" 으로 교체 |
| 문서 | `README.md`(로깅 절 신설), `docs/guides/ARCHITECTURE.md`(§3·§4.2·§5·§14), `docs/guides/DEVELOPMENT.md`(§8.1), `docs/guides/server-lifecycle-guide.html` | 문서 | |

- 기준선: base `ede6e1c`(main) · alembic 변경 없음 · 새 의존성 없음.

## 2. 계약 (Contract)

### 2-1. 불변식 (Invariants)
- INV-1: 앱 로거·`python main.py`·`uvicorn main:app`·Celery 워커(메인·`celery.task`)의 모든 줄은 root 의 핸들러 한 벌(같은
  `TzFormatter`·필터)로 한 번씩 찍힌다. 경로별 형식 분기는 없다. (`test_web_paths_share_one_format_on_console_and_file`·
  `test_celery_worker_and_task_lines_share_the_format`·`test_python_main_passes_no_uvicorn_log_config`)
- INV-2: 헤더 판별은 `filters._app_from_path(pathname, name)` 한 함수다 — 우리 코드는 경로, 라이브러리는 로거 이름 표.
  (`test_external_code_is_labeled_by_logger_name`·`test_our_code_keeps_path_rules_regardless_of_logger_name`)
- INV-3: `LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT` 에 필수 자리표시자 7개가 없으면 설정 오류(빠진 목록 포함).
  (`test_format_missing_a_required_field_is_a_settings_error`·`test_error_lists_every_missing_field`)
- INV-4: `LOG_APP_LEVELS` 는 헤더별 최소 레벨이고 필터 하나(`AppLevelFilter`, ContextFilter 바로 뒤, 모든 핸들러)로 적용된다.
  root 레벨은 최솟값. 잘못된 형식·레벨은 설정 오류, 모르는 헤더는 경고. dictConfig 에 `loggers` 키는 없다.
  (`test_app_levels_*`·`test_root_level_is_lowered_*`·`test_unknown_app_level_header_only_warns`·`test_dictconfig_has_no_per_app_loggers`)
- INV-5: 파일은 프로세스 종류별(`LOG_FILES`) — 웹 `app.log`·`error.log`, Celery `celery.log`·`celery-error.log`. 종류는 Celery 수신자가
  정한다(웹은 기본값). (`test_file_names_follow_the_process_kind`·`test_celery_worker_and_task_lines_share_the_format`)
- INV-6: `DailyRotatingFileHandler` — UTC 자정 교체(`app.log.YYYY-MM-DD`), 하루 안 크기 초과 분할(`.1`, `.2`…), 교체 시점에
  `LOG_RETENTION_DAYS` 보다 오래된 날짜·분할 파일 삭제(정확히 N일 전은 남음, `0` 은 삭제 안 함, 음수는 설정 오류). (`test_midnight_*`·
  `test_size_overflow_*`·`test_retention_*`·`test_negative_retention_is_a_settings_error`)
- INV-7: DSN 의 사용자명·비밀번호가 모두 가려지고, `config.LOG_SECRET_SETTINGS` 의 값 원문이 메시지·인자·traceback·stack 어디서든 가려진다.
  4글자 미만 값은 DSN·`user=`·`username=` 에서만. 비밀 이름 규칙(`*_USER`·`*_PASSWORD`·`*SECRET*`·`*_KEY`) 설정은 목록에 있어야 한다.
  (`test_dsn_masks_both_user_and_password`·`test_configured_secret_values_*`·`test_short_secret_*`·`test_secret_inside_exception_chain_is_masked`·
  `test_every_secret_like_setting_is_in_the_log_secret_list`·경로 테스트 2건의 원문 0건 단언)
- INV-8: prefork 자식은 파일 listener 를 다시 세운다. 같은 프로세스(solo 풀)면 세우지 않는다.
  (`test_listener_is_restarted_after_fork`·`test_listener_is_not_restarted_in_the_same_process`·`test_worker_process_init_restarts_the_listener`)

### 2-2. 비목표
- 다중 프로세스가 같은 파일을 안전하게 회전시키는 장치(파일 잠금·중앙 수집 프로세스). 문서·WARNING 으로 대신한다(R-901).
- 구조화(JSON) 로그, 외부 수집기 연동.
- uvicorn CLI `--log-level` 의 무력화(R-904).

## 3. 인수 기준 (Acceptance Criteria)

- [x] `pytest -m "not mysql"` 전량 통과, skip 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 모두 (run-log Round 1)
- [x] `-m mysql --collect-only` 수집 오류 0
- [x] `ruff check .` · `ruff format --check .` · `mypy .` 클린
- [x] INV-1~INV-8 각각 실행 테스트 1개 이상, 핵심 변경의 fail-on-revert(run-log)
- [x] 실기동 스모크 — `uvicorn main:app`·`python main.py`·`celery worker --pool=solo` + 태스크 1건, 출력·파일 형식 동일, 비밀값 원문 0건
- [x] alembic 변경 없음

## 4. 버전
- v0.1 (2026-10-19): 최초 — REQ-001(L1~L9).
