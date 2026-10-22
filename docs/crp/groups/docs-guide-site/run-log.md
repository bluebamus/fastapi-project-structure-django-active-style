# Run Log — docs-guide-site (라운드 로그 + 수렴 판정)

### Round 0 — 2026-10-22 (base SHA: `6f00cf6`) — 계획
- **트리거:** REQ-001 — "1번으로 지적 전부 고쳐줘".
- **입력:** active 지적 43건(HIGH 4 · MED 22 · LOW 17, 부수 2 포함).
- **확인:** `main.py`(미들웨어 등록 순서·DEBUG 문서·Guard), `config.py`(검사 3종·필드 75개), `app/core/resources.py`, `app/core/db/session.py`,
  `app/features/*/api/routers/v1/*.py`(쓰기 핸들러 commit 29곳), `auth_service.py`·`user_service.py`·`home/tasks.py`, `pyproject.toml` markers,
  `.github/workflows/ci.yml`, `tests/e2e/test_faults.py`(Redis 정지 중 blog 목록 200).
  정정 4건: GS-03·OP-02(Redis 장애는 Redis 경로만 503), RP-04(routed 세션 기능 사용 0), TS-01(`browser` 마커 없음).
- **수렴 판정:** `NOT CONVERGED` (Open Fix 43)

### Round 1 — 2026-10-22 — 수정
- **Fix:** ledger 전부 → **Fixed** (`a275ad1` · `043d1c3` · `ad25277` · `487375f` · `86a066a` · 이 기록 커밋).
- **계약 테스트:** `tests/test_docs_guide_site.py` 4건 — 생성물 원본에서 4 failed, 수정 후 4 passed.
- **검사:** `.env` 없는 클론에서 `pytest -m "not mysql"` 1448 passed · 44 deselected · skip 0 · `tests/test_doc*.py` 통과 ·
  ruff check·format 통과 · 링크 검사 broken 0 · `review_gate --group docs` 통과 · 새 HTML 태그 짝 오류 0·끝 개행.
- **수렴 판정:** `CONVERGED` (Open Fix 0)

### Round 2 — 2026-10-22 (base SHA: `a2181cd`) — 2차 재검수 수정
- **트리거:** 사용자 "2번으로 진행해줘" — round2-report 남은 결함 중 active 분(A-N1~A-N7, X-2).
- **재확인:** 8건 모두 코드로 다시 열어 맞음(`sales_reports.py`, `user_service.revocation_for`, `tests/e2e/test_faults.py`,
  `config.validate_deployment_safety`, `user_info_middleware._should_skip`, integration-e2e ADR-014, 두 문서 테스트의 링크 검사).
- **정정:** Round 1 의 `CONVERGED (Open Fix 0)` 은 FT-01·FT-03·부수-1 이 일부만 고쳐진 상태였다(ledger Round 2 정정 행).
- **Fix:** `eda2049`(테스트) · `7be79b3`(문서·docstring) · 이 기록 커밋.
- **보강 테스트:** 저장소 밖 복사본 변이 3종 — 기존 테스트 28 passed(못 잡음), 새 테스트 3 failed → 원본에서 29 passed.
- **수렴 판정:** `CONVERGED` (Open Fix 0, 재검수 대기)

### Round 3 — 2026-10-22 (base SHA: `b900316`) — 검수 루프 라운드 2
- **트리거:** 루프 라운드 2 지시 — 반복 지적(`workflows/authentication#Redis 503 범위`, `features/user#폐기 조건`) 거시 재진단 + A-C1·A-C2.
- **재진단:** 규칙(`revocation_for`)과 진입점(HTTP PATCH·DELETE / 관리 화면 / CLI `--set-password`)을 섞었다. `UserUpdate` 필드·`UserAdmin.form_excluded_columns`·auth 라우터(비밀번호 변경 없음)·`create_superuser` 종료 코드 2 로 확인.
- **Fix:** `24f7a63`(가이드·README·ARCHITECTURE) · `f5e6fb5`(주석·docstring·.env.example, 동작 변경 없음) · `74c483c`(설정 표 계약 테스트) · 이 기록 커밋.
- **TDD:** 저장소 밖 `.env` 없는 클론 변이 4종(MYSQL_PORT 3306→9999, 이름 MYSQL_PORTX, 중복 행, 설명 변조) — 기존 테스트는 셋 다 통과(못 잡음), 새 테스트는 4종 모두 실패 → 원본에서 통과.
- **검사:** 클론에서 문서 테스트·tests/scripts·test_admin_session·tests/core·user 테스트 895 passed, ruff check·format 통과, 링크 검사 broken 0, `review_gate --group docs` 통과.
- **상태:** 수정됨 — 검수 대기 (수렴 판정은 감독이 병합 때 기록)

### Round 4 — 2026-10-22 (base SHA: `7daf2ad`) — 검수 루프 라운드 3
- **트리거:** 루프 라운드 3 지시 — `features/user#폐기` 3회째 지적(거시 재진단 2) + A-R2-1(README 로그아웃 범위).
- **재진단:** `revoke_user_access` 호출부를 코드로 확정 — `app/features/user/services/user_service.py`(UserService PATCH·DELETE), `app/features/user/admin.py`(`on_model_change`·`on_model_delete` → `_revoke`), `scripts/create_superuser.py`(`--set-password`, 기존 사용자). 로그인 재해시는 `auth_service` 에서 해시만 UPDATE(폐기 없음). 로그아웃은 `session.clear()` → 미들웨어 `_commit` 이 그 SID 만 `delete`.
- **Fix:** `76df541`(폐기 정본 표 + 계약 테스트) · `08337b9`(로그아웃 범위 분리) · `9b76c66`(ruff format 끝 빈 줄) · 이 기록 커밋.
- **TDD:** 새 테스트는 수정 전 문서에서 실패(`admin.py` 누락). 저장소 밖 `.env` 없는 클론에서 문서 경로 하나 빼기(`admin.py`)·더하기(`auth_service.py`) 변이 둘 다 실패 → 원본 통과.
- **검사:** 클론에서 `tests/test_doc*.py` 35 passed, `ENV=test review_gate --group docs` 통과, ruff check·format 통과, 링크 검사 broken 0.
- **상태:** 수정됨 — 검수 대기 (수렴 판정은 감독이 병합 때 기록)

### Round 5 — 2026-10-22 (base SHA: `37cf2a7`) — 검수 루프 라운드 4
- **트리거:** 루프 라운드 4 지시 — 거시 재진단 3(관리 세션 종료 서술 3회 연속) + A-R3-1(ARCHITECTURE 789) + A-R3-2(폐기 표 테스트가 set 비교).
- **재진단(코드):** ① `revoke_user_access` 호출 = `user_service.py:108`(`_revoke_sessions` ← `update_user`·`delete_user`)·`admin.py:174`(`_revoke` ← `on_model_change`·`on_model_delete`)·`scripts/create_superuser.py:152`(커밋 전). 로그아웃 = `admin_auth.logout` → `session.clear()`(그 세션 하나). ② `admin_auth.py:181` `authenticate` — 사용자 없음·비활성·비슈퍼유저면 `session.clear()`.
- **두 층 전수 판정(맞음 = 고치지 않음):**
  - 고침: ARCHITECTURE 789(①+② 오귀속), ARCHITECTURE 750(② 범위), README 461(② 범위), admin-authentication 31 '폐기' 행(② 범위), `admin_auth.py` 10-11(② 범위), DEVELOPMENT 568-570·admin-authentication 372(① `revoke_user` → `revoke_user_access`), `features/user.html#revocation`(② 경계 문장 추가).
  - 맞음 ①: README 310(키 교체=전부 무효, 별도 사실)·466-470·547·611·652, ARCHITECTURE 742-749, DEVELOPMENT 568(앞 문장), features/index 58, user.html 13·32·33·61/71·75·89-90·106·111, authentication 142·144, getting-started 100, deployment 73, admin-authentication 172/187(키 없음=폐기)·216 행 7·8·9·222·270/279·327·328·340/351·352 전 행, `admin_session.py` 12·14-15·45·57·120·183, `admin.py` 145-153, `user_dependencies.py` 36, `user_service.py` 13-14·59-60·103·107·159-160·170, `create_superuser.py` 13·149·180-181·221.
  - 맞음 ②: admin-authentication 31 '권한 확인 시점' 행·166·167 도식(dbcheck)·216 행 10(정본)·356 '쿠키 탈취' 행, ARCHITECTURE 742('authenticate 거부는 키를 지우고').
  - 관리 세션 아님(범위 밖): ARCHITECTURE 573·675·705-706, `auth_dependencies.py` 129, `authorization.py` 19, `refresh_store.py` 71.
- **Fix:** `4967927`(문서·docstring) · `0725b4b`(계약 테스트) · 이 기록 커밋.
- **TDD:** 저장소 밖 `.env` 없는 클론 변이 4종 — (a) `user_service.py` 행 삭제 (b) `admin.py` 행 중복 (c) `admin.py` 행 삭제 (d) 비호출 모듈(`app/features/auth/admin_auth.py`) 행 추가. 기존 테스트는 (a)·(b) 통과(못 잡음), 새 테스트는 4종 모두 AssertionError 로 실패 → 원본 통과.
- **검사:** `.env` 없는 클론에서 `tests/test_doc*.py`·auth 테스트·`test_admin_login`·`test_admin_session` 184 passed, `ENV=test review_gate --group docs` 통과, ruff check·format 통과, 링크 검사 broken 0.
- **상태:** 수정됨 — 검수 대기 (수렴 판정은 감독이 병합 때 기록)
