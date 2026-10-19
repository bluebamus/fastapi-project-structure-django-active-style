# Residual Risk — config-cleanup (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-801 | `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 은 여전히 읽는 코드가 없다(계약 테스트의 `UNUSED_FIELD_EXCEPTIONS`). | LOW | REQ-001 은 세 묶음만 정했다. 기존 문서가 이미 "선언만" 으로 안내한다. | 2026-10-19 | 사용자가 정리를 정하면 지우고 예외 목록에서 뺀다(낡은 예외는 테스트가 잡는다). **→ 해소(2026-10-19, REQ-002 Round 2):** `API_VERSION` 삭제(F-004), 로그 4필드 연결(F-005), 예외 목록 삭제. |
| R-802 | 계약 테스트는 이름 등장만 본다 — `config.py` 의 validator 만 읽는 필드도 "읽힘" 으로 센다. | LOW | ADR-003. 프로퍼티 경유 사용을 놓치지 않으려면 `config.py` 를 포함해야 한다. 현재 validator 만 읽는 필드는 없다. | 2026-10-19 | validator 전용 필드가 생기면 검사를 AST 기반(검증 함수 제외)으로 바꾼다. |
| R-803 | `LOG_CONSOLE_FORMAT`·`LOG_DATE_FORMAT` 은 `uvicorn main:app` CLI 와 Celery 워커가 **스스로 세운** 콘솔 핸들러의 형식에는 적용되지 않는다(각자의 기본 형식). `LOG_CONSOLE_ENABLED` 는 적용된다. | LOW | 명세 §2 "기본 출력 불변" — 두 경로의 현재 기본 출력은 uvicorn·Celery 형식이다. 바꾸면 기본 출력이 바뀐다. | 2026-10-19 | 워커·CLI 출력도 앱 형식으로 통일하기로 정하면 `adopt_external_handlers()` 에서 `TzFormatter` 를 단다(Celery 는 `worker_hijack_root_logger` 검토). |
| R-804 | `setup_uvicorn_logging()` 의 access 포매터가 `{client_addr}`·`{request_line}`·`{status_code}` 를 쓰지만 `TzFormatter` 는 이 필드를 만들지 않는다(uvicorn `AccessFormatter` 가 하는 일). `python main.py` 로 띄우면 접속 줄마다 logging 오류가 난다. **이번 변경 전부터 있음**(fmt 미변경, 재현: `uvicorn.access` 에 uvicorn 과 같은 args 로 info). | LOW | REQ-002 범위 밖(형식 연결만). `uvicorn main:app` CLI 경로는 uvicorn 자체 포매터라 영향 없다. | 2026-10-19 | 감독자 결정 — access 포매터를 `uvicorn.logging.AccessFormatter` 기반으로 바꾸거나 `TzFormatter` 에서 args 를 풀어 필드를 채운다. |
