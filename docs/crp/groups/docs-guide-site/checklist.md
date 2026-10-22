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
- [x] Round 2: A-N1~A-N7·X-2 근거 재확인(8건 맞음)
- [x] Round 2: 보강 테스트(기능별 API 표·링크 fragment) 복사본 변이에서 실패 → 통과 — `eda2049`
- [x] Round 2: 문서·docstring 정정 — `7be79b3`
- [x] Round 2: 1차 CONVERGED 선언 정정 행(ledger)
- [x] Round 3: 규칙/진입점 분리 — 정본 표 `features/user.html#revocation`, 저장소 전체 grep 판정 — `24f7a63`·`f5e6fb5`
- [x] Round 3: A-C1 설정 표 계약 테스트 — 변이 4종 실패 → 원본 통과 — `74c483c`
- [x] Round 3: A-C2 접속 로그 docstring·.env.example — `f5e6fb5`
- [x] Round 4: 폐기 정본을 `revoke_user_access` 호출 모듈 표로 재정의 + AST 계약 테스트(변이 빼기·더하기 실패 → 원본 통과) — `76df541`·`9b76c66`
- [x] Round 4: A-R2-1 로그아웃(지금 세션 하나) / 강등·비활성화·삭제·CLI 비밀번호 교체(사용자 세션 전부) 분리 — `08337b9`
- [x] Round 5: 관리 세션 종료 문장 전수 판정 — ① 즉시 폐기 / ② 매 요청 DB 확인 귀속, A-R3-1 포함 — `4967927`
- [x] Round 5: A-R3-2 폐기 표 모듈 열·중복 금지 계약 테스트(변이 4종 실패 → 원본 통과) — `0725b4b`
