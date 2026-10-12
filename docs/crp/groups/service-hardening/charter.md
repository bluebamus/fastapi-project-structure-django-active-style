# Charter — service-hardening  (Charter v0.1 / 2026-10-12)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001)·불가침 제약(C-1~C-10)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

> 아직 없는 산출물은 경로 대신 이름으로 적는다(만들어지는 단계에서 경로로 바꾼다).

| 단계 | 영역 | 경로 | 종류 | 비고 |
|---|---|---|---|---|
| A1 | CI 재현성 | `.github/workflows/ci.yml` | 설정 | 두 job 의 `uv sync` |
| A1 | 검증 게이트 | `scripts/review_gate.py` | 소스 | 파일 목록 = git 추적 목록 |
| A2 | DSN | `config.py`, `migrations/env.py` | 소스 | `URL.create`·마스킹·Alembic `%` |
| A2 | DSN 소비처 | `app/core/db/session.py`, `app/core/resources.py`, `app/celery/app.py` | 소스 | URL 객체·Redis URL |
| A3 | 라우터·read-only | `app/core/db/router.py` | 소스 | 잠금 읽기 판정 |
| A3 | 목록 정렬 | `app/core/repositories/repository_base.py`, `app/features/catalog/repositories/product_repository.py`, `app/features/home/repositories/user_access_log_repository.py` | 소스 | 기본 정렬·PK 보조 키 |
| B | 접속 로그 | `app/core/middlewares/user_info_middleware.py`, `app/features/home/access_log_sink.py` | 소스 | 클라이언트 IP 판정 클래스(신규)·500 기록·민감 query·절단 |
| B | 오류 변환·PATCH | `app/core/repositories/repository_base.py`, `app/core/exception.py`, 각 기능 schemas | 소스 | null PATCH 거부·코드별 변환 |
| B | 리포트 기간 | `app/features/reports/services/report_service.py` | 소스 | 기간 상한 |
| C | 테스트 하네스 | 공용 override 헬퍼(신규), 기능별 `tests/test_endpoint` 계열 | 테스트 | read-only 표시 유지 |
| C | MySQL 스모크 | `tests/integration/` | 테스트 | `mysql` 마커 |
| D | 시각 정책 | `app/core/models/types.py`(신규), `app/core/models/models_base.py`, `config.py`(`TimezoneSettings`), `migrations/env.py`, `migrations/versions/e5a7c9d1f3b5_store_datetimes_as_utc.py`(신규), `app/features/reports/services/report_service.py`, `app/features/reports/repositories/sales_report_repository.py`, `app/celery/app.py`, 응답 스키마 설명 | 소스 | UTC 저장·리포트 영업일 |
| E | Redis·readiness | `app/core/resources.py`, `main.py`, `app/core/redis.py`(신규), `compose.test.yaml` | 소스 | `/ready` 의 Redis 확인 |
| E | Celery 발견 | `app/celery/app.py`, 중앙 태스크 모듈(단계 E 에서 삭제), `app/core/registry.py`, `app/features/home/tasks.py`(신규), home `dependencies` | 소스 | registry 기반 include |
| F1 | 인증 코어 | `app/features/auth/**`, 옛 JWT·bcrypt 유틸 패키지(단계 F1 에서 삭제), `app/core/security/`(신규), `app/core/exception.py`, `config.py`(`JWTSettings`), `main.py`(예외 헤더) | 소스 | 해시·토큰·refresh 저장소·rate limit |
| F2 | 인가·소유권 | core security 모듈, blog·sns·reply·catalog·reports·home·user 라우터와 서비스, 신규 Alembic 리비전 | 소스 | 주체·소유권·슈퍼유저 |
| F2 | 운영 도구 | `scripts/` 의 슈퍼유저 생성 스크립트(신규) | 소스 | Django `createsuperuser` 대응 |
| 공통 | 문서 | `README.md`, `docs/guides/ARCHITECTURE.md`, `docs/guides/DEVELOPMENT.md`, `.env.example` | 문서 | 단계마다 갱신 |

- 기준선: base `4707cd4` · `pytest -m "not mysql"` **814 passed / 32 deselected / skip 0** · 라우트 인벤토리
  22 paths / 37 operations · alembic head `d4e6f8b12c34`.

## 2. 계약 (Contract)

### 2-1. 지원 구성
- DB: MySQL 8.4(운영·`mysql` 마커 테스트), SQLite(aiosqlite) 단위 테스트. 라우터 on/off 양쪽.
- Redis: **필수**(ADR-008). 테스트는 fakeredis 또는 가짜 클라이언트 주입.
- 프록시: 앞단 신뢰 홉 수를 설정으로 받는다(기본 0 = 직접 피어만 신뢰).
- 인증: OAuth2 password 흐름 + Bearer access 토큰(JWT, HS 계열), refresh 토큰 회전.

### 2-2. 위협 모델
- **방어한다**
  - credential stuffing·대량 가입 — Redis 고정 창 rate limit(로그인 ip+username·ip, 가입 ip), 429 + `Retry-After`.
  - refresh 토큰 탈취 — 회전 + 재사용 탐지로 family 전체 폐기, 비활성화·삭제 시 사용자 family 전부 폐기.
  - IDOR — 수정·삭제는 소유자 또는 슈퍼유저만(`OwnershipPolicy`), 관리 경로는 슈퍼유저 전용.
  - 헤더 위조 — 클라이언트 IP 는 신뢰 홉 수만큼 오른쪽에서 고르고 `ipaddress` 로 검증한다.
  - 로그 누출 — 접속 로그 query 의 민감 키 값 가림, DSN 비밀번호 마스킹, 토큰·비밀번호를 로그·응답에 남기지 않음.
  - 운영에서만 드러나는 설정 파손 — 비밀번호 특수문자·IPv6 호스트·Alembic `%` 보간.
  - 잠금 읽기의 replica 유출 — ORM `with_for_update()` 는 writer 로, read-only 세션에서는 거부.
- **방어하지 않는다** (§2-4 비목표와 같다)
  - access 토큰의 즉시 폐기(짧은 만료 + refresh 폐기로 대신), SQLAdmin 인증, 분산 rate limit 의 정밀 창.

### 2-3. 불변식 (Invariants)
- INV-1: CI 는 락이 pyproject 와 어긋나면 실패한다(`uv sync --locked`). (검사: `tests/scripts/test_review_gate.py::test_ci_installs_with_a_lock_freshness_check`)
- INV-2: 게이트의 파일 기반 검사는 git 추적 파일만 본다. (검사: `tests/scripts/test_review_gate.py` 의 `test_repo_files_*`)
- INV-3: DSN 은 비밀번호·호스트를 그대로 왕복한다 — `make_url(...).password` 가 원래 값. (검사: `tests/core/test_dsn_urls.py`)
- INV-4: 잠금 읽기는 쓰기다 — 라우터 on 에서 writer, read-only 세션에서 거부. (검사: `tests/core/test_read_only_guard.py`, `tests/core/test_db_router.py`)
- INV-5: 범용 목록은 결정적 순서를 갖고 offset 페이지가 겹치지 않는다. (검사: `tests/core/test_list_ordering.py`)
- INV-6: 클라이언트 IP 는 신뢰 홉 밖의 헤더 값을 채택하지 않는다. (검사: `tests/core/test_client_ip_trust.py`)
- INV-7: 저장 시각은 UTC aware 로 돌아온다. naive 저장은 거부된다. (검사: `tests/core/test_utc_datetime.py`, MySQL `tests/integration/test_mysql_utc_datetime.py`)
- INV-8: Redis 가 응답하지 않으면 `/ready` 는 503 이다. (검사: `tests/test_ready.py` 의 `test_ready_returns_503_when_redis_*`, `tests/core/test_redis_provider.py`)
- INV-9: 워커 include 는 registry 가 발견한 앱에서 만들어지고, 기능을 지워도 깨지지 않는다. (검사: `tests/core/test_registry_tasks.py`, `tests/core/test_celery_app.py`)
- INV-10: 소비된 refresh 토큰의 재사용은 그 family 전체를 폐기한다. (검사: `app/features/auth/tests/test_endpoint.py::test_reused_refresh_token_revokes_the_whole_family`, `tests/core/test_refresh_store.py`)
- INV-11: 소유자도 슈퍼유저도 아닌 주체의 수정·삭제는 403, 토큰 없는 쓰기는 401. (단계 F2)

### 2-4. 비목표
- SQLAdmin 인증 백엔드(orm-raw-repository C-8 유지), OAuth 소셜 로그인, 이메일 인증·비밀번호 재설정 메일, 2FA.
- access 토큰 즉시 폐기, 다중 테넌시, 세분화된 RBAC(슈퍼유저/일반 2단계만).
- API 응답 Redis 캐시.
- 2026-10-07 리뷰 중 이 그룹 단계에 들지 않은 항목(미처리 예외 트레이스백의 SQL·`.env` 의 `ENV` 누락·풀 크기 설정·스키마 골든 위치·버전 갱신 자동화) — residual-risk 참조.

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [ ] 단계마다 새 동작의 단위 테스트가 있고, 가능한 것은 fail-on-revert 를 확인했다(run-log 에 기록).
- [ ] `ruff check .` · `ruff format --check .` · `python -m mypy .` 클린.
- [ ] `pytest -m "not mysql"` 전량 통과, skip/xfail 0. `mysql` 마커 테스트는 로컬에서 수집만 확인하고 CI 가 실행한다.
- [ ] `scripts/review_gate.py` 의 인프라·네트워크 불필요 그룹(static · structure · supply · docs) 통과.
- [ ] 불변식 구조 증거: INV-1~INV-11 각각에 실행 테스트 연결(단계 완료 시 경로를 §2-3 에 적는다).
- [ ] ledger 의 이 그룹 Fix 가 모두 Fixed.
- [ ] 질의 수준(design-baseline §0 = 보통)에 맞춘 P/D 질문 깊이 준수.

## 4. 변경 이력
- v0.1 (2026-10-12): 최초 작성. 기준선 실측(814 passed / 32 deselected / skip 0).
- v0.2 (2026-10-12): 단계 A 완료 — INV-1~INV-5 에 검사 경로를 적었다(845 passed / 32 deselected / skip 0).
- v0.4 (2026-10-12): 단계 D 완료 — INV-7 검사 경로(930 passed / 41 deselected / skip 0). alembic head `d4e6f8b12c34` → `e5a7c9d1f3b5`(ADR-020).
- v0.5 (2026-10-12): 단계 E 완료 — INV-8·INV-9 검사 경로(948 passed / 41 deselected / skip 0). 인벤토리 E 행을 실제 파일로 고쳤다(중앙 태스크 모듈 삭제, ADR-021).
- v0.6 (2026-10-12): 단계 F1 완료 — INV-10 검사 경로(1001 passed / 41 deselected / skip 0). 인벤토리 F1 행을 실제 파일로 고쳤다(옛 유틸 삭제, ADR-022).
- v0.3 (2026-10-12): 단계 B 완료 — INV-6 검사 경로(905 passed / 32 deselected / skip 0). 설정 `TRUST_PROXY_HEADERS` → `TRUSTED_PROXY_HOPS`, `ACCESS_LOG_SENSITIVE_QUERY_KEYS` 추가(ADR-019).
