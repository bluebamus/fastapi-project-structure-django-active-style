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
