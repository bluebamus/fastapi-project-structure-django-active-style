# Ledger — access-policy (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | MED | REQ-001, log-redaction-fixes R-406 | INV-1·INV-4 | Fix | **Fixed** | Round 1 | 새 뷰에 인증을 빠뜨려도 막는 기본값이 없다 — 유일한 장치인 권한표 테스트는 새 operation 을 PUBLIC 으로 분류하면 통과하고 `include_in_schema=False` 라우트를 보지 못한다. **조치:** `AccessPolicyGuard` 가 조립 끝에서 모든 `APIRoute` 를 검사해 기동 거부(ADR-002·ADR-003). 회귀: `tests/core/test_access_policy.py`. |
| F-002 | LOW | REQ-001 | INV-5 | Fix | **Fixed** | Round 1 | 공개 뷰에 표시가 없어 "공개로 정한 뷰" 와 "선언을 잊은 뷰" 를 코드에서 구별할 수 없고, 보호 방식이 인자·경로 의존성·라우터 의존성 셋으로 갈려 있다. **조치:** 예시 뷰 전체를 뷰 단위 선언으로 통일(ADR-004), OpenAPI 바이트 동일 확인. 회귀: `test_example_routes_declare_expected_access_levels`. |
| F-003 | LOW | REQ-001 명세 §4 | C-5 | Fix | **Fixed** | Round 1 | 분류표 `POLICY` 가 뷰 선언과 별도로 같은 분류를 또 적는다(두 벌). **조치:** `EXPECTED` 하나 + 가드 판정 대조(ADR-005). |
| F-004 | LOW | REQ-001 명세 §4 | INV-6 | Fix | **Fixed** | Round 1 | 스캐폴드가 접근 수준 선언을 가르치지 않는다. **조치:** 예시 뷰 파일 생성·안내문(ADR-006). |
| F-005 | — | Round 1 조사 | — | Wont-fix | **확인 — 해당 없음** | Round 1 | `/docs`(DEBUG 전용 Scalar)는 명세가 제외하라고 한 "FastAPI 가 붙이는 문서 경로" 가 아니라 main 이 `@app.get` 으로 붙인 `APIRoute` 다 — 제외 목록을 두지 않고 `Public` 을 선언했다(ADR-004). |
