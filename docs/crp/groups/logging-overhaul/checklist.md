# Checklist — logging-overhaul (개선 항목 추적판)

> 각 항목은 한 줄이며, 그 줄이 닫히기(`[x]`) 전엔 "완료"가 아니다. ledger 의 Fix 항목과 1:1 로 연결한다.

## Round 0 — 2026-10-19 (계획·조사)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] 현재 흐름 조사 — `app/utils/logs/*`, `main.py`(`setup_uvicorn_logging`), uvicorn CLI(`LOGGING_CONFIG` → `adopt_external_handlers`), Celery 수신자(`after_setup_logger`·`after_setup_task_logger`, `worker_hijack_root_logger`), `config.LogSettings` (run-log Round 0)
- [x] Celery `setup_logging_subsystem`·stdlib `TimedRotatingFileHandler`·`QueueListener`(3.14) 소스 확인

## Round 1 — 2026-10-19 REQ-001 — 완료 (브랜치 `feat/logging-overhaul`)
- [x] (F-002) L2 헤더 — `_app_from_path(pathname, name)` 로거 이름 표
- [x] (F-003) L3 필수 필드 검사
- [x] (F-007) L7 DSN 사용자명·`redis://:pw@`, `LOG_SECRET_SETTINGS`·`set_secret_values`, 짧은 값 규칙, 계약 테스트
- [x] (F-004) L4 `LOG_APP_LEVELS`·`AppLevelFilter`·root 최솟값·모르는 헤더 경고
- [x] (F-006) L6 `DailyRotatingFileHandler`·`LOG_RETENTION_DAYS`, `LOG_BACKUP_COUNT`·`LOG_*_FILENAME` 삭제(남은 키 무시 테스트에 추가)
- [x] (F-005) L5 프로세스별 파일·Celery 수신자의 root 재구성·`--logfile` 유지
- [x] (F-001) L1 모든 경로 같은 형식 — `log_config=None`, 외부 핸들러 걷기, `setup_uvicorn_logging`·`TzAccessFormatter`·`redact_handlers` 삭제, 기존 "기본 출력 불변" 테스트를 "같은 형식" 으로 교체
- [x] (F-008) prefork 자식 listener 재시작, (F-009) 같은 프로세스 가드
- [x] uvicorn spawn 워커 + 파일 로그 WARNING
- [x] fail-on-revert(run-log)
- [x] L8 문서 — README 로깅 절, ARCHITECTURE §3·§4.2·§5·§14, DEVELOPMENT §8.1, server-lifecycle 부록, `.env.example`, 이전 그룹 residual-risk 상태 덧붙임(config-cleanup R-803·R-804, log-redaction-fixes R-404, runtime-lifecycle R-104), `docs/review` 두 문서(커밋하지 않음)
- [x] L9 검사 — ruff·format·mypy, `pytest -m "not mysql"` skip 0(저장소 안 + `.env` 없는 저장소 밖 클론), `-m mysql --collect-only`, review_gate static·structure·docs, 실기동 스모크
