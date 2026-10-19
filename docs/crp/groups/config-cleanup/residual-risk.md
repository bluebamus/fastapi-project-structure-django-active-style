# Residual Risk — config-cleanup (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용"으로 박제된 항목은 의도적으로 고치지 않기로 결정된 것이다.
> 고쳐야 하면 새 결함이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-801 | `API_VERSION`·`LOG_CONSOLE_ENABLED`·`LOG_CONSOLE_FORMAT`·`LOG_FILE_FORMAT`·`LOG_DATE_FORMAT` 은 여전히 읽는 코드가 없다(계약 테스트의 `UNUSED_FIELD_EXCEPTIONS`). | LOW | REQ-001 은 세 묶음만 정했다. 기존 문서가 이미 "선언만" 으로 안내한다. | 2026-10-19 | 사용자가 정리를 정하면 지우고 예외 목록에서 뺀다(낡은 예외는 테스트가 잡는다). |
| R-802 | 계약 테스트는 이름 등장만 본다 — `config.py` 의 validator 만 읽는 필드도 "읽힘" 으로 센다. | LOW | ADR-003. 프로퍼티 경유 사용을 놓치지 않으려면 `config.py` 를 포함해야 한다. 현재 validator 만 읽는 필드는 없다. | 2026-10-19 | validator 전용 필드가 생기면 검사를 AST 기반(검증 함수 제외)으로 바꾼다. |
