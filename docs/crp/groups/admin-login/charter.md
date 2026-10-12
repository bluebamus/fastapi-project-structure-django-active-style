# Charter — admin-login  (Charter v0.1 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001·REQ-002)·불가침 제약(C-1~C-7)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 관리 인증 | `app/features/auth/admin_auth.py`(신규) | 소스 | `AdminAuthBackend` |
| 자격 확인 공유 | `app/features/auth/services/auth_service.py` | 소스 | `verify_credentials` 추출, `AuthService.authenticate` 위임 |
| 조립 | `app/features/admin.py`, `main.py` | 소스 | 백엔드·템플릿 주입, `ADMIN_DISABLED` 분기 |
| 로그인 화면 | `app/templates/admin/sqladmin/login.html`(신규) | 템플릿 | Bootstrap 5.3.8 + SRI |
| 설정 | `config.py`, `.env.example` | 소스·문서 | `ADMIN_DISABLED`·`validate_renamed_settings`·확인 플래그 제거·Field 주석 |
| 배포 전 확인 주석 | `app/core/middlewares/client_ip.py`, `migrations/versions/e5a7c9d1f3b5_store_datetimes_as_utc.py`, `scripts/create_superuser.py`, `scripts/new_app.py`(템플릿), 기능 `admin.py`·`__init__.py` docstring, `app/core/registry.py` | 주석 | 리비전은 docstring 만(스키마 변경 없음) |
| 게이트 | `scripts/review_gate.py` | 소스 | 없앤·바꾼 설정 이름의 이력 인용 허용 |
| 의존성 | `pyproject.toml`, `uv.lock` | 설정 | `itsdangerous` |
| 테스트 | `tests/test_admin_login.py`·`tests/test_admin_disabled.py`·`tests/integration/test_mysql_admin_login.py`(신규), `tests/core/test_celery_app.py`·`test_deployment_safety.py`·`test_admin_lazy_import.py`, `tests/test_admin_wiring.py`, `tests/test_docs_learnability.py` | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`·`server-lifecycle-guide.html`·`feature-development-guide.html`·`admin-auth-guide.html`(신규) | 문서 | |

- 기준선: base `7a99987`(main) · `pytest -m "not mysql"` 1098 passed / 42 deselected / skip 0(service-hardening 종료 기록) ·
  라우트 인벤토리 22 paths / 37 operations · alembic head `a7c3e9f1b2d4`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- 관리 화면: sqladmin 0.32, starlette `SessionMiddleware`(itsdangerous 서명). Redis 필수(로그인 rate limit).
- DB: MySQL 8.4(운영·`mysql` 마커), SQLite(단위·통합 테스트).
- 브라우저: Bootstrap 5.3.8 CSS 를 CDN(jsDelivr)에서 SRI 로 받는다. CDN 이 막히면 스타일 없이 동작한다.

### 2-2. 위협 모델
- **방어한다**
  - 무인증 관리 화면 접근 — 활성 슈퍼유저 로그인 필수, 매 요청 DB 확인(강등·비활성화 즉시 반영).
  - 무차별 대입·credential stuffing — IP·IP+사용자명 고정 창 rate limit, 429 + `Retry-After`.
  - 계정 열거 — 실패 사유 미구분(같은 메시지·같은 상태 400), 없는 사용자도 더미 해시 검증.
  - 세션 고정 — 로그인 성공 시 세션 비운 뒤 id 만 저장.
  - 교차 사이트 요청 — `SameSite=Strict`, `Path=/admin`. 스크립트 접근 — HttpOnly. 평문 전송 — 배포 환경 Secure.
  - 관리 화면 노출 자체 — `ADMIN_DISABLED=true` 면 경로·링크·로그 없음.
  - 의미가 뒤집힌 설정 잔존 — 예전 `ADMIN` 이 남으면 기동 거부.
- **방어하지 않는다** (residual-risk)
  - 탈취된 세션 쿠키의 서버측 즉시 폐기(서명 쿠키 — 만료 8시간까지 유효, 강등·비활성화로만 끊김), sqladmin 폼의 CSRF 토큰,
    계정 잠금, 2FA.

### 2-3. 불변식 (Invariants)
- INV-1: `/admin` 은 활성 슈퍼유저만 들어간다 — 틀린 비밀번호·없는 사용자·비슈퍼유저·비활성은 400, 로그인 뒤 강등·비활성화는 다음 요청에서 302. (검사: `tests/test_admin_login.py` 의 `test_failed_login_is_400_with_one_indistinguishable_message`·`test_demoted_user_is_rejected_on_the_next_request`·`test_deactivated_user_is_rejected_on_the_next_request`·`test_create_superuser_then_full_admin_login_flow`, MySQL `tests/integration/test_mysql_admin_login.py`)
- INV-2: 관리 세션 쿠키는 `admin_session`·`Path=/admin`·`SameSite=Strict`·HttpOnly·8시간이고 로그인은 세션 내용을 바꿔 끼운다. (검사: `test_session_cookie_attributes`·`test_login_replaces_any_existing_session_content`·`test_logout_clears_the_session`)
- INV-3: 세션 인증은 `/admin` 전용이다. (검사: `test_session_middleware_lives_only_in_the_admin_sub_app`·`test_admin_session_cookie_does_not_authenticate_the_api`·`test_admin_session_cookie_is_never_set_outside_admin`·`test_crafted_cookie_is_a_valid_admin_session`)
- INV-4: 한도 초과는 429 + `Retry-After` 로그인 화면이고 키는 `admin:rl:` 다. (검사: `test_too_many_attempts_rerenders_login_with_429_and_retry_after`·`test_successful_login_resets_the_per_user_counter`)
- INV-5: `ADMIN_DISABLED=true` 면 관리 경로 404·응답·로그·미들웨어에 흔적이 없다. (검사: `tests/test_admin_disabled.py`, `tests/core/test_admin_lazy_import.py`, `tests/test_admin_wiring.py::test_admin_layer_is_not_loaded_when_disabled`)
- INV-6: 예전 `ADMIN` 이 남으면 기동하지 않고, 예전 확인 플래그는 코드·현행 문서에 없다. (검사: `tests/core/test_deployment_safety.py` 의 `test_leftover_admin_*`·`test_import_fails_with_leftover_admin`·`test_deployed_admin_starts_with_login_required`, `tests/test_admin_login.py::test_unauthenticated_admin_flag_is_gone_from_code_and_current_docs`)
- INV-7: 로그인 화면은 Bootstrap 5.3.8 + SRI 독립 페이지이고 오류는 이스케이프된다. (검사: `test_login_page_is_the_bootstrap_override`·`test_error_message_is_html_escaped`)
- INV-8: Celery include 모듈은 import 되고 태스크를 등록한다. (검사: `tests/core/test_celery_app.py::test_celery_include_modules_import_and_register_their_tasks`)

### 2-4. 비목표
- 관리 화면의 역할별 권한(sqladmin `AuthorizationBackend`), 2FA, 계정 잠금, 서버측 세션 저장소.
- 기존 ModelView 정의의 sqladmin 0.32 호환 수정(목록 필터 — ledger F-006, residual-risk R-305).
- 문서 중 이번 변경과 무관한 낡은 서술 정리(R-310).

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] 각 변경에 단위 테스트가 있고 fail-on-revert 를 확인했다(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0. `mysql` 마커는 로컬에서 수집만 확인.
- [x] `scripts/review_gate.py` 의 structure · supply · docs · deps 통과(static 은 같은 도구를 개별 실행).
- [x] alembic 리비전 추가 없음(head `a7c3e9f1b2d4` 단일).
- [x] INV-1~INV-8 에 실행 테스트 연결.
- [x] 실제 기동 스모크(uvicorn + SQLite 파일 + fakeredis TCP)로 로그인 흐름 확인(run-log Round 2).

## 4. 변경 이력
- v0.1 (2026-10-12): 최초 작성. REQ-001·REQ-002 구현 완료 기준으로 기록(1131 passed / 43 deselected / skip 0).
