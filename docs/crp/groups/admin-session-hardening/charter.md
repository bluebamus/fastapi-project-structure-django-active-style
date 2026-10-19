# Charter — admin-session-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-8)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| Redis 관리 세션 | `app/core/security/admin_session.py`(신규), `app/core/security/dependencies.py`(`get_admin_session_store`), `config.py`(`ADMIN_SESSION_*`), `.env.example` | 소스 | `AdminSessionStore`·`RedisSessionMiddleware`·`rotate_session` |
| 인증 백엔드·CSRF | `app/features/auth/admin_auth.py`, `app/features/admin.py` | 소스 | `AdminCsrfMiddleware`·`csrf_valid`·`_make_logout_post_only` |
| 폐기 훅 | `app/features/user/services/user_service.py`, `app/features/user/dependencies/user_dependencies.py` | 소스 | `_revoke_sessions` |
| 템플릿 | `app/templates/admin/sqladmin/base.html`(신규), `app/templates/admin/sqladmin/filters/local_date_filter.html`(신규) | 템플릿 | meta·스크립트, 기간 필터 |
| 기간 필터 | `app/core/admin_filters.py` | 소스 | 연산 `range`, `range_bounds`, `quick_ranges` |
| 의존성 | `pyproject.toml`, `uv.lock` | 설정 | `itsdangerous` 제거 |
| 테스트 | `tests/test_admin_session.py`(신규), `tests/test_admin_login.py`·`tests/core/test_admin_filters.py`·`tests/test_admin_disabled.py`·`tests/integration/test_mysql_admin_login.py`(갱신) | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`·`server-lifecycle-guide.html`, 이전 그룹 residual-risk 주석 | 문서 | |

- 기준선: base `ca7973c`(main) · alembic head `a7c3e9f1b2d4`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- sqladmin 0.32 — `AuthenticationBackend.middlewares`, `Admin.admin.router.routes`(이름 `logout`), 템플릿 로더의
  `sqladmin_original` 접두사, `base.html` 의 `head_tail` 블록, 필터 객체의 `template` 속성, `statics/js/main.js` 의
  삭제(`$.ajax` DELETE)·가져오기(`fetch`) 방식.
- Starlette 1.6 ASGI 미들웨어(`scope["session"]`, `http.response.start` 헤더), redis-py asyncio, Redis 7.0+
  (새 명령 없음 — `SET EX`·`GET`·`EXPIRE`·`DEL`·`SADD`·`SREM`·`SMEMBERS`).

### 2-2. 위협 모델
- **방어한다**
  - 로그아웃 뒤·권한 회수 뒤 복사된 관리 세션 쿠키의 재사용, 세션 고정, Redis 유출로 쿠키 위조.
  - 다른 사이트가 관리자의 브라우저로 보내는 생성·수정·삭제·일괄 삭제·가져오기·로그아웃 요청(CSRF), `<img>` 강제 로그아웃.
  - 기간 필터 입력이 500 을 내는 것.
- **방어하지 않는다** (residual-risk)
  - 살아 있는 세션 쿠키 자체의 탈취(R-701), 사용자 정의 GET action(R-702), JavaScript 차단 환경(R-703),
    익명 세션 키 누적(R-704), 관리 화면 직접 편집 시 다른 브라우저 세션 즉시 폐기(R-705), 405 `Allow`(R-706, 사용자 결정).

### 2-3. 불변식 (Invariants)
- INV-1: 쿠키 값은 43자 무작위 ID 뿐이고 Redis 키는 `admin:sess:` + 64자 hex HMAC 이며 원문 ID·사용자 id 가 쿠키·키에 없다; 사용자 인덱스에 키가 오른다. (검사: `tests/test_admin_session.py::test_cookie_carries_only_a_random_session_id`)
- INV-2: 로그아웃 뒤 이전 쿠키 사본은 302 + 쿠키 삭제; 로그인은 ID 를 회전하고 이전 키를 지운다; 미사용 TTL 은 요청마다 갱신되고 키가 사라지면 로그아웃; 절대 만료는 연장되지 않는다. (검사: `test_logout_kills_copied_cookie`·`test_login_rotates_the_session_id_and_deletes_the_old_key`·`test_each_request_resets_the_idle_ttl`·`test_idle_expiry_logs_out`·`test_absolute_expiry_is_never_extended`·`tests/test_admin_login.py::test_login_replaces_any_existing_session_content`)
- INV-3: 비활성화·강등·삭제는 그 사용자의 모든 브라우저 세션을 지우고 다른 사용자 세션은 남긴다; 프로필 수정은 유지; provider 가 저장소를 주입; `ADMIN_DISABLED=true` 면 저장소 없음. (검사: `test_user_changes_revoke_every_admin_session_of_that_user`·`test_profile_update_keeps_admin_sessions`·`test_user_service_provider_injects_the_admin_session_store`·`test_admin_disabled_builds_no_store`·`tests/test_admin_disabled.py`)
- INV-4: Redis 오류·클라이언트 없음 → 503. 설정 검증(ge=60, 미사용 ≤ 절대). (검사: `test_redis_failure_fails_closed_with_503`·`test_session_settings_are_validated`·`test_session_settings_defaults`)
- INV-5: 생성·수정·삭제·일괄 삭제·로그아웃 각각 토큰 없음·틀림 403(상태 불변), 맞으면 정상(폼·헤더 두 경로, 폼 본문 재생으로 실제 저장), 다른 세션 토큰 403, GET 은 토큰 불필요, GET 로그아웃 405, 403 은 로그인 화면이 아님, 렌더된 화면에 meta·스크립트, sqladmin 원본 템플릿 적합성. (검사: `tests/test_admin_session.py` §2 전체)
- INV-6: 기간 경계(시작일 자정 포함·종료일 마지막 마이크로초 포함·다음날 자정 제외), DST, 한쪽만, 역순·형식 오류 미적용+WARNING, 빠른 선택, 모든 created_at 뷰에서 기간 쿼리 200 + 실제로 좁혀짐, 전용 템플릿 렌더. (검사: `tests/core/test_admin_filters.py` 기간 절, `test_range_filter_narrows_every_created_at_list`·`test_range_filter_template_renders_two_dates_and_quick_links`·`tests/test_admin_login.py::test_every_admin_list_page_and_filter_returns_200`)

### 2-4. 비목표
- 405 `Allow` 헤더 보완(ADR-006, 사용자 결정), 액세스 토큰 수명 변경, 관리 화면 역할 세분화, sqladmin 사용자 정의 action 의 POST 화.

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] 각 변경에 단위 테스트가 있고 fail-on-revert 를 확인했다(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽.
- [x] `-m mysql --collect-only` 로 갱신한 MySQL 테스트 수집 확인(실행은 CI).
- [x] `scripts/review_gate.py` 의 네트워크 없는 그룹 통과.
- [x] alembic 리비전 추가 없음(head `a7c3e9f1b2d4` 단일).
- [x] INV-1~INV-6 에 실행 테스트 연결.

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성. REQ-001 구현 완료 기준으로 기록.
- v0.5 (2026-10-19): REQ-005 — INV-7 재정정: 관리 화면·API 모두 비활성화·강등·삭제(관리 화면은 비밀번호 해시 변경도)면 관리 세션과 refresh 를 모두 폐기, 판정은 `user_service.revocation_for` 한 곳. (검사: `test_admin_ui_edit_revokes_sessions_and_refresh_of_that_user`·`test_revocation_for_returns_both_sets_from_one_rule`·`tests/test_user_permissions.py` 의 `test_demotion_revokes_refresh_tokens`·`test_deactivation_revokes_the_family_itself`·`test_profile_update_keeps_refresh_tokens`)
- v0.4 (2026-10-19): REQ-004 — INV-7 정정: 강등은 관리 세션만 0 으로 하고 refresh family 는 유지한다(비활성화·삭제·비밀번호 해시 변경은 둘 다). 판정은 `revocation_for` 하나. (검사: `test_admin_ui_edit_revokes_sessions_and_refresh_of_that_user`[demote]·`test_revocation_for_returns_both_sets_from_one_rule`)
- v0.3 (2026-10-19): REQ-003 — INV-7 개정: 관리 화면 비활성화·슈퍼유저 해제·삭제·(훅 경유) 비밀번호 해시 변경은 **커밋 전에** 그 사용자의 관리 세션 키·인덱스를 0 으로 하고 API refresh family 를 폐기한다; 일반 수정은 둘 다 유지; Redis 폐기 실패 시 DB 변경이 커밋되지 않는다(수정 400·삭제 목록 오류). (검사: `tests/test_admin_session.py` 의 `test_admin_ui_*`·`test_password_hash_change_through_the_admin_hook_revokes_access`·`test_self_demotion_ends_the_current_session_too`·`test_revoke_failure_blocks_the_edit_commit`·`test_revoke_failure_blocks_the_delete_commit`·`test_save_does_not_resurrect_a_revoked_session`)
- v0.2 (2026-10-19): REQ-002(R-705 해소) — 인벤토리에 `app/features/user/admin.py`(폐기 훅), `app/core/security/admin_session.py`(`session_store_of`·`revoke_user_sessions`·`SET XX`) 추가. INV-7: 관리 화면 비활성화·슈퍼유저 해제·삭제·(훅 경유) 비밀번호 변경은 그 사용자의 세션 키·인덱스를 0 으로, 일반 수정은 유지, 자기 강등은 지금 세션도 끊고, 폐기 실패는 503, 폐기된 세션은 같은 요청의 저장으로 되살아나지 않는다. (검사: `tests/test_admin_session.py` 의 `test_admin_ui_*`·`test_password_change_through_the_admin_hooks_revokes_sessions`·`test_self_demotion_ends_the_current_session_too`·`test_revoke_failure_is_503_not_silently_ignored`·`test_save_does_not_resurrect_a_revoked_session`)
