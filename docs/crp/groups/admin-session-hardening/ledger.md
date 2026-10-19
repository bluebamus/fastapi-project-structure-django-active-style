# Ledger — admin-session-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001, security-ops-hardening R-602, admin-login R-301 | INV-1~INV-4 | Fix | **Fixed** | Round 1 | 관리 세션이 서명 쿠키(내용 전체가 쿠키)라 로그아웃·강등 뒤에도 복사본이 8시간 유효했고 서버에서 폐기할 수 없었다. **조치:** Redis 서버 세션(ADR-001·ADR-002), 사용자 서비스 폐기 훅(ADR-003), `itsdangerous` 제거. |
| F-002 | MED | REQ-001, security-ops-hardening R-601, admin-login R-302 | INV-5 | Fix | **Fixed** | Round 1 | 로그인 이후 생성·수정·삭제·일괄 삭제·가져오기 요청과 GET 로그아웃에 CSRF 토큰이 없었다(`SameSite=Strict` 에만 의존, `<img>` 강제 로그아웃 가능). **조치:** `AdminCsrfMiddleware` + `base.html` 덮어쓰기 + POST 전용 로그아웃(ADR-004). |
| F-003 | LOW | REQ-001, security-ops-hardening R-606 | INV-6 | Fix | **Fixed** | Round 1 | 날짜 필터가 하루 단위 연산만 있어 기간을 한 번에 지정할 수 없었다(빠른 선택도 없음). **조치:** `LocalDateFilter` 연산 `range` + 전용 템플릿 + 빠른 선택(ADR-005). |
| F-004 | — | REQ-001 "405 문제는 현행 유지한다" | — | Accept-out-of-scope | **Accepted** | Round 1 | 같은 경로를 메서드별 라우트로 나눈 경우 405 `Allow` 에 첫 라우트의 메서드만 실린다. 사용자 결정으로 유지(ADR-006, R-706). |
| F-005 | — | Round 0 조사 | — | Wont-fix | **확인 — 해당 없음** | Round 1 | 비밀번호 변경 경로(API·관리 화면)가 없다 — `UserAdmin` 은 `hashed_password` 를 폼에서 제외하고 `create_superuser --set-password` 는 스크립트다. 폐기 훅을 걸 지점이 없어 문서에 "생기면 같은 훅" 으로 남겼다. |
| F-006 | — | Round 0 조사 | — | Wont-fix | **확인 — 해당 없음** | Round 1 | 사용자 정의 `@action`(GET 라우트)은 이 저장소에 없다. 가져오기(`can_import`)를 켠 뷰도 없다 — 미들웨어·스크립트는 그래도 덮는다(헤더). |
| F-007 | LOW | REQ-002, R-705 | INV-7 | Fix | **Fixed** | Round 2 | 관리 화면에서 사용자를 비활성화·강등·삭제해도 다른 브라우저 세션이 Redis 에 남아 다음 요청의 DB 확인까지 기다렸다. **조치:** `UserAdmin` 훅 + `revoke_user_sessions`(ADR-007). |
| F-008 | LOW | REQ-003, F-007 후속 | INV-7 | Fix | **Fixed** | Round 3 | F-007 의 관리 화면 폐기는 커밋 뒤라 Redis 오류 시 "DB 는 비활성화됨 + 세션은 살아 있음" 이 남았고(503 으로 알릴 뿐), API refresh 토큰은 끊지 않았다(UserService 와 폐기 집합이 달랐다). **조치:** 커밋 전 훅 + `revoke_user_access` 공유, 503 변환 장치 제거(ADR-008). |
| F-009 | LOW | REQ-004(감독자 정정) | INV-7 | Fix | **Fixed** | Round 3 | F-008 직후 구현은 강등에도 API refresh 를 폐기했다. 강등된 사용자는 일반 사용자로 API 를 계속 쓰고 refresh 회전이 DB 권한으로 재발급하므로 과한 폐기였다. **조치:** `revocation_for` 하나가 관리 세션·refresh 두 집합을 돌려주고 강등은 관리 세션만(ADR-009). API `UserService` 와의 불일치는 R-707. |
