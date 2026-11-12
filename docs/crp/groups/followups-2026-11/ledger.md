# Ledger — followups-2026-11 (결함 원장)

| ID | Severity | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001 (MySQL 자동 검증 0건) | Fix | Fixed (CI 확인 대기) | `test/mysql-ci` 병합 | 7건, 실행은 CI |
| F-002 | LOW | REQ-002 (기능 테스트 픽스처 10곳 복사) | Fix | Fixed | `refactor/feature-client-fixture` 병합 | 수집 ID 1272 동일 |
| F-003 | LOW | 엔진 안전 옵션 가드가 `app/features/conftest.py` 의 테스트 엔진을 운영 생성 지점으로 셈 | Fix | Fixed | 같은 병합 | conftest.py 제외, 가드 2건 통과 |
