# Charter — Runtime/Lifecycle  (Charter v0.1 / 2026-08-19)

> 검수의 **닫힌 정의**. 여기 적힌 것이 범위와 합격 기준의 전부다.
> **상위 기준:** `design-baseline.md` 의 Active 요구사항(REQ-001~009)·불가침 제약(C-1~C-6)과
> 모순될 수 없다(모순 시 design-baseline 우선).

## 1. 인벤토리 (Scope Inventory)

| 영역/하위시스템 | 경로 | 종류 | 비고 |
|---|---|---|---|
| 자원 관리자 | `app/core/resources.py` | 소스(신규) | ADR-001 — 등록·역순 정리·부분 실패 내성 |
| 수명주기 | `main.py` (lifespan 부분) | 소스 | 자원 관리자로 이관 |
| 백그라운드 태스크 | `app/core/middlewares/background_tasks.py` | 소스 | ADR-002 — admission 종료·예외 소비·cancel |
| DB 엔진 정리 | `app/core/db/session.py` (`dispose_engine`) | 소스 | 부분 실패 내성 부여 |
| 로깅 구성 | `app/utils/logs/config.py`, `setup.py` | 소스 | ADR-003 — queue handler/listener |
| 로깅 필터 | `app/utils/logs/filters.py` | 소스 | ADR-004 — SQL noise filter |
| 설정 | `config.py`, `.env.example` | 설정 | `LOG_SQL_ECHO_ENABLED` 추가 + 환경 제한 |
| Celery 워커 | `app/celery/app.py`, `task.py` | 소스 | ADR-005 — prefork 신호 |
| 발견 부작용 | `app/features/home/__init__.py`, `app/core/registry.py` | 소스 | ADR-006 — init hook |
| 기존 테스트 | `tests/**`, `app/features/*/tests/**` | 테스트 | 기준선 **621** (감소 감시선) |
| 검증 게이트 | `scripts/review_gate.py` | 소스 | 그대로 재사용 — 이 그룹도 같은 게이트로 판정 |
| 설계·계획 | `docs/orm-raw-repository/2026-08-13/development-plan.md` §8 | 문서 | 이 그룹의 사양 원본 |

- 기준선 수집 테스트 수: **621** (`pytest --collect-only -q`, 2026-08-19)
- 기준선 commit: `50cf194` · 라우트 인벤토리 **22 paths / 37 operations**(불변)
- alembic head: `d4e6f8b12c34`(불변 — 이 그룹은 스키마를 건드리지 않는다)

## 2. 계약 (Contract)

### 2-1. 지원 구성
- 진입점 **둘 다**: `python main.py` 와 `uvicorn main:app`. 두 경로에서 로깅 bootstrap 이
  **정확히 한 번** 일어나야 한다.
- 환경: development / test / staging / production. 파일 로깅은 staging·production 에서만.
- Celery: **prefork 만**(ADR-005·REQ-009). 이 저장소의 Celery 는 태스크 1개짜리 **구조
  예시**이며, 검증 범위도 그 수준이다. Windows 로컬 개발은 `--pool=solo` 로 띄운다(Celery 는
  4.0 부터 Windows 를 공식 지원하지 않는다). solo 는 fork 를 하지 않아 상속 문제 자체가 없다.
  gevent/eventlet 은 비목표.
- DB: 단일 MySQL. 라우터 on/off 양쪽.

### 2-2. 위협 모델
- **방어한다**
  - startup 이 중간에 실패해도 이미 확보한 자원이 회수된다.
  - cleanup 하나가 예외를 내도 나머지 cleanup 이 실행된다.
  - shutdown 이 오케스트레이터의 강제 종료보다 먼저 끝난다(단일 deadline).
  - 파일 로깅이 event loop 를 블로킹하지 않는다.
  - SQL 본문·파라미터가 로그로 새지 않는다(운영에서 opt-in 자체가 불가).
  - fork 된 워커가 부모의 커넥션을 재사용하지 않는다.
- **방어하지 않는다**
  - 프로세스 강제 종료(SIGKILL)·전원 차단 시의 정리. OS 가 회수한다.
  - 로그 유실 0 보장. queue 상한 초과분은 **의도적으로 드롭**하고 카운터로 노출한다.
  - 멀티 프로세스(gunicorn 다중 worker) 간 로그 파일 경합. 파일 로깅은 프로세스별이다.

### 2-3. 불변식 (Invariants)

| ID | 불변식 | 검사 방법 |
|---|---|---|
| INV-1 | 자원 cleanup 은 **등록 역순**으로 실행되고, 하나가 예외를 내도 나머지가 전부 실행된다. | 실패 주입 fake 자원으로 순서·전량 실행 단언 |
| INV-2 | startup 실패 시에도 그 시점까지 등록된 자원이 정리된다. | 두 번째 자원 start 를 실패시키고 첫 자원 cleanup 호출 확인 |
| INV-3 | drain 은 admission 을 닫은 뒤 수행되며, 종료 후 추적 집합이 **비어 있다**. | drain 중 spawn 거부 + `active == 0` 단언 |
| INV-4 | 완료된 백그라운드 태스크의 예외는 **소비**된다("never retrieved" 경고 0). | 예외를 던지는 태스크 후 경고 캡처 0 단언 |
| INV-5 | 파일 로깅 handler 는 root 에 직접 붙지 않는다 — `QueueHandler` 를 경유한다. | dictConfig 구조 단언 |
| INV-6 | 로깅 bootstrap 은 `python main.py` 와 `uvicorn main:app` 양쪽에서 **1회**만 일어난다. | 자식 프로세스 2종에서 listener 수 단언 |
| INV-7 | SQL/driver 로거의 DEBUG·INFO 는 차단되고 WARNING 이상은 통과한다. | 필터 단위 테스트(레벨별) |
| INV-8 | `LOG_SQL_ECHO_ENABLED=true` + staging/production 조합은 **기동 실패**한다. | 배포 안전성 검증 테스트 |
| INV-9 | `discover()` 만 실행하면 metadata 와 장기 자원 수가 변하지 않는다(부작용 0). | 등록된 sink 수 before/after 단언 |
| INV-10 | Celery `worker_process_init` 이 부모 상속 pool 을 폐기하고, `shutdown` 은 **멱등**이다. | 신호 핸들러 단위 테스트(2회 호출) |
| INV-11 | shutdown 전체가 **단일 monotonic deadline**(20s) 안에서 배분된다 — 단계 timeout 의 합이 아니다. | 느린 자원 주입 후 총 소요 시간 단언 |

### 2-4. 비목표
- ORM/Raw Base·예제 기능 변경(C-1). 이 경로의 결함은 이 그룹의 결함이 아니다.
- 라우트·스키마·마이그레이션 변경(C-3).
- SQLAdmin 인증 백엔드(C-6, 영구 비목표).
- 성능 SLO·처리량 측정. 이 그룹의 계약은 **정리의 정확성**이지 속도가 아니다.
- 분산 로그 수집(ELK 등) 연동.

## 3. 인수 기준 (Acceptance Criteria) — GATE 3

- [x] `pytest` 전량 실행·통과 — **677 passed**(621 → +55), skip/xfail/deselected 0
- [x] `scripts/review_gate.py` 6그룹 전부 통과
- [x] 불변식 구조 증거: INV-1~INV-11 각각에 실행 테스트 연결
- [x] 라우트 인벤토리 **22 paths / 37 operations** 불변, alembic head `d4e6f8b12c34` 불변
- [x] ORM/Raw Base·예제 기능 경로에 **diff 0**(C-1 기계 검증)
- [x] 이월 결함 F-016~F-020 이 `orm-raw-repository` ledger 에서 **Closed** — 그 그룹도 Open Fix 0
- [x] 각 Fix 에 fail-on-revert 확인 기록
- [x] residual-risk 재평가 조건 기록 완료 (R-101~R-104)

## 4. 변경 이력
- v0.1 (2026-08-19): 최초 작성. 기준선 621 tests / commit `50cf194` 반영.
- v0.2 (2026-08-19): 2-1 에 Celery prefork 확정(REQ-009)과 Windows `--pool=solo` 안내 반영.
