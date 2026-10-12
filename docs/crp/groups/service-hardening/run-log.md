# Run Log — service-hardening (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.
> 단계 하나 = Round 하나(Round 0 = 계획).

## 라운드 기록

### Round 0 — 2026-10-12 (base SHA: `4707cd4`) — 계획
- **트리거:** 사용자 요청(REQ-001) — 2026-10-07 리뷰의 우선 조치 1~8 진행, Redis 필수, 로그인 고도화.
- **검수 범위:** 2026-10-07 전체 검수 리뷰의 지적 전수 대조 → 단계 A~F2 에 배정.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **기준선 실측:** `pytest -m "not mysql"` 814 passed / 32 deselected / skip 0 · 22 paths / 37 operations · alembic head `d4e6f8b12c34`.
- **신규 finding(심각도별):** CRIT 0 · HIGH 1 · MED 14 · LOW 8 (ledger F-001~F-023)
- **이전 요구 충돌:** orm-raw-repository charter 2-4 의 Redis readiness·JWT lifecycle 비목표와 R-002 의 권한 모델 비목표 → ADR-018 로 대체(그 그룹 design-baseline 에 상태 주석 append). SQLAdmin 비목표(C-8)는 유지(ADR-017).
- **수렴 판정:** `NOT CONVERGED` (Open Fix 23)
- **잔여 위험 변화:** R-201~R-204 등록.

### Round 1 — 2026-10-12 (base SHA: `e357f0c`) — 단계 A
- **트리거:** REQ-001 단계 A(리뷰 우선 조치 1·2 의 DSN·4).
- **검수 범위:** `.github/workflows/ci.yml`, `scripts/review_gate.py`, `config.py`·`migrations/env.py`·DSN 소비처, `app/core/db/router.py`, `app/core/repositories/repository_base.py`·`ProductRepository`·`UserAccessLogRepository`, 관련 가이드 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 에서 등록한 F-001~F-005 를 닫았다)
- **Fix:** F-001 · F-002 · F-003 · F-004 · F-005 → **Fixed**
- **fail-on-revert:** 수정 전 파일을 하나씩 되돌려 새 테스트를 돌렸다 — ci.yml 1 실패 · 게이트 1 실패(보조 가드 2건은 새 분기 고정용 대조군이라 통과) · DSN 8 실패(`config.py`+`env.py`) · 라우터 10 실패 · 정렬 base 3 / product 1 / access log 1 실패. 복원 후 전부 통과.
- **동작이 바뀐 기존 테스트:** `tests/core/test_db_router.py` 의 DSN 문자열 비교 7건을 `make_url(...)` 의미 비교로 바꿨다(속성이 `URL` 객체를 돌려주므로). 단언의 강도는 같다 — 드라이버·사용자·비밀번호·호스트·포트·DB 가 모두 비교된다. 삽입 순서에 기대던 목록 테스트는 없었다.
- **검사 수치:** `pytest -m "not mysql"` 845 passed / 32 deselected / skip 0(814 → +31), `-m mysql --collect-only` 32 수집, ruff check·format 클린, mypy 190 files 0 issues, review_gate `supply`·`docs`·`structure` 통과(static 의 mypy 는 로컬 정책 사유로 별도 실행 — 아래).
- **환경 주석:** 로컬 Windows 의 애플리케이션 제어 정책이 mypy 의 컴파일된 확장(DLL) 로드를 막아 `uv run python -m mypy .` 가 import 단계에서 죽는다. 같은 버전(1.20.2)의 순수 Python 빌드를 작업 폴더 밖 venv 에 설치해 `--python-executable` 로 이 저장소 venv 를 가리켜 실행했다. CI(ubuntu)에는 해당 없다.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 18: F-006~F-023 — 다음 단계)
- **잔여 위험 변화:** 없음.

### Round 2 — 2026-10-12 (base SHA: `679e4c6`) — 단계 B
- **트리거:** REQ-001 단계 B(리뷰 우선 조치 4·5 — 접속 로그 수집, 오류 매핑 버그).
- **검수 범위:** `app/core/middlewares/`(user_info_middleware·새 client_ip), `config.py` MiddlewareSettings·SessionSettings, home `UserAccessLogService`, `app/core/schemas.py`(신규)·5개 기능 Update 스키마, `app/core/repositories/repository_base.py`·새 `db_error_translator.py`, reports `ReportService`, `main.py` AppException 핸들러, 관련 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 의 F-006·F-007·F-009~F-013 을 닫고, F-008 은 B 부분만 닫음)
- **Fix:** F-006 · F-007 · F-009 · F-010 · F-011 · F-012 · F-013 → **Fixed**, F-008 → B 부분 Fixed(조회 접근 통제는 Round 7)
- **설계 구체화:** ADR-019 — `TRUST_PROXY_HEADERS` 제거·`TRUSTED_PROXY_HOPS` 대체, 홉 해석(`XFF[-N]`, 직접 피어를 0번째로 셈), delete 도 변환, 4xx WARNING·detail 미기록.
- **fail-on-revert:** 수정 전 파일을 작업 폴더 밖 사본으로 하나씩 되돌려 새 테스트를 돌렸다 — 미들웨어 6 실패 · config 2 실패 · home 서비스 1 실패 · 스키마 5개 11 실패(대조군 7 통과) · repository_base 2 실패(409 유지·변환기 단위 테스트는 대조군) · report_service 5 실패(경계 허용 3 은 대조군) · main 1 실패(5xx ERROR 는 대조군). 판정기는 신규 클래스라 변이로 확인 — "왼쪽 값 채택" 변이 7 실패, IP 검증 제거 변이 4 실패. 복원 후 전부 통과.
- **동작이 바뀐 기존 테스트:** `tests/core/test_client_ip_trust.py` 를 새 계약으로 고쳤다 — 예전 `test_first_hop_is_taken_from_forwarded_chain`(신뢰 모드에서 **왼쪽** 값 채택)은 이번에 고친 결함 자체를 고정하던 테스트라 반대 단언(`test_one_hop_takes_the_value_appended_by_our_proxy`)으로 바꿨고, bool 설정을 monkeypatch 하던 픽스처는 `ClientIPResolver(hops)` 직접 생성으로 바꿨다. 가짜 요청 객체는 실제 Starlette `Request` 로 바꿨다(여러 줄 XFF 를 시험하려고). 나머지 기존 테스트는 그대로 통과.
- **OpenAPI:** Home 태그 설명 문구만 바뀌었다(`TRUST_PROXY_HEADERS` → `TRUSTED_PROXY_HOPS`·민감 query 가림). 스키마 구조는 그대로다 — `PatchSchema` 는 `model_validator` 라 JSON Schema 에 나타나지 않는다(R-205). orm-raw-repository 의 `baseline/openapi.json` 은 그 그룹의 재구조화 이전 기록이고 비교하는 테스트가 없어 고치지 않았다.
- **검사 수치:** `pytest -m "not mysql"` 905 passed / 32 deselected / skip 0(845 → +60), ruff check·format 클린, mypy 193 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), review_gate `structure`·`supply`·`docs` 통과 · `static` 은 로컬 mypy DLL 차단으로만 실패(위 우회로 별도 확인). `deps`(pip-audit, 네트워크)는 생략했다.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 11: F-008(F2 부분)·F-014~F-023 — 다음 단계)
- **잔여 위험 변화:** R-205(OpenAPI 의 Update null 표기), R-206(Raw 경로 DB 오류 미변환) 등록.

### Round 3 — 2026-10-12 (base SHA: `f81b3a0`) — 단계 C
- **트리거:** REQ-001 단계 C(리뷰 우선 조치 6 — 테스트 하네스).
- **검수 범위:** 세션 Dependency 를 override 하는 모든 테스트(`app/features/*/tests/`, `tests/`), `tests/integration/conftest.py` 하네스, `docs/guides/DEVELOPMENT.md` 테스트 절.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 의 F-014·F-015 를 닫았다)
- **Fix:** F-014 · F-015 → **Fixed**
- **설계 구체화:** 헬퍼는 `tests/session_overrides.py` 한 모듈·한 함수다(conftest 픽스처가 아니라 import 하는 함수 — 기능 테스트의 엔진·훅이 제각각이라 픽스처 하나로 묶으면 매개변수가 픽스처 체인으로 숨는다). 기존 commit/rollback 집계는 세션을 직접 yield 하던 제너레이터 대신 `on_open` 훅으로 옮겼다. reports 는 일부러 writer 를 남기는 의도를 `writer=False` 로 유지했다. `tests/core/test_session_rollback_logging.py` 는 override 가 아니라 실제 Dependency 의 롤백 로깅을 시험하므로 바꾸지 않았다. C3 은 이 저장소에 해당 항목이 없다.
- **fail-on-revert:** 헬퍼의 `mark_read_only` 를 빼면 `test_read_only_override_rejects_a_write_from_a_get_route` 실패, catalog 엔드포인트 테스트를 수정 전 내용으로 되돌리면 `test_session_overrides_are_defined_only_in_the_helper` 실패(2 실패). 복원 후 전부 통과. MySQL 스모크는 로컬 실행 금지라 수집만 확인했고, 본문은 별도 in-memory SQLite 대입 실행으로 API 오용이 없음을 확인했다(collation 단언 1건은 MySQL 전용이라 제외).
- **동작이 바뀐 기존 테스트:** 10개 파일의 override 가 이제 운영과 같은 표시를 건다. 전환 후에도 기존 테스트가 전부 통과했다 — 조회 경로에서 몰래 쓰는 핸들러는 없었다. `tests/test_dto_before_commit.py` 의 `except Exception: rollback` 은 `async with` 의 close 가 같은 일을 하므로 뺐다.
- **검사 수치:** `pytest -m "not mysql"` 910 passed / 37 deselected / skip 0(905 → +5), `-m mysql --collect-only` 37 수집(32 → +5), ruff check·format 클린, mypy 193 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), review_gate `structure`·`supply`·`docs` 통과.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 9: F-008(F2 부분)·F-016~F-023 — 다음 단계)
- **잔여 위험 변화:** 없음.

### Round 4 — 2026-10-12 (base SHA: `0223722`) — 단계 D
- **트리거:** REQ-001 단계 D(리뷰 우선 조치 7 — 시각 정책, 결정: DB 는 UTC·마이크로초, 응답은 오프셋 포함 ISO 8601).
- **검수 범위:** `app/core/models/`(models_base·새 types), `config.py` `TimezoneSettings`, `migrations/env.py`·새 리비전, reports Service·Raw Repository, `app/celery/app.py`, 응답 스키마 설명 5개, `tests/integration/`(시각 왕복·리포트 시드), 관련 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 의 F-016 을 닫았다)
- **Fix:** F-016 → **Fixed**
- **설계 구체화:** ADR-020 — 단일 시각 클래스(`TimezoneSettings.utc_now`·`local_dates_to_utc`·`utc_offset`), `UTCDateTime`(`load_dialect_impl` 로 MySQL `DATETIME(6)`), Alembic `render_item` 훅(비교는 컴파일 DDL 이라 `compare_type` 훅 불필요 — 단 정밀도 차이는 Alembic 이 못 잡아 MySQL `DATETIME_PRECISION` 단언 추가), 리비전은 `op.get_context().dialect`·Core UPDATE, 리포트는 Service 가 경계·오프셋을 계산하고 Repository 는 타입 건 bind + `GROUP BY` 별칭. 새 head `e5a7c9d1f3b5`.
- **fail-on-revert:** 수정 전 파일을 작업 폴더 밖 사본으로 하나씩 되돌려 새 테스트를 돌렸다 — models_base 7 실패 · env.py 1 실패 · celery app 1 실패 · report_service 10 실패. `UTCDateTime` 은 신규 클래스라 변이로 확인 — UTC 변환 제거 2 실패, naive 허용 2 실패, 결과 UTC 부착 제거 5 실패, MySQL fsp 제거 1 실패. `utc_offset` 부호 변이 1 실패(New York). 복원 후 전부 통과. MySQL 테스트(`tests/integration/test_mysql_utc_datetime.py` 4건)는 로컬 실행 금지라 수집만 확인했다 — 리비전 SQL 은 오프라인 `alembic upgrade d4e6f8b12c34:head --sql`(MySQL 방언)로 `ALTER ... DATETIME(6) NOT NULL` + `UPDATE ... convert_tz(...)` 를 눈으로 확인했다.
- **동작이 바뀐 기존 테스트:** ① reports 기능 테스트의 Repository 대역은 새 시그니처(`start_at, end_at, tz_offset`)를 받는다 — `test_query_params_reach_repository_as_dates` 는 같은 계약을 UTC 경계로 단언하는 `test_query_params_reach_repository_as_utc_bounds` 로, 경계 허용 테스트는 지역 00:00 경계로 단언을 옮겼다(단언 강도 동일 이상 — 날짜 대신 순간·오프셋까지 비교). ② `tests/integration/test_sales_report_mysql.py` 는 시드를 KST 영업 시각으로 적고 UTC 로 넣으며, Repository 호출은 Service 와 같은 경계 계산을 거친다. 테스트 전용 일 단위 DELETE 도 KST 영업일로 비교한다. 기대 집계 값은 그대로다. ③ `tests/integration/test_mysql_orm_smoke.py` 의 같은 시각 시드를 aware UTC 로 바꿨다(naive 거부가 새 계약). 응답 직렬화 바이트 고정(`tests/test_response_serialization.py`)은 이미 aware UTC 를 `Z` 로 고정하고 있어 바꿀 필요가 없었다. 스키마 골든은 서명 `type` 이 그대로(`DATETIME`)라 바꾸지 않았다(ADR-020 ⑥).
- **OpenAPI:** 시각 필드 설명이 "생성/수정 시각(UTC, 오프셋 포함 ISO 8601)" 으로 바뀌었다. 구조 변화 없음.
- **검사 수치:** `pytest -m "not mysql"` 930 passed / 41 deselected / skip 0(910 → +20), `-m mysql --collect-only` 41 수집(37 → +4), ruff check·format 클린, mypy 194 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), `alembic heads` 단일 head `e5a7c9d1f3b5`, SQLite 빈 DB `upgrade head` 후 `alembic check` "No new upgrade operations detected", review_gate `structure`·`supply`·`docs` 통과.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 8: F-008(F2 부분)·F-017~F-023 — 다음 단계)
- **잔여 위험 변화:** R-207(리포트 고정 오프셋 — DST 지역), R-208(리비전의 KST 가정·downgrade 소수 초 반올림) 등록.

### Round 5 — 2026-10-12 (base SHA: `d00c7e8`) — 단계 E
- **트리거:** REQ-001 단계 E(리뷰 우선 조치 8 — 결정: Redis 필수 유지, `/ready` 에 Redis, Celery 태스크를 기능별로 두고 registry 로 발견).
- **검수 범위:** `app/core/redis.py`(신규), `main.py` `/ready`, `app/core/registry.py`, `app/celery/app.py`·중앙 태스크 모듈(삭제), `app/features/home/tasks.py`(신규)·home `dependencies`, `compose.test.yaml`, 관련 문서·`scripts/new_app.py` 독스트링.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 의 F-017·F-018 을 닫았다)
- **Fix:** F-017 · F-018 → **Fixed**
- **설계 구체화:** ADR-021 — `get_redis`(없으면 503)·`ping_redis`(DB 와 같은 상한), `/ready` 동시 점검, 태스크 발견은 `find_spec`(순환 방지 — 모듈 안 오류는 워커의 include import 가 드러냄), Celery 는 모듈 수준 `discover()`·`import_models()`·`task_modules()`, provider 를 "세션을 받는 일반 함수 + `Depends` provider" 로 분리, `redis-test` 이미지는 레지스트리 API 로 얻은 index digest 로 고정.
- **fail-on-revert:** 수정 전 파일을 작업 폴더 밖 사본으로 하나씩 되돌려 새 테스트를 돌렸다 — main.py 5 실패(Redis 503·200 의 Redis 왕복), registry.py 4 실패(그리고 celery app 이 `task_modules` 없이 import 실패), celery app + 중앙 태스크 모듈 2 실패(include 출처·AST 계약). 신규 코드는 변이로 확인 — `get_redis` 가 None 을 돌려주는 변이 2 실패, home 태스크가 서비스를 직접 만드는 변이 1 실패. 복원 후 전부 통과. 워커 경로는 `celery_app.loader.import_default_modules()` 로 include import 를 실행해 `home.aggregate_access_stats` 등록을 확인했다(브로커 접속 없음).
- **동작이 바뀐 기존 테스트:** ① `tests/test_ready.py` — 테스트 클라이언트는 lifespan 을 돌리지 않으므로 autouse 픽스처가 `app.state.redis` 에 정상 가짜 client 를 둔다(이전 테스트의 단언은 그대로). ② `tests/core/test_celery_app.py` — `"app.celery.tasks" in include` 단언을 "include = registry 발견 결과, home tasks 포함, 중앙 모듈 없음" 으로 바꿨다(중앙 모듈 삭제가 새 계약). ③ home `test_home_tasks.py` — 중앙 모듈 import 대신 home 태스크 모듈을 쓰고 태스크 이름 불변을 단언한다.
- **OpenAPI:** `/ready` 설명 문구만 바뀌었다("DB 와 Redis 까지 확인…"). 구조 변화 없음.
- **검사 수치:** `pytest -m "not mysql"` 948 passed / 41 deselected / skip 0(930 → +18), `-m mysql --collect-only` 41 수집(변화 없음), ruff check·format 클린, mypy 195 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), review_gate `structure`·`supply`·`docs` 통과.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 6: F-008(F2 부분)·F-019~F-023 — 다음 단계)
- **잔여 위험 변화:** R-209(앱 삭제 시 큐에 남은 태스크 메시지) 등록.

### Round 6 — 2026-10-12 (base SHA: `39e2b0d`) — 단계 F1
- **트리거:** REQ-001 단계 F1(리뷰 우선 조치 9 전반 — Argon2 해시와 기존 bcrypt 점진 이전, JWT claims 강화, refresh 회전·재사용 탐지, 로그인·가입 rate limit).
- **검수 범위:** `app/core/security/`(신규 — `tokens.py`·`refresh_store.py`·`rate_limiter.py`), `app/core/exception.py`(`headers`·`InvalidTokenException`·`TooManyRequestsException`), `main.py`(예외 헤더), `config.py`(`JWTSettings`), auth 기능 전부(해시기 모듈 신규 — F2 에서 `app/core/security/password_hasher.py` 로 이동·`auth_service.py`·`dependencies`·`api/routers/v1/auth.py`·`schemas`·`exceptions.py`), 옛 JWT·bcrypt 유틸 패키지(삭제), 관련 테스트·문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 □ 5 □
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 0 · LOW 0 (Round 0 의 F-019·F-020·F-021 을 닫았다)
- **Fix:** F-019 · F-020 · F-021 → **Fixed**
- **설계 구체화:** ADR-022 — 토큰 예외를 core 로, access `su` claim 은 F2 로, 저장소 TTL 은 생성자 인자, rate limit 은 MULTI `INCR`+`EXPIRE NX`+`TTL`·정수 설정 5개·`ClientIPResolver` provider, `/login` 항상 커밋·`/refresh`·`/logout` 무커밋, `get_current_user` 는 리포지토리 직접 조회, 옛 유틸 삭제, `pwdlib[argon2]`·dev `fakeredis` 추가.
- **fail-on-revert:** 새 클래스·경로는 변이로 확인했다(작업 폴더 밖 사본으로 복원) — `GETDEL`→`GET` 2 실패, 재사용 시 family 폐기 제거 1, 폐기 확인 제거 2, `EXPIRE NX`→`EXPIRE` 1, 로그인 성공 시 초기화 제거 1, IP 한도 제거 1, 핸들러의 `headers` 전달 제거 2, 가입 제한 의존성 제거 1, 옛 72바이트 절단 제거 1, 재해시 저장 제거 1, `require` 옵션 제거 6, `audience` 제거 5, `type` 검사 제거 1, `nbf` 제거 3. 복원 후 전부 통과. 수정 전 코드에는 새 모듈(`app.core.security`·`PasswordHasher`)과 `/logout` 이 없어 새 테스트는 수집 단계에서 실패한다.
- **동작이 바뀐 기존 테스트:** ① auth 엔드포인트·트랜잭션 경계 테스트와 `tests/test_dto_before_commit.py` — 가입·로그인이 Redis(rate limit·refresh 저장소)를 쓰므로 `get_redis` 를 `fakeredis.FakeAsyncRedis` 로 override(단언 불변). ② `tests/test_route_inventory.py` — `/api/v1/auth/logout` 추가(ADR-018: 이유를 주석으로). ③ `tests/test_read_path_no_commit.py` — login 은 재해시 저장 때문에 커밋하므로 무커밋 허용 목록에서 빼고, Redis 만 바꾸는 refresh·logout 을 이유와 함께 등록. ④ 옛 유틸 단위 테스트(tests/utils/test_auth.py)는 삭제 — 같은 단언(해시 왕복·72바이트 초과·토큰 왕복·종류 혼동·만료·변조)을 `test_password_hasher.py`·`test_token_service.py` 가 새 클래스에 대해 한다.
- **OpenAPI:** `authLogout`(204) 추가, `TokenResponse.expires_in` 필드, register·login 에 429 응답, refresh·logout 설명. 규칙 기반 계약 테스트(`tests/test_openapi_contract.py`) 통과.
- **검사 수치:** `pytest -m "not mysql"` 1001 passed / 41 deselected / skip 0(948 → +53), `-m mysql --collect-only` 41 수집(변화 없음), ruff check·format 클린, mypy 198 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), review_gate `structure`·`supply`·`docs` 통과, `uv lock --check` 통과.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 3: F-008(F2 부분)·F-022·F-023 — 단계 F2)
- **잔여 위험 변화:** R-210(rate limit IP 판정의 프록시 홉 의존) 등록.

### Round 7 — 2026-10-12 (base SHA: `31bd77a`) — 단계 F2 · 그룹 종료
- **트리거:** REQ-001 단계 F2(리뷰 우선 조치 9 후반 — 인증 주체·소유권·슈퍼유저 2단계, 운영 도구 `create_superuser`).
- **검수 범위:** `app/core/security/`(`authorization.py`·`dependencies.py` 신규, `password_hasher.py` 를 auth 에서 이동, `tokens.py` 의 `su`), `app/core/middlewares/user_info_middleware.py`, `app/core/tags_metadata.py`, blog·sns·reply(모델·스키마·서비스·provider·라우터), catalog·reports·home(라우터), user(모델·스키마·예외·서비스·provider·라우터), auth(provider·서비스·스키마), 리비전 `a7c3e9f1b2d4`, `scripts/create_superuser.py`, 스키마 골든, 관련 테스트·문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 1 · LOW 1 — 구현 중 발견한 F-024(접속 로그가 `user_id` 를 `call_next` 앞에서 읽어 항상 NULL), F-025(토큰 없음 401 이 FastAPI 기본 형식). 둘 다 이번 라운드에서 고쳤다.
- **Fix:** F-008(F2 부분) · F-022 · F-023 · F-024 · F-025 → **Fixed**
- **설계 구체화:** ADR-023 — 해시기·공유 provider 의 core 이동(auth 는 다시 내보냄), access `su` claim(ADR-022 ② 이행), `Principal`·`get_current_principal`(DB 조회 없음, `request.state.user_id`)·`require_superuser`·별칭 2개, `get_current_user` 는 주체 위의 DB 조회만, `OwnershipPolicy` 생성자 주입(글은 404 뒤 403, 사용자는 판정 먼저), 작성자 서버 기록·`author` 를 요청 스키마에서 제거, 관리 경로의 라우트·라우터 의존성, 특권 필드 403·`revoke_user`(비활성화·강등·삭제), 리비전 `a7c3e9f1b2d4`, 스크립트(getpass·`--password-stdin`, 환경변수 미사용), 접속 로그 응답 뒤 읽기.
- **fail-on-revert:** 변이 22종을 작업 폴더 밖 사본으로 복원하며 확인했다 — 모두 실패(KILLED). blog update 소유권 판정 제거 2 실패, sns delete 판정 제거 1, reply update 판정 제거 1, 정책의 NULL 소유자 허용 4, 정책의 슈퍼유저 우회 제거 3, `require_superuser` 무력화 12, catalog 생성 라우트 의존성 제거 1, reports 라우터 의존성 제거 2(분류표 포함), home 라우터 의존성 제거 5, user 목록 의존성 제거 1, 특권 필드 검사 제거 1, user 단건 조회 판정 제거 1, 비활성화·강등 폐기 제거 1, 삭제 폐기 제거 1, 생성 해시 제거 2, 작성자를 본문에서 받기 1, `su` 필수 해제 5, 로그인 토큰의 `su` 를 상수 False 로 1, 주체의 `request.state` 기록 제거 3, 미들웨어의 응답 뒤 읽기 제거 1, 스크립트 승격 플래그 제거 1, 스크립트 신규 슈퍼유저 플래그 제거 2. 토큰 없음 401 의 오류 형식은 `test_protected_routes_reject_missing_token` 의 error_code 단언이 고정한다(분기 제거 시 `AUTH_INVALID_TOKEN` 이 나가 실패). 수정 전 코드에는 `app.core.security.authorization`·`dependencies` 와 스크립트가 없어 새 테스트는 수집 단계에서 실패한다.
- **동작이 바뀐 기존 테스트(새 계약으로 갱신, 단언을 느슨하게 하지 않음):** ① blog·sns·reply·catalog·reports·user 엔드포인트 테스트와 blog 트랜잭션 경계 — 클라이언트에 기본 Bearer 헤더(`tests/auth_headers.py`, 실제 `TokenService` 서명)를 붙였다. 쓰기는 이제 인증이 필요하다. ② `blog::test_patch_null_on_nullable_field_clears_it` → `test_patch_cannot_change_author` — `author` 는 더 이상 수정 가능 필드가 아니다(본문 무시·작성자 유지 단언). ③ `sns::test_create_and_get_post` — 본문 `author="park"` 대신 서버 기록 `alice`·`author_id` 를 단언. ④ user 엔드포인트 — 생성 본문에 비밀번호, `get_redis` 를 fakeredis 로(비활성화·삭제가 refresh 저장소를 쓴다). ⑤ `tests/test_dto_before_commit.py` — 슈퍼유저 헤더·user 생성 비밀번호. ⑥ `tests/test_email_validation.py` — `UserCreate` 에 유효한 비밀번호를 넣어 이메일 규칙만으로 실패하게 했다(비밀번호 누락으로 우연히 통과하지 않도록). ⑦ `tests/test_update_noop.py` — 서비스 생성자에 `OwnershipPolicy`, 메서드에 슈퍼유저 주체. ⑧ `tests/core/test_token_service.py` — `issue_access` 세 번째 인자, 위조 claims 기본값에 `su`. ⑨ `tests/core/test_utc_datetime.py` 응답 시각 테스트에 사용자 헤더. ⑩ `tests/core/test_password_hasher.py` — 클래스와 함께 auth 기능 tests 에서 이동(단언 불변). ⑪ MySQL `tests/integration/test_mysql_orm_smoke.py` — 새 `UserService` 조립·비밀번호(로컬은 수집만).
- **스키마 골든:** `docs/crp/groups/orm-raw-repository/baseline/schema.json` 에 `users.is_superuser`·`blog_posts`/`sns_posts`/`replies.author_id` 4개 항목만 추가(기존 항목 무변경). 이유: 의도한 스키마 변경(ADR-023 ⑥), 마이그레이션 드리프트 테스트·`alembic check` 가 모델과 리비전의 일치를 따로 증명한다.
- **OpenAPI:** 경로·메서드 불변(라우트 인벤토리 22 / 37, 골든 그대로). 보호 operation 에 `security`(OAuth2PasswordBearer)·401/403 응답, 요청 스키마에서 `author` 제거, 응답에 `author_id`, `UserCreate.password`·`is_superuser`, `UserUpdate.is_superuser`, `UserResponse`·`AuthUserResponse.is_superuser`, 태그 설명(권한). 규칙 기반 계약 테스트(`tests/test_openapi_contract.py`) 통과, 새 분류표 테스트가 operation 별 `security` 표시를 권한 분류와 대조한다.
- **검사 수치:** `pytest -m "not mysql"` 1098 passed / 42 deselected / skip 0(1001 → +97), `-m mysql --collect-only` 42 수집(41 → +1, `test_mysql_authorization_revision.py`), ruff check·format 클린(330 files), mypy 201 files 0 issues(Round 1 과 같은 순수 Python 빌드 우회), alembic head 하나(`a7c3e9f1b2d4`), 빈 SQLite 에 `upgrade head` → `alembic check` "No new upgrade operations detected" → `downgrade -1` → `upgrade head`, review_gate `structure`·`supply`·`docs` 통과(ENV=test), `uv lock --check` 통과. 새 의존성 없음.
- **수렴 판정:** `CONVERGED` — Open Fix 0(F-001~F-025 전부 Fixed), charter §3 인수 기준 전부 충족, 잔여 위험은 residual-risk R-201~R-214 로 수용.
- **잔여 위험 변화:** R-211(권한 변경의 access 토큰 반영 지연)·R-212(작성자 표시 이름 복사·FK 없음)·R-213(옛 글은 슈퍼유저만 수정)·R-214(스크립트의 비밀번호 입력 경로) 등록.

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 1 | 14 | 8 | 23 | NOT CONVERGED |
| 1 | 0 | 0 | 0 | 0 | 0 (Fixed 5) | NOT CONVERGED |
| 2 | 0 | 0 | 0 | 0 | 0 (Fixed 7, 부분 1) | NOT CONVERGED |
| 3 | 0 | 0 | 0 | 0 | 0 (Fixed 2) | NOT CONVERGED |
| 4 | 0 | 0 | 0 | 0 | 0 (Fixed 1) | NOT CONVERGED |
| 5 | 0 | 0 | 0 | 0 | 0 (Fixed 2) | NOT CONVERGED |
| 6 | 0 | 0 | 0 | 0 | 0 (Fixed 3) | NOT CONVERGED |
| 7 | 0 | 0 | 1 | 1 | 2 (Fixed 5 — F-008 잔여·F-022~F-025) | **CONVERGED** |
