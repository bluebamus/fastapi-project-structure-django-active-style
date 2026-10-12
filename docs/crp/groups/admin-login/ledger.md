# Ledger — admin-login (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001, service-hardening R-203 | INV-1·INV-2·INV-4·INV-7 | Fix | **Fixed** | Round 1 | `/admin` 이 자격증명 없이 열린다(배포는 확인 플래그로만). **조치:** `AdminAuthBackend`(활성 슈퍼유저·매 요청 DB 확인·세션 고정 방지·`admin:rl:` rate limit), `verify_credentials` 공유, Bootstrap 로그인 화면, `create_admin_interface` 주입. 회귀: `tests/test_admin_login.py` |
| F-002 | MED | REQ-001 | INV-6 | Fix | **Fixed** | Round 1 | 인증이 붙은 뒤에도 무인증 확인 플래그·배포 게이트의 "ADMIN=true 거부"·기동 WARNING 이 남는다. **조치:** 셋 다 제거, 남은 키는 `extra="ignore"` 로 무시(기동 회귀 테스트). |
| F-003 | MED | REQ-002 | INV-5·INV-6 | Fix | **Fixed** | Round 2 | 관리 화면을 완전히 끄는 설정이 "켬" 의미(`ADMIN`)라 사용자 결정대로 `ADMIN_DISABLED` 로 바꾸면, 남은 `ADMIN=false` 가 조용히 무시돼 관리 화면이 **켜진다**. **조치:** `validate_renamed_settings` 가 기동 거부, true 일 때 흔적 없음 4가지를 서브프로세스 테스트로 고정. |
| F-004 | LOW | 명세 §4 | INV-8 | Fix | **Fixed** | Round 1 | Celery include 모듈의 import 오류가 워커 기동 때만 드러난다. **조치:** `import_default_modules()` 로 import·등록 확인 테스트. |
| F-005 | LOW | REQ-001 | — | Fix | **Fixed** | Round 1 | "배포 전 확인"(프록시 홉 수·KST→UTC·첫 관리자·관리 로그인)이 문서마다 다르게·부분적으로 적혀 있고 "인증 없음" 서술이 남는다. **조치:** README 체크리스트 2a·2b·4·7 이 소유, 나머지는 같은 내용을 맥락별로(ADR-010). |
| F-006 | MED | 기동 스모크(Round 2) | INV-9 | Fix(REQ-003 으로 범위 편입) | **Fixed** | Round 3 | sqladmin 0.32 에서 `column_filters` 에 모델 컬럼을 그대로 넘긴 ModelView 5개(blog·home·reply·sns·user)의 목록 페이지가 500 — 스모크에서 `/admin/user/list` 가 `AttributeError: ... 'parameter_name'` 로 실패했다. 로그인 이전부터 있던 문제이며(뷰 정의) 이번 범위가 아니다. residual-risk R-305. **조치(Round 3, 감독자 결정):** 필터를 `BooleanFilter`·`OperationColumnFilter` 로, `created_at` 필터 제외(ADR-011). 회귀: `test_every_admin_list_page_and_filter_returns_200`(뷰 7개, 필터 14개)·`test_admin_detail_page_returns_200`. |
| F-007 | LOW | REQ-002 | — | Fix | **Fixed** | Round 2 | 세션 설정 설명("쿠키 세션 구현 없음, `SESSION_SECRET_KEY` 는 배포 게이트만 검사")이 README·ARCHITECTURE·server-lifecycle 가이드·`.env.example` 에서 낡았다. **조치:** 관리 세션 서명 키로 정정. |
| F-008 | LOW | residual-risk R-309 | — | Fix(REQ-003) | **Fixed** | Round 3 | ARCHITECTURE §12 의 revision 체인이 head 를 `e5a7c9d1f3b5` 로 적었다. **조치:** `a7c3e9f1b2d4`(head)까지 적었다. |
