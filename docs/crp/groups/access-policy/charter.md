# Charter — access-policy  (Charter v0.1 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-6)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 접근 수준·가드 | `app/core/security/access.py`(신규), `app/core/security/__init__.py`·`dependencies.py`(docstring) | 소스 | `Public`·`PublicWrite`·`LoginRequired`·`SuperuserRequired`·`AccessLevel`·`AccessPolicyGuard` |
| 조립 지점 | `main.py` | 소스 | 조립 끝 `AccessPolicyGuard().verify(app)`, `/health`·`/ready`·`/docs` 에 `Public` |
| 예시 뷰 | `app/features/{auth,blog,sns,reply,catalog,home,reports,user}/api/routers/v1/*.py` | 소스 | 뷰 단위 선언, home·reports 라우터 단위 의존성 제거 |
| 스캐폴드 | `scripts/new_app.py` | 소스 | `api/routers/v1/<name>.py` 예시 뷰, 안내문 |
| 테스트 | `tests/core/test_access_policy.py`(신규), `tests/test_authorization.py`(권한표 교체), `tests/scripts/test_new_app.py`(1건 추가) | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`·`feature-development-guide.html` | 문서 | |

- 기준선: base `3880451`(main) · `pytest -m "not mysql"` 1166 passed / 43 deselected / skip 0(log-redaction-fixes 종료 기록) ·
  라우트 인벤토리 22 paths / 37 operations · alembic head `a7c3e9f1b2d4`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- FastAPI 0.141.1 — `fastapi.routing.iter_route_contexts` 와 `_IncludedRouter` 의 effective route context(합쳐진 경로·의존성 트리).

### 2-2. 위협 모델
- **방어한다**
  - 선언을 잊은 뷰가 인증 없이 배포되는 것 — 숨긴 경로(`include_in_schema=False`)·중첩 include 포함.
  - 인증 없는 쓰기를 `Public` 으로 무심코 여는 것(→ `PublicWrite` 로 명시해야 함), 수준을 둘 이상 적은 모순 선언.
- **방어하지 않는다** (residual-risk)
  - 선언은 했지만 잘못 고른 수준(예: 관리 경로에 `Public`) — 사람의 판단이다. 예시 경로는 `EXPECTED` 회귀가 잡는다(R-501).
  - 소유권 판정 누락 — 선언이 아니라 서비스 동작이다(R-502).
  - `APIRoute` 가 아닌 라우트(Starlette `Route`·`WebSocketRoute`·`Mount`)를 앱에 직접 붙인 경우(R-503).

### 2-3. 불변식 (Invariants)
- INV-1: 선언 없음·수준 둘 이상·쓰기+`Public`·안전+`PublicWrite` 는 각각 위반으로 보고되고, 정상 선언 4종은 위반이 아니다. (검사: `tests/core/test_access_policy.py` 의 `test_route_without_declaration_is_a_violation`·`test_two_levels_are_a_violation`·`test_public_on_write_method_points_to_public_write`·`test_public_write_on_safe_method_is_a_violation`·`test_each_level_is_valid_alone`)
- INV-2: 인자 principal·라우터 단위 의존성·중첩 include·숨긴 경로가 판정에 들어오고, 문서 `Route`·`Mount` 는 빠지며, superuser 는 login 을 포함한다. (검사: `test_principal_argument_counts_as_declaration`·`test_superuser_wins_over_the_login_it_contains`·`test_router_level_dependencies_count_through_nested_includes`·`test_nested_undeclared_route_is_found`·`test_hidden_routes_are_checked`·`test_docs_routes_and_mounts_are_excluded`)
- INV-3: `verify` 는 위반 전부를 한 `AppContractError` 에 담는다. (검사: `test_verify_reports_every_violation_at_once`·`test_verify_passes_a_clean_app`)
- INV-4: 실제 앱은 가드를 통과하고, main 의 조립 경로가 가드를 실제로 부른다(라우터 결선 뒤 붙인 선언 없는 라우트로 import 가 실패). (검사: `test_real_app_passes_the_guard`·`test_main_refuses_to_assemble_with_an_undeclared_route`)
- INV-5: 예시 라우트의 판정 수준이 `EXPECTED` 와 같고 OpenAPI `security` 표시와 맞는다. 401/403·소유권 실요청 동작 불변. (검사: `tests/test_authorization.py` 전체, `tests/test_user_permissions.py`, `tests/test_openapi_contract.py`, `tests/test_route_inventory.py`)
- INV-6: 스캐폴드가 만든 예시 뷰는 선언을 갖고 가드를 통과한다. (검사: `tests/scripts/test_new_app.py::test_generated_example_view_declares_access_and_passes_the_guard`)

### 2-4. 비목표
- 권한 모델 변경(역할·그룹 세분화), 예시 정책 변경 — 현재 동작 유지(ADR-004).
- `/admin` 세션 인증 변경.

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] 각 변경에 단위 테스트가 있고 fail-on-revert 를 확인했다(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽.
- [x] 변경 전후 `app.openapi()` 직렬화 바이트 동일.
- [x] `scripts/review_gate.py` 의 structure · supply · docs 통과(deps 는 네트워크라 생략).
- [x] alembic 리비전 추가 없음(head `a7c3e9f1b2d4` 단일).
- [x] INV-1~INV-6 에 실행 테스트 연결.

## 4. 변경 이력
- v0.1 (2026-10-13): 최초 작성. REQ-001 구현 완료 기준으로 기록.
