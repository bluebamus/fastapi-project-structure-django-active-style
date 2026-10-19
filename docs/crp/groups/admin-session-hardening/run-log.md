# Run Log — admin-session-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-10-19 (base SHA: `ca7973c`) — 계획·조사
- **트리거:** 사용자 요청 REQ-001(로그인 이후 CSRF·GET 로그아웃, 관리 세션 Redis 이전(방법 2), 기간 필터, 405 현행 유지).
- **검수 범위:** `app/features/auth/admin_auth.py`·`app/features/admin.py`·`app/core/admin_filters.py`·`app/features/user/services/user_service.py`·`app/core/security/{dependencies,refresh_store}.py`, sqladmin 0.32 소스(`application.py` 라우트·로그인·로그아웃, `authentication.py`, `templates/sqladmin/{base,layout,create,edit,list}.html`·`filters/*`·`modals/*`, `statics/js/main.js`), starlette 1.6 의 세션 미들웨어 소스.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **조사:** 상태 변경 요청 — 생성·수정은 네이티브 폼 POST, 삭제·일괄 삭제는 jQuery `$.ajax` DELETE(본문 없음), 가져오기는 `fetch(FormData)`, 로그아웃은 GET 링크(`layout.html`), 사용자 정의 action 은 GET 라우트(이 저장소에 없음). 템플릿 로더에 `sqladmin_original` 접두사가 있어 원본 상속 덮어쓰기가 가능하고, 원본 화면 중 `head_tail` 을 덮어쓰는 것은 없다(`create.html` 은 `tail`, `edit.html` 은 `tail_js`). 필터는 객체의 `template` 을 include 한다. 폐기 지점은 `UserService.update_user`·`delete_user` 의 `revoke_user`. 비밀번호 변경 경로 없음(F-005). `itsdangerous` 소비처는 테스트 헬퍼뿐.
- **신규 finding:** CRIT 0 · HIGH 0 · MED 2 · LOW 1 (F-001~F-003) · 수용 1(F-004) · 해당 없음 2(F-005·F-006)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 3)

### Round 1 — 2026-10-19 — REQ-001 구현 (브랜치 `feat/admin-session`)
- **Fix:** F-001·F-002·F-003 → **Fixed**. F-004 → ADR-006 로 수용. 세 단계는 같은 테스트 파일(`tests/test_admin_session.py`·`tests/test_admin_login.py`)과 백엔드 모듈을 함께 바꿔 코드 커밋 하나로 묶었다(중간 커밋이 깨지지 않게). 문서·CRP 는 별도 커밋.
- **설계:** ADR-001(Redis 서버 세션 두 클래스·HMAC 키·사용자 인덱스), ADR-002(절대+미사용 만료·명시적 회전·503), ADR-003(폐기 훅 주입), ADR-004(CSRF 미들웨어·본문 재생·base.html·POST 로그아웃), ADR-005(기간 연산·전용 템플릿·빠른 선택), ADR-006(405 유지).
- **동작이 바뀐 기존 테스트:** `tests/test_admin_login.py` — `build_admin_app` 이 `session_store` 를 받고(기본 fakeredis `AdminSessionStore`), 로그아웃은 `logout()` 헬퍼(화면 meta 토큰으로 POST). `test_login_replaces_any_existing_session_content` 는 세션이 `{user_id, 새 csrf_token}` 이고 회전 표시가 섰는지 본다. Redis 키 단언 2건은 세션 키(`admin:sess:*`)를 빼고 레이트 리밋 키만 본다. 서명 쿠키 헬퍼(`_signed_admin_cookie`, itsdangerous)는 Redis 에 심은 세션 ID 로 바꿨다(`test_planted_session_id_is_a_valid_admin_session`). `test_session_middleware_lives_only_in_the_admin_sub_app` 은 `RedisSessionMiddleware` 를 본다. main 앱 조립 테스트는 미들웨어 목록·저장소 설정을 보고, 익명 리다이렉트 테스트는 `app.state.redis` 에 fakeredis 를 둔다(Redis 필수 — 없으면 503). 날짜 필터 대조군 14+7×4 → 14+7×5. `tests/core/test_admin_filters.py` 의 연산 목록 3 → 4. `tests/test_admin_disabled.py` 는 새 미들웨어 이름도 없음을 본다. `tests/integration/test_mysql_admin_login.py` 는 POST 로그아웃(수집만 확인).
- **DB 접속 없음:** 새 테스트는 파일 SQLite·fakeredis 만 쓰고 lifespan 을 돌리지 않는다. mysql 마커 파일은 `-m mysql --collect-only` 로만 다뤘다.

### fail-on-revert (Round 1)
대상 파일을 작업 폴더 밖(`C:\Users\rnd15\.claude\jobs\456c49a4\tmp\active\admin-session\backup\`)에 복사해 두고 결함을 되살린 내용을 넣어 돌린 뒤 복사본으로 복원했다(복원 후 바이트 비교 동일, 대상 124건 재실행 통과).

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| 사용자 서비스의 관리 세션 폐기 호출 제거 | `test_user_changes_revoke_every_admin_session_of_that_user` | 실패 |
| 로그인 시 세션 ID 회전 무시 | `test_login_rotates_the_session_id_and_deletes_the_old_key` | 실패 |
| 요청마다 TTL 갱신 안 함 | `test_each_request_resets_the_idle_ttl` | 실패 |
| `load` 의 절대 만료 검사 제거 | `test_absolute_expiry_is_never_extended` | 실패 |
| 세션을 비워도 Redis 키를 안 지움 | `test_logout_kills_copied_cookie` | 실패 |
| `RedisError` → 503 변환 제거 | `test_redis_failure_fails_closed_with_503` | 실패 |
| Redis 키를 HMAC 대신 세션 ID 원문으로 | `test_cookie_carries_only_a_random_session_id` | 실패 |
| CSRF 미들웨어 비교 통과 | `test_state_changing_request_without_a_valid_token_is_403`·`test_token_from_another_session_is_rejected` | 실패 |
| 폼 본문 receive 재생 제거 | `test_state_changing_request_with_the_session_token_succeeds` | 실패(다운스트림이 본문을 기다리며 멈춤 — 프로세스 종료로 판정) |
| GET 로그아웃 유지(라우트 교체 제거) | `test_logout_cannot_happen_by_get` | 실패 |
| 로그인 시 CSRF 토큰 새로 만들지 않음 | `test_login_replaces_any_existing_session_content` | 실패 |
| `admin_filters.py` 를 main 버전으로 | 기간 관련 16건(`-k "range or four"`) | 8 실패 |
| 기간 종료일을 다음날 자정 대신 종료일 자정으로 | `test_range_includes_both_ends`·`test_range_includes_the_last_microsecond_of_the_end_day` | 실패 |
| 역순 기간 허용 | `test_invalid_range_leaves_the_query_unfiltered_with_a_warning` | 실패 |
| `base.html` 의 `head_tail` 블록 이름 변경 | `test_rendered_admin_pages_carry_the_meta_token_and_script` | 실패 |

참고: 연산 목록에서 `range` 만 뺀 변이는 `get_filtered_query` 가 연산 이름으로 먼저 분기해 기간 질의 테스트 2건을 통과했다 — 목록 자체는 `test_offers_exactly_the_four_date_operations` 가 지킨다(main 버전 되돌림에서 함께 실패).

### 검사 (Round 1)
- `ruff check .` 통과 · `ruff format --check .` 통과 · mypy(규칙 파일 방법) 206 파일 이상 없음.
- `pytest -m "not mysql"` 1296 passed · 44 deselected · skip 0 (기준 main `ca7973c` 1231 passed — +65). `.env` 없는 저장소 밖 클론에서도 같은 수(보고서 참조).
- `-m mysql --collect-only tests/integration/test_mysql_admin_login.py` 1건 수집.
- `scripts/review_gate.py --group static structure supply docs` 통과(커밋 후 — docs 그룹은 git 추적 파일 기준). deps(pip-audit)는 네트워크라 생략.
- alembic head `a7c3e9f1b2d4` 단일(리비전 추가 없음).
- 실기동 스모크(uvicorn 실제 HTTP + fakeredis TCP 서버 + SQLite 파일 DB, 저장소 밖 임시 스크립트): 로그인 302 → 쿠키 43자·사용자 id 없음 → Redis 키 `admin:sess:<64hex>` 1개(세션 ID 미포함) → 생성 토큰 없음 403 / 폼 토큰 302 → 삭제 토큰 없음 403 / 헤더 200 → 기간 필터(옛 기간 미표시·열린 구간 표시) 200 → GET 로그아웃 405 → POST 로그아웃 302 → 이전 쿠키 사본 302 /admin/login → Redis 세션 키 0개.
- **수렴 판정:** `CONVERGED` (Open Fix 0)

### Round 2 — 2026-10-19 — REQ-002 R-705 해소 (브랜치 `fix/admin-ui-revoke`, base main `0ba9d85`)
- **Fix:** F-007 → **Fixed**(ADR-007, 커밋 `a8526ee`). `UserAdmin` 의 `on_model_change`·`after_model_change`·`after_model_delete`, `app/core/security/admin_session.py` 의 `session_store_of`·`revoke_user_sessions`·실패 표시 → 503·기존 세션 저장 `SET XX`.
- **조사:** sqladmin 0.32 `_queries.py` — 수정은 `on_model_change` → 값 반영 → commit → `after_model_change`, 삭제는 `on_model_delete` → delete → commit → `after_model_delete`. `application.py` 의 edit·delete 는 `update_model`·`delete_model` 예외를 잡아 400 폼·목록 `error` 로 그린다 — 그래서 실패 표시를 미들웨어가 503 으로 바꾼다.
- **동작이 바뀐 기존 테스트:** `test_planted_session_id_is_a_valid_admin_session` 이 새 세션을 `create=True` 로 심는다(기존 세션 저장은 키가 있을 때만 쓴다).
- **fail-on-revert:** 대상 파일을 작업 폴더 밖 `admin-ui-revoke\backup\` 에 복사해 두고 변이 후 복원(복원 후 대상 57건 재실행 통과).

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| 수정 훅의 폐기 호출 제거 | `test_admin_ui_edit_revokes_every_session_of_that_user`(비활성화·강등) | 2 실패 |
| 삭제 훅의 폐기 호출 제거 | `test_admin_ui_delete_revokes_every_session_of_that_user` | 실패 |
| 변경 전후 비교 없이 항상 폐기 | `test_admin_ui_plain_edit_keeps_sessions` | 실패 |
| 비밀번호 변경 비교 제거 | `test_password_change_through_the_admin_hooks_revokes_sessions` | 실패 |
| 기존 세션 저장의 `SET XX` 제거 | `test_save_does_not_resurrect_a_revoked_session` | 실패(처음 고른 자기 강등 테스트는 세션 내용이 안 바뀌어 TTL 갱신 경로라 통과 — 저장 경로 테스트를 더했다) |
| 미들웨어가 폐기 실패 표시를 안 봄 | `test_revoke_failure_is_503_not_silently_ignored` | 실패(수정 400·삭제 200 으로 삼켜짐) |

- **검사:** ruff check·format --check 통과, mypy 206 파일 이상 없음, `pytest -m "not mysql"` 1304 passed · 44 deselected · skip 0(Round 1 대비 +8), `.env` 없는 저장소 밖 클론 같은 수, alembic 변경 없음.
- **수렴 판정:** `CONVERGED` (Open Fix 0)
