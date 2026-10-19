# Ledger — logging-overhaul (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> 분류: **Fix** / **Accept-out-of-scope** / **Wont-fix**. 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 L1 (config-cleanup R-803) | INV-1 | Fix | **Fixed** | Round 1 | `uvicorn main:app`·Celery 워커는 각자 기본 형식, `python main.py` 접속 줄은 전용 형식이었다. **조치:** 모든 경로가 root 핸들러 한 벌(ADR-004). |
| F-002 | LOW | REQ-001 L2 | INV-2 | Fix | **Fixed** | Round 1 | 설치된 라이브러리 줄은 모두 `app=ext` — Celery·uvicorn·SQLAlchemy 줄을 헤더로 구분할 수 없었다. **조치:** `_app_from_path(pathname, name)` 의 로거 이름 표. |
| F-003 | LOW | REQ-001 L3 | INV-3 | Fix | **Fixed** | Round 1 | 형식에서 `{funcName}` 등을 빼도 통과했다. **조치:** validator 에 필수 자리표시자 검사. |
| F-004 | LOW | REQ-001 L4 | INV-4 | Fix | **Fixed** | Round 1 | 레벨이 root 하나뿐이었다. **조치:** `LOG_APP_LEVELS` + `AppLevelFilter`(ADR-005). |
| F-005 | MED | REQ-001 L5 조사 | INV-5 | Fix | **Fixed** | Round 1 | Celery 워커는 `worker_hijack_root_logger` 로 root 핸들러를 비워 우리 queue 핸들러가 사라졌다 — staging/production 워커는 `--logfile` 없이는 파일 로그가 하나도 없었다. **조치:** 수신자가 root 를 다시 구성(`celery.log`·`celery-error.log`). |
| F-006 | MED | REQ-001 L6 조사 | INV-6 | Fix | **Fixed** | Round 1 | 파일 이름의 `{date}` 가 기동 시각에 한 번 정해져, 오래 떠 있는 프로세스는 며칠치를 한 날짜 이름에 썼다(크기 회전만). **조치:** `DailyRotatingFileHandler`(ADR-002·003). |
| F-007 | HIGH | REQ-001 L7 조사 | INV-7 | Fix | **Fixed** | Round 1 | DSN 정규식이 사용자명을 1자 이상으로 요구해 `redis://:비밀번호@host` 꼴(이 저장소 `REDIS_URL` 의 모양)의 **비밀번호를 그대로** 남겼다(base `ede6e1c` 에서 재현). 사용자명도 남겼다. **조치:** 사용자명 0자 허용, 둘 다 `***`, 설정 비밀값 원문 마스킹(ADR-006). |
| F-008 | MED | REQ-001 L5 조사 | INV-8 | Fix | **Fixed** | Round 1 | prefork 자식은 listener 스레드가 없어 파일 레코드가 큐에 갇힌다(F-005 를 고치면 드러나는 잠재 결함). **조치:** `worker_process_init` 에서 재시작(ADR-007). |
| F-009 | LOW | Round 1 실기동 스모크 | INV-8 | Fix | **Fixed** | Round 1 | solo 풀도 `worker_process_init` 을 같은 프로세스에서 보내 F-008 조치가 둘째 listener 를 세웠다. **조치:** 시작 pid 가드(ADR-007), 테스트 `test_listener_is_not_restarted_in_the_same_process`. |
