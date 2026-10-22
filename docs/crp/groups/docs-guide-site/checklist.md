# Checklist — docs-guide-site

## Round 0 — 2026-10-22 (계획)
- [x] 요청을 design-baseline §2 에 기록(REQ-001)
- [x] 생성물 원본을 그대로 커밋 — `362eafe`
- [x] 지적마다 코드 근거를 다시 열어 확인 — 범위·사실 정정 4건(GS-03·OP-02·RP-04·TS-01), 나머지 그대로

## Round 1 — 2026-10-22 (수정) — 완료
- [x] 계약 테스트를 먼저 써서 생성물에서 4건 실패 확인
- [x] 트랜잭션·흐름·인증·기능 문서 — `a275ad1`
- [x] 시작·설정·API·테스트·배포 문서 — `043d1c3`
- [x] 허브·README — `ad25277`
- [x] docstring·`.env.example`·ARCHITECTURE 변경 이력 — `487375f`
- [x] 계약 테스트 — `86a066a`
- [x] docs-guide-review residual-risk 원복 + 해결 기록 추가
- [x] 검사: 계약 테스트 통과, `.env` 없는 클론 `pytest -m "not mysql"`, ruff, 링크 검사, `review_gate --group docs`, 태그 짝 0
