# Charter — integration-e2e  (Charter v0.2 / 2026-10-20)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 REQ-001·REQ-002 와 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 테스트 환경 | `compose.e2e.yaml`, `tests/e2e/compose/{primary,replica}-init.sh`·`.gitattributes` | 설정 | MySQL 8.4 primary + GTID replica, Redis 7.4, 127.0.0.1·포트 13331/13332/16392, 프로젝트 `itest-active`, tmpfs |
| 하네스 | `tests/e2e/conftest.py`, `tests/e2e/inventory_probe.py`, `tests/redis_target.py` | 테스트 | 대상 안전 검사, `.env` 없는 자식, Alembic·슈퍼유저·uvicorn·Celery·Chromium, 인벤토리 추출 |
| 테스트 본문 | `tests/e2e/test_api_matrix.py`(L2)·`test_scenarios.py`(L3)·`test_db_routing.py`(L3-8·F-001)·`test_admin_ui.py`·`test_admin_auth.py`(L4)·`test_faults.py`(L5)·`test_ops.py`(L6)·`test_inventory.py`(W3) | 테스트 | `e2e` 마커, `-m e2e` 로만 수집 |
| 결함 수정 | `pyproject.toml`·`uv.lock`(F-001), `app/core/exception.py`(F-002), `app/features/catalog/admin.py`(F-003), `main.py`(F-004), `app/core/db/router.py`(F-005), `app/utils/logs/config.py`(F-006) | 소스 | 각 결함마다 단위 회귀 테스트 |
| CI | `.github/workflows/ci.yml` | 설정 | gate·mysql 의 pytest 단계에 `REDIS_HOST`·`REDIS_PORT`, job `e2e` |
| 게이트 | `scripts/review_gate.py` | 소스 | `E2E_*` 를 외부 환경변수로 인정 |
| 문서 | `README.md`(테스트·장애·로그 파일), `docs/guides/ARCHITECTURE.md`(Redis·라우팅·로깅·이력), `docs/guides/DEVELOPMENT.md`(Redis 계약·테스트·체크리스트) | 문서 | |

- 기준선: base `c463ac0`(main) · alembic 변경 없음 · 새 의존성: dev `playwright`·`pytest-timeout`, 런타임 `pymysql[rsa]`(= `cryptography`).

## 2. 계약 (Contract)

### 2-1. 불변식 (Invariants)
- INV-1: `-m e2e` 는 실패 0·skip 0·xfail 0, 0건이 아니다. (CI job `e2e` 의 판정 단계)
- INV-2: 하네스는 모든 접속 대상의 host 가 `127.0.0.1` 이고 포트가 계획서 §0 active 행이 아니면 시작하지 않는다. Redis 대상은
  `REDIS_HOST`·`REDIS_PORT` 가 둘 다 명시돼야 한다(W0, `tests/test_redis_target.py`).
- INV-3: 자식 프로세스(uvicorn·Celery·Alembic·스크립트)는 `.env` 를 읽지 않는다 — cwd 가 산출물 폴더, 설정은 하네스가 명시.
- INV-4: 인벤토리 대조에 빈 칸이 없다 — OpenAPI operation × 7칸, 관리 뷰 × 11칸, Celery 태스크, Redis 접두어(소스에서 추출),
  L3~L6 항목. 해당 없는 칸은 사유가 있는 N/A. (`test_inventory_has_no_empty_cells`)
- INV-5: 실행마다 만든 비밀값·사용자 비밀번호·발급 토큰·DSN 원문이 산출물의 어떤 로그에도 없다. (`test_no_secret_reaches_any_log`)
- INV-6: Redis 에는 소스가 만드는 접두어와 Celery·kombu 키만 있다. (`test_redis_holds_only_known_key_prefixes`)
- INV-7: Redis 연결·시간 초과 오류는 503 `SERVICE_UNAVAILABLE`, traceback 한 번, 연결 유지. (F-004)
- INV-8: read-only 세션의 replica 연결 계열 오류는 primary 로 한 번 재시도 + WARNING. 그 밖은 그대로. (F-005)
- INV-9: 기동 초기 줄은 그 프로세스의 파일(웹 `app.log`, Celery worker·beat `celery.log`)에 한 번. (F-006)

### 2-2. 비목표
- 다른 실행 경로의 500(전역 `Exception` 핸들러)이 traceback 을 두 번 남기고 연결을 끊는 것 — P-003(정책 결정 대기).
- OpenAPI 의 422 스키마 문서화 — P-001. `create_superuser --set-password` 의 세션 폐기 — P-002.
- 메서드 분할 경로의 405 `Allow` 값(첫 라우트의 메서드만) — 사용자 결정으로 현행 유지, 값만 기록.

## 3. 인수 기준
- `-m e2e` Windows·Linux(WSL 네이티브 `.env` 없는 클론) 모두 통과, skip·xfail 0.
- `-m "not mysql"`·`-m mysql` 통과, skip 0. ruff·mypy·review gate(structure·supply·docs·deps) 통과.
- 결함마다 fail-on-revert 확인 기록(run-log).
