# Charter — security-ops-hardening  (Charter v0.1 / 2026-10-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-7)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 엔진 옵션 | `app/core/db/session.py`, `migrations/env.py` | 소스 | `ENGINE_SAFETY_OPTIONS`(`hide_parameters=True`) — writer·reader·background·Alembic |
| 접속 로그 보존 | `config.py`(`ACCESS_LOG_RETENTION_DAYS`), `.env.example`, `app/features/home/{repositories/user_access_log_repository.py, services/access_log_retention_service.py(신규), dependencies/access_log_dependencies.py, tasks.py}` | 소스 | 배치 삭제·provider·beat 등록 |
| 관리 로그인 CSRF | `app/features/auth/admin_auth.py`, `app/features/admin.py`, `app/templates/admin/sqladmin/login.html` | 소스·템플릿 | synchronizer token |
| 관리 날짜 필터 | `app/core/admin_filters.py`(신규), `app/features/{home,blog,reply,sns,user,catalog,reports}/admin.py`, `scripts/new_app.py`(주석) | 소스 | `LocalDateFilter` |
| 테스트 | `tests/core/test_hide_parameters.py`·`test_admin_filters.py`(신규), `app/features/home/tests/test_access_log_retention.py`(신규), `tests/integration/test_mysql_access_log_retention.py`(신규, mysql), `tests/test_admin_login.py`·`tests/integration/test_mysql_admin_login.py`(갱신) | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`admin-auth-guide.html`, `.gitignore`(beat 상태 파일), 이전 그룹 residual-risk 주석 | 문서 | |

- 기준선: base `a1625fe`(main) · `pytest -m "not mysql"` 1190 passed / 43 deselected / skip 0(access-policy 종료 기록) ·
  alembic head `a7c3e9f1b2d4`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- SQLAlchemy 2.0 `create_engine`/`create_async_engine`/`engine_from_config` 의 `hide_parameters`.
- Celery 5 beat(`celery_app.conf.beat_schedule`, `crontab`, `timezone=TIME_ZONE`, `enable_utc=True`).
- sqladmin 0.32 — `Admin.login` GET 렌더 경로, `Jinja2Templates.env.globals`, `OperationColumnFilter` 프로토콜.

### 2-2. 위협 모델
- **방어한다**
  - DB 예외 문자열·`logger.exception`·SQLAlchemy echo 로그에 바인드 값이 실리는 것.
  - 접속 로그가 보존 기간 없이 무기한 쌓이는 것(개인정보 최소 보유).
  - 다른 사이트가 관리자의 브라우저로 `/admin/login` 에 POST 하는 로그인 CSRF(로그인 강제·시도 횟수 소진).
  - 관리 목록 날짜 필터 입력이 500 을 내는 것.
- **방어하지 않는다** (residual-risk)
  - 로그인 이후 sqladmin 폼·GET 로그아웃 CSRF(R-601), 관리 세션 서버측 폐기(R-602), beat 미기동(R-603), 엔진 밖의 값 노출(R-604).

### 2-3. 불변식 (Invariants)
- INV-1: 바인드 값은 예외 문자열과 운영 로그 파이프라인 출력에 없고 SQL 문은 남는다; 앱의 모든 엔진 객체가 `hide_parameters=True` 이고 모든 생성 지점이 정본 옵션을 펼친다. (검사: `tests/core/test_hide_parameters.py` 전체)
- INV-2: 보존 삭제는 `created_at < cutoff` 만 지우고(경계 행 유지) 배치마다 커밋하며 지운 수를 정확히 돌려준다; `0` 은 쿼리하지 않는다; 음수는 서비스·설정 모두 거부. (검사: `test_access_log_retention.py` 의 `test_only_rows_older_than_the_cutoff_are_deleted`·`test_deletes_in_batches_and_commits_each_batch`·`test_zero_retention_deletes_nothing`·`test_negative_retention_is_rejected_by_service_and_settings`·`test_rowcount_matches_count_query`, MySQL: `test_batched_purge_respects_cutoff_on_mysql`)
- INV-3: 설정 기본 365·`.env` 반영, provider 가 설정값을 쓰고, 태스크가 provider 로 조립되며, beat 에 매일 03:30 으로 등록된다. (검사: `test_retention_defaults_to_one_year_and_reads_the_env`·`test_provider_uses_the_configured_retention`·`test_purge_task_builds_its_service_through_the_home_provider`·`test_purge_task_is_scheduled_daily_at_0330_local_time`, `tests/core/test_settings_contract.py`)
- INV-4: 토큰 없음·빈 값·틀림·다른 세션·세션 없음·비 ASCII → 403, 자격 확인·레이트 리밋 카운터 미접촉; 올바른 토큰 → 302; GET 이 세션에 묶인 hidden 필드를 그림; 성공 후 회전; 403 재표시로 재시도 가능; 비교는 `hmac.compare_digest`. (검사: `tests/test_admin_login.py` 의 CSRF 절 10건 + 기존 로그인 테스트 전체)
- INV-5: 날짜 필터 경계(지역 자정 ±1초)·연산 3종·DST·기본 시간대·잘못된 입력 무시; `created_at` 이 있는 모든 뷰가 필터를 갖고 실제 목록 화면이 날짜로 좁혀지며 모든 목록·필터 쿼리가 200. (검사: `tests/core/test_admin_filters.py` 전체, `test_every_view_with_created_at_has_the_local_date_filter`·`test_date_filter_narrows_the_real_list_page`·`test_every_admin_list_page_and_filter_returns_200`·`test_filter_queries_are_actually_exercised`)

### 2-4. 비목표
- 액세스 토큰 수명·즉시 폐기 변경(ADR-005, 사용자 결정으로 유지), 관리 세션의 Redis 이전.
- 접속 로그 수집 필드 변경(C-7), sqladmin 내부 폼 CSRF.

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] 각 변경에 단위 테스트가 있고 fail-on-revert 를 확인했다(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽.
- [x] `-m mysql --collect-only` 로 새 MySQL 테스트 수집 확인(실행은 CI).
- [x] `scripts/review_gate.py` 의 structure · supply · docs 통과(deps 는 네트워크라 생략).
- [x] alembic 리비전 추가 없음(head `a7c3e9f1b2d4` 단일).
- [x] INV-1~INV-5 에 실행 테스트 연결.

## 4. 변경 이력
- v0.1 (2026-10-19): 최초 작성. REQ-001 구현 완료 기준으로 기록.
