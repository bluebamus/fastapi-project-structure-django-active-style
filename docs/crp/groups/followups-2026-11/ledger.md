# Ledger — followups-2026-11 (결함 원장)

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 (MySQL 자동 검증 0건) | Fix | Fixed | `test/mysql-ci` 병합 + `7bef2e2` | CI 7건 통과(2회차) |
| F-002 | LOW | REQ-002 (기능 테스트 픽스처 10곳 복사) | Fix | Fixed | `refactor/feature-client-fixture` 병합 | 수집 ID 1272 동일 |
| F-003 | LOW | 엔진 안전 옵션 가드가 `app/features/conftest.py` 의 테스트 엔진을 운영 생성 지점으로 셈 | Fix | Fixed | 같은 병합 | conftest.py 제외, 가드 2건 통과 |
| F-004 | MED | REQ-001 — CI 첫 실행에서 계정 생성 헬퍼가 `ValueError: unsupported format character` 로 2건 실패(`exec_driver_sql` 이 pymysql `%` 치환을 거쳐 `'@'%'` 가 서식 문자가 됨) | Fix | Fixed | `7bef2e2` | 테스트 코드 결함, 운영 코드 무관 |
