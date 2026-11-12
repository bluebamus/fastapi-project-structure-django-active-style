# Residual Risk — followups-2026-11

| ID | 항목 | Severity | 왜 비범위인가 | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-001 | `tests/mysql` 은 로컬에서 한 번도 돌지 않았다 — 첫 CI 실행에서 실패할 수 있다 | MED | 이 PC 에서 MySQL 접속 금지(C-1) | 2026-11-12 | CI `mysql` 잡이 실패하면 ledger 로 |
| R-002 | 서비스 이미지가 태그(`mysql:8.4`)로만 고정 | LOW | 이 PC 에서 digest 를 얻을 수 없음 | 2026-11-12 | digest 를 확인할 수 있게 되면 |
| R-003 | 복제 지연·replica 장애 전환은 실제 MySQL 로 검증하지 않음 | LOW | 서버 하나(비목표) | 2026-11-12 | 복제 구성 CI 가 생기면 |
| R-004 | `CONVERT_TZ` 는 쿼리당 오프셋 하나 — DST 시간대에서 전환일 행이 어긋남 | LOW | 기존 코드의 `ponytail:` 표기 그대로, 기본 TIME_ZONE 은 DST 없음 | 2026-11-12 | DST 있는 TIME_ZONE 을 지원하면 |
