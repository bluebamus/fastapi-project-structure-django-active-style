# Checklist — docs-guide-review

## Round 0 — 2026-10-21 (계획)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] 지적 34건·재검수 결과·누락 표 확인, 지적마다 코드 근거를 다시 열어 확인(틀린 지적 0)

## Round 1 — 2026-10-21 (수정) — 완료
- [x] ARCHITECTURE·DEVELOPMENT (A-01~A-14·D-01~D-03) — `0dd3db2`
- [x] HTML 안내서 3종 (S-01~S-03·S-05·S-06·H-01~H-03·F-01~F-08), 기준일·기준 커밋 — `e2e3125`
- [x] README 같은 사실 (R-01~R-05) — `4655a3a`
- [x] S-04 판정 보류 — 고치지 않음, 관련 사실(RedactingFilter 위치)만 A-10 과 함께
- [x] 누락 표 6항목 반영(CI 세 job·e2e / AccessPolicyGuard·예외 미들웨어·422 / Redis 503 / 생성기 v1 / CLI 폐기 / 401 headers)
- [x] ARCHITECTURE §14 변경 이력 한 줄
- [x] 검사: `tests/test_doc*.py`, 링크·앵커 broken 0, `review_gate --group docs`, html.parser 태그 짝 0, 줄바꿈 보존
