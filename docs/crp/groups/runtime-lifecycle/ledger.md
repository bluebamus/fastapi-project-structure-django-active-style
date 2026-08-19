# Ledger — Runtime/Lifecycle (결함 대장)

> ID 규칙: **F-016~F-020 은 `orm-raw-repository` 그룹에서 인수한 결함**이라 원래 번호를
> 그대로 쓴다. 번호를 새로 매기면 두 그룹의 기록이 끊겨 "언제 발견됐는지" 를 잃는다.
> 이 그룹에서 **새로 발견한** 결함은 충돌을 피해 **F-101** 부터 매긴다.

| ID | 등급 | 위반 계약 | 처리 | 상태 | 내용 | 조치 |
|---|---|---|---|---|---|---|
| F-016 | MED | REQ-002 / INV-1·INV-2 (자원 관리자) | Fix | **Fixed** | `app/core/resources.py` 부재. lifespan 이 try/finally 로 직접 정리하며 자원별 등록·역순 정리·부분 실패 내성이 없다. 확인한 구체적 구멍: `dispose_engine()` 이 writer → replica → background 를 순차 호출하는데 **앞의 dispose 가 예외를 내면 뒤가 실행되지 않는다**. | Round 1. `app/core/resources.py` 추가 — 등록 역순 정리, 부분 실패 내성, 단일 monotonic deadline(20s) 배분. `acquire()` 가 정리를 **start 앞에** 등록해 startup 실패도 회수된다. `dispose_engine()` 도 writer/reader/background 를 전부 시도하도록 바꿨다. 회귀: `tests/core/test_resources.py`(10건) — fail-on-revert 확인(내성 제거 시 2건 실패). |
| F-017 | MED | REQ-004 / INV-5·INV-6 (bounded logging queue) | Fix | **Fixed** | `QueueHandler`/`QueueListener` 미도입. `app/utils/logs/config.py` 가 staging/production 에서 `RotatingFileHandler` 를 **root 에 직접** 붙여 파일 쓰기·로테이션이 event loop 스레드를 블로킹한다. `uvicorn main:app` import 경로의 bootstrap 1회 보장도 미검증. | Round 1. `app/utils/logs/queue_logging.py` 추가 — 파일 handler 를 `QueueHandler` 뒤로 옮기고 listener 가 별도 스레드에서 파일 I/O 를 수행한다. 큐는 bounded(10,000)이며 넘치면 세고 넘어간다. bootstrap 은 `configure_logging()` 한 곳이라 두 진입점 모두 1회. 회귀: `tests/utils/test_queue_logging.py`(23건). uvicorn 설정이 root 를 재정의하지 않는지도 함께 고정 — 재정의되면 파일 로깅이 **아무 오류 없이** 멈춘다. |
| F-018 | MED | REQ-005 / INV-7·INV-8 (SQL noise filter) | Fix | **Fixed** | SQL/driver DEBUG·INFO 차단 필터와 `LOG_SQL_ECHO_ENABLED` opt-in 이 없다. Phase 1 의 `RedactingFilter` 는 알려진 키워드 마스킹이라 SQL 전문 노출을 막지 못한다. | Round 1. `SQLNoiseFilter` 추가 — SQL/드라이버 DEBUG·INFO 차단, WARNING 이상 통과. `loggers` 항목이 아니라 **필터**로 구현해 '새 기능 추가 시 로깅 설정 손댈 곳 0' 성질을 유지했다. `LOG_SQL_ECHO_ENABLED` opt-in 은 development/test 전용이며 staging/production 에서 켜면 기동 실패(이중 방어: 배포 검증 + 필터 자체 환경 확인). |
| F-019 | MED | REQ-006 / INV-10 (Celery 생명주기) | Fix | **Fixed** | `worker_process_init`/`worker_process_shutdown` 신호 처리가 없다. `app/celery/task.py` 는 프로세스당 영속 루프를 유지하지만 **fork 로 상속된 부모 pool 을 폐기하지 않는다**. 개발 startup DDL 을 단일 worker 로 제한하는 장치도 없다. | Round 1. `app/celery/worker_lifecycle.py` 추가 — `worker_process_init` 에서 상속 pool 을 `Engine.dispose(close=False)` 로 폐기(자식이 부모 소켓을 닫으면 안 된다)하고 루프를 재설정, `worker_process_shutdown` 은 멱등. prefork 만 지원을 문서에 명시(ADR-005). 회귀: `tests/core/test_celery_worker_lifecycle.py`(9건). **미이행 하위 항목:** 계획서 §8 의 "개발 startup DDL 은 단일 worker 에서만 허용" 은 구현하지 않았다 — charter 2-1 이 지원 진입점을 단일 프로세스로 선언하고 2-2 가 다중 worker 를 비목표로 두므로 R-105 로 이관했다. |
| F-020 | LOW | REQ-007 / INV-9 (발견 단계 부작용) | Fix | **Fixed** | `app/features/home/__init__.py` 의 import-time `register_sink()` 가 남아 있다. import 부작용이라 모듈을 import 하는 것만으로 sink 가 등록되고, 테스트 순서에 따라 결과가 달라질 수 있다. | Round 1. `discover()` 에서 패키지 import 루프를 제거해 **부작용 0** 으로 만들고, 초기화를 `AppRegistry.install_hooks()` → `<package>.apps.ready()` 로 옮겼다(Django `AppConfig.ready()` 대응물). `home/__init__.py` 는 docstring 만 남았다. 옛 계약을 박제하던 테스트도 새 계약으로 갱신. |
| F-021 | MED | REQ-003 / INV-3·INV-4 (background drain) | Fix | **Fixed** | `BackgroundTaskRunner.drain()` 이 timeout 후 미완료 태스크를 **경고만 하고 버린다** — cancel 도 재await 도 하지 않고 추적 집합도 비우지 않는다. 버려진 태스크는 이후 engine dispose 와 경합한다. drain 중 새 태스크가 들어오는 것을 막는 admission 종료도 없고, 완료 태스크의 예외를 아무도 소비하지 않는다. | Round 1. drain 을 `admission 종료 → 대기 → cancel → 재await → 예외 소비 → 집합 비우기` 순으로 재작성. 예외는 타입만 남긴다(C-4). 회귀: `tests/core/test_background_tasks.py`(+5). |

<!--
규칙:
- 계약 위반만 Fix. 나머지는 Accept-out-of-scope(→ residual-risk.md) 또는 Wont-fix.
- Fix 는 회귀 테스트 + fail-on-revert 검증 후에만 Status=Fixed.
- Open 인 Fix 가 0건이어야 GATE 5 Done.
- F-016~F-020 을 Closed 로 전환할 때 `orm-raw-repository/ledger.md` 의 해당 행도 함께 갱신한다
  (두 그룹이 같은 결함을 다르게 기록하면 어느 쪽이 사실인지 알 수 없다).
-->
