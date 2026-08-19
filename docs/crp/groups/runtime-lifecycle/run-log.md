# Run Log — Runtime/Lifecycle (라운드 로그 + 수렴 판정)

> 각 라운드가 무엇을 검사했고 심각도 추세가 어떻게 변했는지. **수렴 추세가 한눈에 보여야** 한다.

## 라운드 기록

### Round 0 — 2026-08-19 (base SHA: `50cf194`) — 기준선 확립

- **트리거:** 사용자 요청 "Phase 1-R2 진행해줘". `orm-raw-repository` 그룹이 delivery
  범위에서 수렴(Round 10)한 뒤 남은 이월 결함 5건을 인수한다.
- **검수 범위:** 런타임 계층 전수 조사(lifespan · 백그라운드 · 로깅 · Celery · 발견 부작용).
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 □ 4 □ 5 □
- **기준선 실측:**
  - 수집 테스트 **621** (`pytest --collect-only -q`)
  - 라우트 인벤토리 **22 paths / 37 operations** · alembic head `d4e6f8b12c34`
  - `scripts/review_gate.py` 6그룹 전부 통과(직전 커밋 기준)
  - `app/core/resources.py` **부재**
  - `QueueHandler`/`QueueListener` **부재** — staging/production 이 `RotatingFileHandler` 를
    root 에 직접 부착(`app/utils/logs/config.py`)
  - `LOG_SQL_ECHO_ENABLED` **부재**, SQL noise filter **부재**
  - Celery `worker_process_init`/`worker_process_shutdown` 신호 **부재**
  - `app/features/home/__init__.py` 의 import-time `register_sink()` **잔존**
- **인수한 결함:** F-016 · F-017 · F-018 · F-019 · F-020 (원 번호 유지 — 번호를 새로 매기면
  두 그룹의 기록이 끊긴다).
- **신규 finding(심각도별):** CRIT 0 · HIGH 0 · MED 1 · LOW 0
  - **F-021(MED)** — `BackgroundTaskRunner.drain()` 이 timeout 후 미완료 태스크를 **경고만
    하고 버린다**. cancel 도, 재await 도, 추적 집합 비우기도 없다. 버려진 태스크는 이후
    engine dispose 와 경합한다. drain 중 새 태스크를 막는 admission 종료도, 완료 태스크의
    예외 소비도 없다. 계획서 §8 이 명시적으로 요구하는 항목인데 **이월 목록에 없었다** —
    Phase 1 검수가 "drain 이 존재한다" 까지만 보고 그 내용을 보지 않은 결과다.
- **함께 확인한 구체적 구멍(F-016 안):** `dispose_engine()` 이 writer → replica →
  background 를 순차 호출하는데 **앞의 dispose 가 예외를 내면 뒤가 실행되지 않는다.**
  "정리가 최선의 경우에만 동작" 하는 구조의 대표 사례라 F-016 의 근거로 기록했다.
- **수렴 판정:** `NOT CONVERGED` (Open Fix 6: F-016~F-021)
- **잔여 위험 변화:** 없음(Round 0).

### Round 1 — 2026-08-19 (base SHA: `50cf194`) — 구현

- **트리거:** Round 0 기준선 확립 후 사용자 승인(ADR-005 는 별도 확정 — REQ-009).
- **검수 범위:** 런타임 계층 전량 — 자원 관리자 · 백그라운드 · 로깅 · Celery · 발견 훅.
- **GATE 통과:** 0 ☑ 1 ☑ 2 ☑ 3 ☑ 4 ☑ 5 ☑
- **작업 순서는 의존 관계를 따랐다.** F-016 의 자원 관리자가 F-017 의 listener 를 소유하고
  F-018 이 F-017 위에 얹히므로, 순서를 바꿨으면 나중 것이 앞의 것을 다시 뜯었다.

- **F-016 자원 관리자** — `app/core/resources.py`. 세 가지를 고쳤다.
  1. 등록을 **start 앞에** 둔다(`acquire()`). 뒤에 두면 start 실패 시 등록 자체가 안 일어난다.
  2. 정리 하나가 실패해도 나머지를 계속한다. `dispose_engine()` 도 같은 원칙으로 바꿨다 —
     이전에는 writer dispose 가 실패하면 reader·background 가 아예 회수되지 않았다.
  3. 단일 monotonic deadline(20s)에서 배분한다. 단계 timeout 의 **합**으로 정의하면 최악의
     경우 오케스트레이터 강제 종료에 걸려 정리가 아예 안 된 상태로 죽는다.
- **F-021 drain** — `admission 종료 → 대기 → cancel → 재await → 예외 소비 → 집합 비우기`.
  이전에는 timeout 후 미완료 태스크를 경고만 하고 **버렸다**. 버린 태스크는 사라지지 않고
  곧 닫힐 엔진을 건드린다.
- **F-017 queue logging** — 파일 handler 를 root 에서 떼어 `QueueHandler` 뒤로 옮겼다.
  큐는 bounded(10,000)이고 넘치면 세고 넘어간다 — 무한 큐는 블로킹을 메모리 증가로 바꿀 뿐이다.
  **부수 발견:** uvicorn 의 log_config 가 `root` 를 재정의하면 queue handler 가 조용히 교체돼
  파일 로깅이 아무 오류 없이 멈춘다. 현재 설정에는 `root` 키가 없어 안전하며, 그 성질을
  테스트로 고정했다.
- **F-018 SQL noise filter** — `loggers` 항목이 아니라 **필터**로 구현했다. 이 저장소는
  "새 기능 추가 시 로깅 설정에 손댈 곳 0" 을 설계로 삼는데, `loggers` 를 추가하면 그 성질이
  깨진다. `LOG_SQL_ECHO_ENABLED` 는 development/test 전용이고 운영에서 켜면 기동이 실패한다.
- **F-020 발견 부작용** — `discover()` 에서 패키지 import 루프를 제거해 부작용을 0 으로 만들고,
  초기화를 `install_hooks()` → `<package>.apps.ready()` 로 옮겼다(Django `AppConfig.ready()`
  대응물). 옛 계약(`discover` 가 훅을 실행한다)을 박제하던 기존 테스트도 새 계약으로 갱신했다.
- **F-019 Celery prefork** — `worker_process_init` 에서 상속 pool 을 `Engine.dispose(close=False)`
  로 폐기한다. **`close=True` 는 자식이 부모가 쓰는 소켓을 닫아버려** 고치려던 문제를 반대
  방향으로 일으킨다. mypy 가 처음 작성한 `pool.dispose(close=False)` 를 잡아줬다 — `close` 는
  Pool 이 아니라 Engine 의 인자다.

- **의도적으로 구현하지 않은 항목 1건:** 계획서 §8 의 "개발 startup DDL 은 단일 worker 에서만"
  은 구현하지 않고 **R-105 로 이관**했다. charter 2-1 이 지원 진입점을 단일 프로세스로 선언하고
  2-2 가 다중 worker 를 비목표로 두기 때문이다. 체크리스트 정리 중 이 항목이 조치란에서 빠져
  있는 것을 발견해 명시했다 — 사양 항목을 조용히 흘려보내지 않기 위해서다.
- **신규 finding:** 0건 (Round 0 에서 식별한 F-021 포함 6건을 이 라운드에서 전부 Fixed).
- **게이트 결과:** 전체 suite **677 passed**(skip·xfail·deselect 0) · `-m mysql` 28 passed ·
  review_gate 6그룹 전부 통과 · 라우트 인벤토리 22 paths / 37 operations **불변** ·
  alembic head `d4e6f8b12c34` **불변** · ORM/Raw Base·예제 기능 경로 **diff 0**(C-1 기계 검증)
- **수렴 판정:** `CONVERGED` (Open Fix 0)
- **연쇄 효과:** `orm-raw-repository` 그룹의 이월 5건(F-016~F-020)이 Closed 로 전환되어
  **그 그룹도 Open Fix 0** 이 됐다. 두 그룹 모두 수렴 상태다.

## 심각도 추세 (수렴이 보이게)
| Round | CRIT | HIGH | MED | LOW | 신규 Fix | 판정 |
|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 0 | 1 (+ 인수 5) | NOT CONVERGED (Open Fix 6) |
| 1 | 0 | 0 | 0 | 0 | 0 (6건 전부 Fixed) | **CONVERGED** (Open Fix 0) |
