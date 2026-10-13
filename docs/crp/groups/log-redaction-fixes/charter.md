# Charter — log-redaction-fixes  (Charter v0.1 / 2026-10-13)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001·REQ-002)·불가침 제약(C-1~C-6)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 로그 마스킹 | `app/utils/logs/filters.py`, `app/utils/logs/setup.py` | 소스 | `RedactingFilter` 가 `exc_text`·`stack_info` 도 가림, `Bearer` 규칙, `redact_handlers` |
| Celery 로깅 | `app/celery/worker_lifecycle.py` | 소스 | `after_setup_logger`·`after_setup_task_logger` 수신자 |
| 예외 응답 헤더 | `main.py` | 소스 | `StarletteHTTPException` 핸들러가 `exc.headers` 를 싣는다 |
| Redis 최소 버전 | `app/core/redis.py`, `app/core/resources.py` | 소스 | `REDIS_MIN_VERSION`·`check_redis_version`, lifespan 연결 직후 호출 |
| 버전 서술 | `app/core/security/rate_limiter.py`·`refresh_store.py` docstring, `compose.test.yaml`, `.env.example` | 주석 | |
| 커버리지 정책 | `pyproject.toml`, `.github/workflows/ci.yml`, `scripts/review_gate.py` | 설정 | `fail_under = 0`, `--cov=app --cov-config=pyproject.toml --cov-report=term-missing` |
| 테스트 | `tests/utils/test_log_redaction.py`(확장), `tests/test_http_exception_headers.py`·`tests/core/test_redis_version.py`·`tests/test_coverage_policy.py`(신규), `tests/test_lifespan.py`·`tests/core/test_token_service.py`(수정) | 테스트 | |
| 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`·`DEVELOPMENT.md`·`server-lifecycle-guide.html`·`feature-development-guide.html` | 문서 | |

- 기준선: base `179bfe1`(main) · `pytest -m "not mysql"` 1140 passed / 43 deselected / skip 0(admin-login 종료 기록) ·
  라우트 인벤토리 22 paths / 37 operations · alembic head `a7c3e9f1b2d4`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- 로깅: `app/utils/logs` 의 dictConfig(console·회전 파일 queue·uvicorn `log_config`) + uvicorn CLI 기본 핸들러 + Celery 워커 핸들러.
- Redis: **7.0 이상**(코드가 쓰는 명령 중 `EXPIRE … NX` 가 7.0). 관리형 Redis 가 `INFO` 를 막으면 확인을 건너뛴다.
- 커버리지: pytest-cov 6.3, 하한은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나.

### 2-2. 위협 모델
- **방어한다**
  - 로그로의 비밀값 유출 — 예외 메시지·체인(`__cause__`·`__context__`)·`stack_info` 에 실린 DSN 자격증명, `password=`/`token=` 형태 값,
    `Bearer` 토큰. 모든 핸들러 경로(console·파일·`python main.py` 의 uvicorn·`uvicorn main:app` CLI·Celery 워커).
  - 낮은 Redis 에서 "기동은 되는데 첫 로그인이 500" — 기동 시 거부.
  - HTTP 계약 누락 — 405 `Allow`·401 `WWW-Authenticate` 등 예외가 실어 온 헤더.
- **방어하지 않는다** (residual-risk)
  - 키워드·DSN·Bearer 꼴이 아닌 비밀값(예: 예외 메시지에 맨 값으로 실린 토큰), `Basic` 등 다른 인증 스킴(R-402).
  - 접속 로그 테이블의 `session_id` 쿠키·Referer·X-Forwarded-For 원문 저장 — 사용자 결정으로 유지(R-401).

### 2-3. 불변식 (Invariants)
- INV-1: 프로젝트 핸들러 경로마다 예외 traceback·체인·`stack_info` 의 비밀값이 출력에 없고 `***` 가 있으며, 예외 타입·파일·줄·체인 문구는 남는다. (검사: `tests/utils/test_log_redaction.py` 의 `test_development_console_handler_masks_traceback`·`test_production_console_and_file_handlers_mask_traceback`·`test_uvicorn_log_config_masks_traceback`·`test_uvicorn_cli_default_handlers_get_the_filter`·`test_celery_worker_handlers_get_the_filter`·`test_filter_masks_exc_text_chain_and_stack_info`·`test_bearer_token_is_masked`)
- INV-2: 마스킹 규칙의 정본은 `filters.redact()` 하나다 — 다른 경로는 `RedactingFilter` 를 단다. (검사: INV-1 테스트가 모두 같은 필터를 거친다, `test_filter_is_wired_into_logging_config`)
- INV-3: HTTP 예외의 `headers` 가 응답에 실리고 본문 형식(`error_code`·`message`·`detail`)은 그대로다. 405 의 `Allow` 는 실제 허용 메서드와 같다. (검사: `tests/test_http_exception_headers.py`)
- INV-4: Redis 가 `REDIS_MIN_VERSION` 미만이면 기동이 멈추고 자원이 정리된다. 이상이면 통과, INFO 거부(`ResponseError`)·버전 판독 불가면 WARNING 후 계속, 연결 오류는 올린다. 상수는 소스가 쓰는 명령의 도입 버전 최댓값과 같다. (검사: `tests/core/test_redis_version.py`, `tests/test_lifespan.py::test_redis_below_the_minimum_version_stops_startup`)
- INV-5: 커버리지 하한은 `pyproject.toml` 에 `fail_under = 0` 으로 명시돼 있고 CI·게이트·addopts 어디에도 `--cov-fail-under` 가 없으며, CI 단위 단계와 `tests` 게이트는 `--cov=app --cov-config=pyproject.toml --cov-report=term-missing` 으로 측정한다. (검사: `tests/test_coverage_policy.py`)

### 2-4. 비목표
- 접속 로그 원문 저장 방식 변경(사용자 결정으로 유지 — ADR-003).
- 엔드포인트 보호 방식 변경 — 명세 §5 는 조사·보고만 한다(ADR-006).
- 커버리지 하한 값 결정 — 사용자가 필요할 때 올린다(ADR-007).

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] 각 변경에 단위 테스트가 있고 fail-on-revert 를 확인했다(run-log).
- [x] `ruff check .` · `ruff format --check .` · mypy 클린.
- [x] `pytest -m "not mysql"` 전량 통과, skip/xfail 0 — 저장소 안과 `.env` 없는 저장소 밖 클론 양쪽. `mysql` 마커는 로컬에서 수집만 확인.
- [x] `scripts/review_gate.py` 의 structure · supply · docs 통과(static 은 같은 도구를 개별 실행, deps 는 네트워크라 생략).
- [x] alembic 리비전 추가 없음(head `a7c3e9f1b2d4` 단일).
- [x] INV-1~INV-5 에 실행 테스트 연결.

## 4. 변경 이력
- v0.1 (2026-10-13): 최초 작성. REQ-001·REQ-002 구현 완료 기준으로 기록(1166 passed / 43 deselected / skip 0).
