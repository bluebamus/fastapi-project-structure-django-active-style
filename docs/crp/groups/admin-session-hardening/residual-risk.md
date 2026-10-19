# Residual Risk — admin-session-hardening (잔여 위험 등록부)

> **재기 금지 목록.** 여기 "수용(Accepted)"으로 박제된 항목은 *의도적으로 고치지 않기로* 결정된
> 것이다. 다음 라운드에서 이걸 새 finding 으로 다시 올리면 안 된다. 고쳐야 하면 그것은
> "새 결함"이 아니라 **계약 변경 제안** — charter 를 먼저 바꾼다.

| ID | 항목 | Severity | 왜 비범위인가(계약 근거) | 수용일 | 재평가 조건 |
|---|---|---|---|---|---|
| R-701 | 살아 있는 세션의 쿠키를 훔치면 로그아웃·만료(미사용 30분·절대 8시간)·폐기 전까지 그 세션으로 쓸 수 있다. | LOW | 세션 쿠키 방식의 한계. HttpOnly·Secure·SameSite=Strict·짧은 미사용 만료로 줄였다(ADR-002). | 2026-10-19 | 관리자 단말 신뢰가 낮아지면 IP·User-Agent 바인딩이나 재인증(민감 작업)을 검토한다. |
| R-702 | sqladmin `@action` 은 GET 라우트라 CSRF 검사 대상이 아니다. 이 저장소에는 없다. | LOW | ADR-004. sqladmin 구조. DEVELOPMENT §12 체크리스트가 "상태를 바꾸는 작업을 action 으로 만들지 않는다" 를 안내한다. | 2026-10-19 | 상태를 바꾸는 action 이 필요해지면 action 경로를 미들웨어 대상에 넣고 스크립트가 링크를 POST 로 바꾸게 한다. |
| R-703 | JavaScript 가 꺼진 브라우저에서는 관리 화면의 상태 변경(생성·수정·삭제·로그아웃)이 403·405 다. | LOW | ADR-004. 토큰을 폼에 싣는 것은 스크립트다(sqladmin 폼 템플릿을 모두 덮어쓰지 않기 위해). sqladmin 자체도 삭제·가져오기에 JS 가 필요하다. 실패 방향이 안전하다. | 2026-10-19 | JS 없는 운영 환경을 지원해야 하면 create/edit 템플릿을 덮어써 hidden 필드를 서버에서 그린다. |
| R-704 | 로그인 화면 GET 은 익명 세션(CSRF 토큰)을 Redis 에 만든다 — 대량 GET 으로 작은 키가 쌓일 수 있다(TTL=미사용 만료). | LOW | ADR-001. 로그인 CSRF 는 세션이 필요하다. 키는 30분 뒤 사라진다. | 2026-10-19 | Redis 메모리 경보가 관측되면 익명 세션의 TTL 을 따로 짧게 두거나 로그인 화면 GET 에 rate limit 을 건다. |
| R-705 | **개정(2026-10-19, F-008, 브랜치 `fix/admin-ui-revoke-precommit`)** — 폐기를 커밋 전 훅(`on_model_change`·`on_model_delete`)으로 옮기고 API refresh 도 같은 폐기 집합(`revoke_user_access`)으로 끊는다. Redis 폐기 실패는 커밋을 막는다(ADR-008). **해소(2026-10-19, admin-session-hardening F-007, 브랜치 `fix/admin-ui-revoke`)** — `UserAdmin` 의 `after_model_change`(비활성화·슈퍼유저 해제·비밀번호 변경일 때만, 변경 전후 비교)·`after_model_delete` 가 `AdminSessionStore.revoke_user` 로 그 사용자의 모든 세션을 즉시 지운다(ADR-007). 원 기록: 관리 화면에서 사용자를 직접 편집(강등·비활성화)하거나 삭제하면 그 사용자의 **다른 브라우저** 세션은 Redis 에서 즉시 지워지지 않고, 다음 요청의 DB 확인(`authenticate`)에서 끊긴다. | LOW | ADR-003. 폐기 훅은 기존 refresh 폐기 지점(사용자 서비스)에 둔다는 명세. 관리 화면 경로도 refresh 를 폐기하지 않는다(기존 동작). 결과(다음 요청 거부)는 같다. | 2026-10-19 | 관리 화면 편집에도 refresh 폐기가 필요해지면 `UserAdmin.after_model_change`·`after_model_delete` 에서 같은 `_revoke_sessions` 를 부른다. |
| R-706 | 같은 경로를 메서드별 라우트로 나눈 경우 405 응답의 `Allow` 헤더에 첫 라우트의 메서드만 실린다. **사용자 결정으로 수용(2026-10-19)** — "405 문제는 현행 유지한다". | LOW | ADR-006. 기능·보안 영향이 없고, 고치려면 FastAPI/Starlette 라우터 내부 구조에 의존해야 한다. | 2026-10-19 | 클라이언트가 `Allow` 로 동작을 정하게 되면(예: 자동 생성 SDK) 재검토한다. |
| R-707 | **해소(2026-10-19, ADR-010)** — 감독자 결정으로 판정 규칙을 `user_service.py` 한 곳에 모으고 관리 화면도 강등 시 refresh 를 폐기한다(API 와 같음). 원 기록: 강등 시 API refresh 처리가 경로마다 다르다 — 관리 화면(`UserAdmin`)은 유지(ADR-009), API `UserService.update_user` 는 폐기(service-hardening, `test_demotion_revokes_refresh_tokens`). 두 경로 모두 안전한 쪽이지만 같은 사건의 결과가 다르다. | LOW | REQ-004 는 관리 화면 폐기 범위였고 UserService 를 바꾸면 service-hardening 의 기존 결정·테스트가 뒤집힌다 — 감독자 결정 대기. | 2026-10-19 | 감독자가 UserService 도 "강등은 refresh 유지" 로 맞추기로 하면 `update_user` 가 `revocation_for` 와 같은 규칙을 쓰게 바꾼다. |

<!--
규칙:
- 여기 있는 항목을 다음 라운드에서 새 finding 으로 다시 올리지 않는다.
- 재평가 조건이 참이 되면 ledger 로 승격한다(그때 비로소 "결함").
-->
