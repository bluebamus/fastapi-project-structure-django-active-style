# Ledger — log-redaction-fixes (결함 원장)

> 모든 finding 의 **영구 기록**. 한 번 적힌 항목은 사라지지 않는다(상태만 바뀐다).
> `Status=Fixed/Accepted` 인 항목은 다음 라운드에서 재검·재수정하지 않는다.
> 분류: **Fix**(계약 위반·고친다) / **Accept-out-of-scope**(계약 밖·안 고침→residual-risk)
> / **Wont-fix**(오탐·이유 명시). 심각도: CRIT / HIGH / MED / LOW.

| ID | Severity | 출처 | 위반 계약 조항 | 결정 | Status | 근거 | 비고 |
|---|---|---|---|---|---|---|---|
| F-001 | HIGH | REQ-001, orm-raw-repository R-007 | INV-1·INV-2 | Fix | **Fixed** | Round 1 | `logger.exception(...)` 의 traceback·체인 예외·`stack_info` 를 `RedactingFilter` 가 보지 않는다. 프로젝트 구성으로 재현: console(development·production)·`setup_uvicorn_logging()` 핸들러에서 DSN(`mysql+asyncmy://u:secret42@h/db`)·`password=secret42`·Bearer 토큰이 그대로 찍혔다. 파일 경로는 `QueueHandler.prepare` 가 traceback 을 메시지에 접어 넣어 DSN·`password=` 는 가려졌다. **조치:** 필터가 `exc_info` 를 미리 렌더해 `exc_text` 에 고정한 뒤 `redact()`, `stack_info` 도 `redact()`(ADR-002). 회귀: `tests/utils/test_log_redaction.py` 경로별 5건 + 필터 단위 1건. |
| F-002 | MED | REQ-001 재현 | INV-1 | Fix | **Fixed** | Round 1 | `Authorization: Bearer <토큰>` 은 키워드 규칙(`키=값`)에 걸리지 않아 메시지·traceback·파일 모든 경로에서 노출. **조치:** `redact()` 에 `Bearer` 규칙. 회귀: `test_bearer_token_is_masked` + 경로별 테스트. |
| F-003 | MED | REQ-001(외부 로거 경로 확인) | INV-1 | Fix | **Fixed** | Round 1 | `uvicorn main:app`(README 의 기본 실행)은 앱 import 전에 uvicorn 기본 핸들러를 세우고(propagate=False), Celery 워커는 root 를 가로채 자기 핸들러로 바꾼다 — 둘 다 마스킹 필터가 없어 "Exception in ASGI application"·태스크 실패 traceback 이 원문으로 찍힌다. **조치:** `redact_handlers()` 를 `configure_logging()`(uvicorn 로거 3개)과 Celery `after_setup_logger`·`after_setup_task_logger` 수신자가 부른다. 회귀: `test_uvicorn_cli_default_handlers_get_the_filter`·`test_celery_worker_handlers_get_the_filter`. |
| F-004 | MED | REQ-001 | INV-3 | Fix | **Fixed** | Round 1 | `DELETE /health` 405 에 `Allow` 가 없다 — `StarletteHTTPException` 핸들러가 `exc.headers` 를 버린다(401 `WWW-Authenticate` 등도 같다). **조치:** `headers=exc.headers`(ADR-004). 회귀: `tests/test_http_exception_headers.py`(4). |
| F-005 | LOW | REQ-001 | INV-4 | Fix | **Fixed** | Round 1 | Redis 요구 버전의 근거·확인이 없다. 7.0 미만에서는 기동되고 첫 로그인 rate limit(`EXPIRE … NX`)이 500. **조치:** `REDIS_MIN_VERSION`(7.0)·`check_redis_version()` 을 lifespan 에(ADR-005), 문서·docstring·compose·`.env.example` 서술 정리. 회귀: `tests/core/test_redis_version.py`(10)·`test_redis_below_the_minimum_version_stops_startup`. |
| F-006 | LOW | REQ-002 | INV-5 | Fix | **Fixed** | Round 2 | 커버리지 하한이 주석(`# fail_under = 80`)으로만 있고 CI·게이트가 커버리지를 재지 않는다. **조치:** `fail_under = 0` 명시, CI 단위 단계·`tests` 게이트가 측정·출력(ADR-007). 회귀: `tests/test_coverage_policy.py`(4). |
| F-007 | MED | F-006 작업 중 실측 | INV-5 | Fix | **Fixed** | Round 2 | `--cov=app` 만 주면 pytest-cov 6.3 이 서브프로세스 테스트에 설정 경로를 넘기지 않아 자식이 branch 없이 측정하고 합치기가 `Can't combine statement coverage data with branch data` INTERNALERROR 로 끝난다(suite 전체 실패). **조치:** `--cov-config=pyproject.toml` 명시. 회귀: `test_ci_unit_tests_measure_coverage`·`test_gate_tests_group_measures_coverage` 가 옵션을 요구. |
| F-008 | LOW | `.env` 없는 클론 실행(Round 2) | C-6 | Fix | **Fixed** | Round 2 | `tests/core/test_token_service.py` 의 not-yet-valid 사례가 `nbf` 를 **수집 시각**+1분으로 계산해, 수집에서 실행까지 1분을 넘기면(커버리지로 느려진 클론 실행 126초에서 실측) 거부되지 않아 실패한다 — 커버리지 측정이 CI 를 느리게 하므로 CI 에서도 나올 수 있다. **조치:** +1일. 회귀: 실행 시각이 지난 `nbf` 로 바꾼 변이에서 실패 확인. |
| F-009 | — | REQ-001(접속 로그 원문 저장) | — | Accept-out-of-scope | **Accepted** | Round 0 | `session_id` 쿠키·Referer·X-Forwarded-For 원문 저장 — 사용자 결정으로 유지(ADR-003). residual-risk R-401. |
| F-010 | — | 명세 §1 "함께 볼 것" | — | Wont-fix | **확인 — 해당 없음** | Round 0 | DEBUG 500 응답 본문에 `str(exc)` 를 싣는 경로를 찾았으나 없다 — `general_exception_handler` 는 DEBUG 와 무관하게 고정 메시지·`detail=null`(`tests/test_exception_handler_leak.py`). |
