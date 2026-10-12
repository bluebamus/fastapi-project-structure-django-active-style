# Ledger — service-hardening (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.
>
> 출처: 2026-10-07 전체 검수 리뷰(로컬 보고서, 저장소에 커밋하지 않음)의 지적 번호를 `리뷰` 칸에
> 그대로 적는다(R-xx = 그 보고서의 번호, 이 그룹 residual-risk 의 ID 와 무관). 번호 없는 Low 항목은 요지를 적는다.

| ID | Severity | 리뷰 | 위반 계약 조항 | 결정 | Status | 근거(커밋/링크) | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | MED | R-14 | INV-1 | Fix | **Fixed** | 단계 A (Round 1) | CI 가 `uv sync --frozen` — 락 최신성을 보지 않는데 주석은 "어긋나면 실패" 라고 적었다. **조치:** 두 job 모두 `uv sync --locked`, 주석을 사실대로 고침. 회귀: `tests/scripts/test_review_gate.py::test_ci_installs_with_a_lock_freshness_check`(ci.yml 에 `--frozen` 없음 · 설치 단계가 job 수만큼 모두 `--locked`) — fail-on-revert 확인(수정 전 ci.yml 에서 실패). |
| F-002 | MED | R-17 | INV-2 | Fix | **Fixed** | 단계 A (Round 1) | 게이트가 작업 트리를 순회해 무시 대상(`.env`·로컬 전용 문서)까지 비밀 스캔·문서 경로 검사에 넣는다. **조치:** `_repo_files()` 가 `git ls-files -z` 를 쓰고(작업 트리에서 지운 추적 파일 제외), git 을 못 쓰면 `_walk_files()` 로 대체. 회귀: `test_repo_files_lists_only_tracked_files` — fail-on-revert 확인. 보조 가드 `test_repo_files_skips_tracked_files_deleted_from_the_worktree`·`test_repo_files_falls_back_to_walking_without_git` 은 새 분기를 고정한다(수정 전 코드에서도 통과하는 대조군). |
| F-003 | MED | R-06 | INV-3 | Fix | **Fixed** | 단계 A (Round 1) | DSN 을 f-string 으로 조립 — 비밀번호의 `@ / : #` 가 파싱을 깨고, `%` 는 Alembic 보간 오류. Redis URL 도 같다. **조치:** `MYSQL_URL`·`MYSQL_WRITER_URL`·`MYSQL_REPLICA_URLS`·`ALEMBIC_URL` 이 `URL` 객체(`URL.create`/`make_url`), `describe_routing()` 은 `render_as_string(hide_password=True)`(`mask_dsn`·`format_host` 제거, IPv6 대괄호는 `bare_host`), `migrations/env.py` 는 `%%` 이스케이프, Redis 비밀번호는 `quote(..., safe="")`. 기존 문자열 비교 테스트(`tests/core/test_db_router.py`)는 `make_url` 의미 비교로 바꿨다. 회귀: `tests/core/test_dsn_urls.py`(10) — fail-on-revert 8건 실패 확인. |
| F-004 | MED | R-10 | INV-4 | Fix | **Fixed** | 단계 A (Round 1) | ORM `with_for_update()` 가 read-only 가드를 통과하고 replica 로 라우팅된다. **조치:** `_is_locking_select()` — `_is_write()` 가 잠금 조회를 쓰기로 보고(writer + sticky), `_statement_is_readable()` 은 거부. 회귀: `tests/core/test_read_only_guard.py::test_orm_locking_select_is_blocked`(라우터 on/off × FOR UPDATE·SHARE·NOWAIT·SKIP LOCKED 8건), `tests/core/test_db_router.py::test_locking_select_is_served_by_writer`·`test_locking_select_in_read_only_session_is_rejected_by_the_router` — fail-on-revert 10건 실패 확인. |
| F-005 | MED | R-11 | INV-5 | Fix | **Fixed** | 단계 A (Round 1) | `get_all` 정렬 없음, 정렬하는 쿼리도 `created_at` 단일 키 — offset 페이지에서 중복·누락. **조치:** `get_all` 기본 정렬 `created_at DESC, PK DESC`(없으면 PK), `ProductRepository.list_active` 와 접속 로그 조회 4개에 `id DESC` 보조 키. 공개 메서드 수 불변(INV-15). 회귀: `tests/core/test_list_ordering.py`(5, 같은 created_at·섞인 삽입 순서에서 페이지 분할이 정확히 PK 역순) — 파일별 fail-on-revert 확인(base 3·product 1·access log 1). 삽입 순서에 기대던 기존 테스트는 없었다(전체 suite 변화 없음). |
| F-006 | MED | R-04 | INV-6 | Fix | Open | 단계 B | 신뢰 모드에서 XFF 의 가장 왼쪽 값을 채택 — 클라이언트가 IP 를 위조한다. |
| F-007 | MED | R-03 | 2-2 로그 누출·접속 로그 | Fix | Open | 단계 B | 컬럼보다 긴 헤더·쿠키에서 접속 로그가 조용히 버려진다(MySQL strict). |
| F-008 | MED | R-02 | 2-2 로그 누출 / INV-11 | Fix | Open | 단계 B·F2 | query_string 원문 저장(B), 접속 로그 조회 무인증(F2). |
| F-009 | LOW | 미처리 예외가 접속 로그를 우회 | 2-2 로그 | Fix | Open | 단계 B | `call_next` 에 try 가 없어 500 이 기록되지 않는다. |
| F-010 | LOW | session_id 쿠키 이름 불일치 | 2-2 로그 | Fix | Open | 단계 B | 미들웨어가 `session_id` 를 읽지만 설정 쿠키 이름은 `session` — 항상 NULL. |
| F-011 | LOW | null PATCH → 409, FK 위반 → 500 | 2-1 | Fix | Open | 단계 B | Update 스키마의 명시적 null 이 NOT NULL 위반을 "충돌" 로 응답한다. |
| F-012 | LOW | 리포트 기간 상한 없음 | 2-1 | Fix | Open | 단계 B | `end_date=9999-12-31` 에서 날짜 연산이 NULL 이 되어 빈 결과. |
| F-013 | LOW | 4xx 를 ERROR 로 로깅 | 2-2 로그 | Fix | Open | 단계 B | 클라이언트 오류가 운영 ERROR 로 쌓인다. |
| F-014 | MED | R-19 | C-6 | Fix | Open | 단계 C | 엔드포인트 테스트가 read-only 세션을 표시 없이 대체한다. |
| F-015 | MED | R-20 | 2-1 | Fix | Open | 단계 C | ORM 기능 경로가 MySQL 에서 한 번도 돌지 않는다. |
| F-016 | MED | R-09 | INV-7 | Fix | Open | 단계 D | `DateTime(timezone=True)` 가 MySQL 에서 오프셋·소수 초를 잃는다. |
| F-017 | MED | R-13 | INV-8 | Fix | Open | 단계 E | Redis 필수인데 `/ready` 가 Redis 를 보지 않는다(필수 유지 결정 — ADR-008). |
| F-018 | MED | R-18 | INV-9 | Fix | Open | 단계 E | 중앙 Celery 태스크가 기능을 직접 import, 워커는 registry 를 거치지 않는다. |
| F-019 | MED | R-07 | INV-10 | Fix | Open | 단계 F1 | refresh 회전·폐기와 로그인 rate limit 이 없다. |
| F-020 | LOW | bcrypt 72바이트 절단 | 2-2 | Fix | Open | 단계 F1 | Argon2 이전으로 해소(기존 해시는 기존 규칙으로 검증 후 재해시). |
| F-021 | LOW | `JWT_ALGORITHM` 자유 문자열 | 2-2 | Fix | Open | 단계 F1 | HS 계열 `Literal` 로 제한. |
| F-022 | HIGH | R-01 | INV-11 | Fix | Open | 단계 F2 | 모든 기능 CRUD 가 무인증 — 익명이 계정 정지·이메일 열거. |
| F-023 | LOW | 무인증 POST /users 가 비밀번호 없는 계정 생성 | INV-11 | Fix | Open | 단계 F2 | 생성은 슈퍼유저 전용 + 비밀번호 필수. |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
-->
