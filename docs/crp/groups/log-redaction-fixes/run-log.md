# Run Log — log-redaction-fixes (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-10-13 (base SHA: `179bfe1`) — 계획·재현
- **트리거:** 사용자 요청 REQ-001(권장 항목 수정 — traceback 마스킹, 405 `Allow`, Redis 재정의; 접속 로그 원문 저장 유지).
- **검수 범위:** `app/utils/logs/*`, `main.py` 예외 핸들러, `app/core/redis.py`·`resources.py`, `app/core/security/rate_limiter.py`·`refresh_store.py`, `app/celery/*` 로깅, 문서.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **재현(수정 전 코드):** `build_dictconfig()`(ENV=production, 파일 켬)의 핸들러를 전용 로거에 붙이고 `setup_uvicorn_logging()` 을 적용한 뒤,
  `ConnectionError("connect to mysql+asyncmy://u:secret42@h/db failed")` 를 `RuntimeError("password=secret42 Authorization: Bearer …") from` 으로 감싸 `logger.exception` + `stack_info=True` 로 남겼다.
  결과 — console: `secret42`·Bearer 노출 · `{date}_app.log`·`{date}_error.log`: Bearer 만 노출(DSN·`password=` 는 `QueueHandler.prepare` 가 traceback 을 메시지에 접어 넣은 뒤 파일 핸들러의 필터가 가렸다) · uvicorn.error: `secret42`·Bearer 노출.
  외부 로거 확인 — SQLAlchemy 등은 root 로 전파(덮임), `uvicorn main:app` CLI 기본 핸들러와 Celery 워커 핸들러는 필터 없음(F-003).
- **신규 finding:** CRIT 0 · HIGH 1 · MED 3 · LOW 1 (F-001~F-005) · Accepted 1(F-009) · 해당 없음 1(F-010)
- **수렴 판정:** `NOT CONVERGED` (Open Fix 5)

### Round 1 — 2026-10-13 — REQ-001 구현
- **Fix:** F-001 · F-002 · F-003 · F-004 · F-005 → **Fixed**
- **설계:** ADR-002(필터 단계 — `exc_text` 고정 후 가림, `redact_handlers`), ADR-004(`headers=exc.headers`), ADR-005(`REDIS_MIN_VERSION`·`check_redis_version`).
- **동작이 바뀐 기존 테스트:** `tests/test_lifespan.py` 의 가짜 Redis 에 `info()`(7.4.0 보고)를 더했다 — lifespan 이 연결 직후 버전을 묻기 때문. 단언은 그대로.
- **조사(읽기 전용, ADR-006):** 명세 §5 엔드포인트 보호 현황 — `app.routes` 를 `_IncludedRouter` 까지 내려가 순회해 메서드·경로·의존성을 뽑아 감독자에게 보고했다. 구조적 한계는 R-406.
- **사고 기록:** fail-on-revert 변이(lifespan 의 버전 확인 제거 등 3건)를 돌릴 때 새 lifespan 테스트가 기동 DDL 까지 진행해 설정된 DB 주소(루프백 — 원격 아님을 불리언으로만 확인)에 연결을 시도했고 거부(2003)됐다. 테스트가 DDL 을 가짜로 두도록 고쳐 같은 변이에서도 DB 에 닿지 않음을 확인했다.

### Round 2 — 2026-10-13 — REQ-002 (커버리지 하한 0) + 문서
- **트리거:** 사용자 추가 요청 REQ-002.
- **Fix:** F-006 · F-007 · F-008 → **Fixed**
- **F-007 발견 경위:** CI 와 같은 명령(`--cov=app --cov-report=term-missing`)으로 전체 suite 를 돌리자 1165 passed 뒤 pytest-cov 합치기가 `Can't combine statement coverage data with branch data` INTERNALERROR. 원인 — 기본 `--cov-config`(`.coveragerc`)가 없으면 pytest-cov 6.3 이 서브프로세스용 설정 경로로 `os.pathsep`(빈 값)을 넘겨 서브프로세스 테스트가 branch 없이 측정. `--cov-config=pyproject.toml` 로 해소(같은 서브프로세스 테스트 2파일에서 전후 비교).
- **F-008 발견 경위:** `.env` 없는 클론에서 커버리지와 함께 돌린 첫 실행(126초)에서 `test_rejects_invalid_claims[not-yet-valid]` 만 실패 — `nbf` 가 수집 시각+1분이라 실행 시점엔 과거였다.
- **문서:** README·ARCHITECTURE·DEVELOPMENT·HTML 가이드 2종(최종 갱신 2026-10-13, html.parser 통과)·이 그룹 CRP. orm-raw-repository R-007 에 해소 주석 append.

### fail-on-revert (Round 1·2)
대상 파일을 작업 폴더 밖에 복사해 두고 결함을 되살린 내용을 넣어 돌린 뒤 복사본으로 복원했다.

| 되돌린 것 | 돌린 테스트 | 결과 |
|---|---|---|
| 필터의 `exc_text`·`stack_info` 마스킹 6줄 제거 | `tests/utils/test_log_redaction.py` | 6 failed · 15 passed(경로별 5·필터 단위 1) |
| `redact()` 의 Bearer 규칙 제거 | 같은 파일 | 7 failed · 14 passed |
| `configure_logging()` 의 `redact_handlers` 호출 제거 | 같은 파일 | 1 failed(uvicorn CLI) |
| Celery `after_setup_logger` 연결 제거 | 같은 파일 | 1 failed(Celery) |
| `headers=exc.headers` 제거 | `tests/test_http_exception_headers.py` | 3 failed · 1 passed(헤더 없는 예외 — 대조군) |
| lifespan 의 `check_redis_version` 호출 제거 | `test_redis_version.py`·`test_lifespan.py` | 1 failed |
| `REDIS_MIN_VERSION` 을 (6, 2) 로 | 같은 두 파일 | 3 failed(6.2.14 거부·계약·lifespan) |
| 버전 비교를 `if False` 로 | 같은 두 파일 | 4 failed |
| `except ResponseError` 를 `except Exception` 으로 | 같은 두 파일 | 1 failed(연결 오류 삼킴) |
| `fail_under = 0` 을 주석으로 | `tests/test_coverage_policy.py` | 1 failed |
| CI 단위 단계의 `--cov…` 제거 | 같은 파일 | 1 failed |
| CI 에서 `--cov-config` 제거 | 같은 파일 | 1 failed |
| CI·게이트에 `--cov-fail-under=85` | 같은 파일 | 각 1 failed |
| not-yet-valid 의 `nbf` 를 이미 지난 시각으로(수집 후 1분 경과 재현) | `tests/core/test_token_service.py` | 1 failed |

### 검사 수치 (최종)
- `pytest -m "not mysql" --cov=app --cov-config=pyproject.toml --cov-report=term-missing`: **1166 passed / 43 deselected / skip 0**(1140 → +26), 커버리지 TOTAL 96% — 저장소 안, 그리고 `.env` 없는 저장소 밖 클론(`git clone --branch fix/log-redaction`) 양쪽 같은 결과. `-m mysql --collect-only`: 43 수집(변화 없음). MySQL 실행은 CI 몫.
- ruff check·format 클린. mypy(순수 Python 빌드 1.20.2, `--python-executable` .venv) 202 files 0 issues. bandit `-ll` 0.
- `scripts/review_gate.py`: structure·supply·docs 통과(static 은 같은 도구를 위처럼 개별 실행, deps 는 네트워크 단계라 생략). alembic heads `a7c3e9f1b2d4` 단일 — 리비전 추가 없음.
- **수렴 판정:** `CONVERGED` — Open Fix 0.
- **잔여 위험 변화:** R-401~R-407 등록. orm-raw-repository R-007 의 "남은 좁은 구멍(traceback)" 해소.
