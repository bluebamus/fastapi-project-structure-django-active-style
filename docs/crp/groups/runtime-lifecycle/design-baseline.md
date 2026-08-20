# Design Baseline — Runtime/Lifecycle (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-08-19 · 변경 이력: (없음)

근거: 앞선 `orm-raw-repository` 그룹과 같은 수준이다. 설계·계획서가 이미 존재하고
(`docs/orm-raw-repository/2026-08-13/development-plan.md` §8), 이 그룹은 그 문서가 명시한
항목을 이행하는 작업이라 "무엇을 만들지" 는 이미 확정돼 있다. 질문이 필요한 지점은
**어떻게** 에 한정된다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

FastAPI 애플리케이션의 **수명주기·백그라운드·로깅·Celery 워커** 계층을 하드닝한다.
`orm-raw-repository` 그룹이 데이터 접근 계층(ORM/Raw)을 다루는 동안, 계획서 §8 은
런타임 계층을 **의도적으로 분리해** 남겨 두었다 — 두 변경을 섞으면 회귀가 났을 때
원인이 데이터 계층인지 런타임인지 가릴 수 없기 때문이다.

그 결과 ORM/Raw 그룹은 delivery 범위에서 수렴했지만(2026-08-19, Round 10), 이월된
결함 5건(F-016~F-020)이 남았다. 이 그룹은 **그 5건을 인수해** 닫는 것이 존재 이유다.

핵심 문제는 하나로 요약된다: **정리(cleanup)가 최선의 경우에만 동작한다.**
startup 이 중간에 실패하거나, cleanup 하나가 예외를 내거나, 워커 프로세스가 fork
되면 자원이 조용히 샌다. 새는 것은 커넥션·태스크·이벤트 루프이고, 증상은 항상
한참 뒤에 "재시작이 느려짐"·"커넥션 소진"·"Event loop is closed" 로 나타난다.

## 2. 요구사항 레지스터 (append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-19 | "Phase 1-R2 진행해줘" | `orm-raw-repository` 에서 이월된 F-016~F-020 을 인수해 런타임/수명주기 계층을 하드닝한다. 계획서 §8 이 사양이다. | Active | INV-1~INV-9 / F-101~ / Round 1 |
| REQ-002 | 2026-08-19 | (REQ-001 에서 도출) 계획서 §8 "자원 관리자" | startup 실패와 정상 shutdown 의 cleanup 을 한 곳에서 통합한다. fallible start 뒤에 cleanup 을 등록하지 않고, **start 전에 등록한 멱등 cleanup** 또는 자원별 context manager 를 쓴다. | Active | ADR-001 / INV-1 |
| REQ-003 | 2026-08-19 | (도출) 계획서 §8 "background task" | admission 을 닫고 → done 예외를 소비하고 → timeout 후 cancel 하고 → done/pending 모두 await 한 뒤 → 추적 집합을 비운다. | Active | ADR-002 / INV-2 |
| REQ-004 | 2026-08-19 | (도출) 계획서 §8 "bounded logging queue" | 파일 logging I/O 를 event loop **밖에서** 실행한다. `uvicorn main:app` import 경로에서도 bootstrap 이 한 번만 일어난다. | Active | ADR-003 / INV-3 |
| REQ-005 | 2026-08-19 | (도출) 계획서 §8 "SQL noise filter" | queue handler 에 SQL/driver DEBUG·INFO 차단 필터를 붙이되 WARNING 이상은 유지한다. `LOG_SQL_ECHO_ENABLED` opt-in 은 development/test 에서만 허용한다. | Active | ADR-004 / INV-4 |
| REQ-006 | 2026-08-19 | (도출) 계획서 §8 "Celery 생명주기" | prefork 만 지원 대상으로 선언한다. `worker_process_init` 에서 부모로부터 상속된 pool 을 폐기하고 child engine/loop 로 재바인딩하며, `worker_process_shutdown` 에서 멱등 정리한다. | Active | ADR-005 / INV-5 |
| REQ-007 | 2026-08-19 | (도출) 계획서 §8 + C-9 | `home/__init__.py` 의 import-time `register_sink()` 를 제거하거나 명시적 멱등 init hook 으로 옮긴다. `discover()` 만 실행했을 때 장기 자원 수가 변하지 않아야 한다. | Active | ADR-006 / INV-6 |
| REQ-008 | 2026-08-19 | (도출) 계획서 §8 마지막 문단 | 이 작업은 ORM/Raw Base 및 예제 기능 변경과 **섞지 않는다**. 기존 621 tests 를 유지한 채 독립 커밋한다. | Active | charter §2 비목표 |
| REQ-009 | 2026-08-19 | "A. prefork만 지원, 구조 예시 수준으로 문서화해줘" | Celery 지원 pool 을 **prefork 하나로 확정**한다. 다만 이 저장소의 Celery 는 태스크 1개짜리 **구조 예시**이므로, 문서는 "운영 검증을 마쳤다" 가 아니라 "예제 수준에서 prefork 만 검증했다" 로 쓴다. Windows 로컬은 `--pool=solo` 를 안내한다. | Active | ADR-005 / R-101 |
| REQ-010 | 2026-08-20 | "처음 개발 단계에서는 create_db_tables 를 사용하고 차후 alembic 을 쓰는 걸 강제하고 싶다. 하지만 처음부터 alembic 을 쓰고자 하는 사람이 있을 수 있기에 문서에 이에 대한 설명을 리드미에 추가하고 main 의 app() 코드의 라인에 주석으로도 추가해줘" | startup DDL 을 **유지**하고 전환 정책을 문서로 세운다. R-105 의 해법이던 "startup DDL 제거" 를 기각하는 결정이다. 전환 시점은 잃으면 안 되는 데이터가 처음 들어온 시점. 처음부터 Alembic 을 쓰는 경로는 코드 변경 없이 열려 있어야 한다(`create_all` checkfirst → no-op). 안내는 README 와 호출 지점 주석 **양쪽**에 둔다. | Active | R-105(Accept) / Round 2 |

## 3. 설계 결정 기록 (ADR)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-19 | `app/core/resources.py` 에 **자원 관리자**를 둔다. 자원은 `(이름, 정리 코루틴)` 으로 **start 이전에** 등록하고, 관리자는 역순으로 정리하되 **하나가 실패해도 나머지를 계속** 실행한다. | 현재 `dispose_engine()` 은 writer → replica → background 를 순차 호출하는데, 앞의 dispose 가 예외를 내면 뒤가 실행되지 않는다. "정리가 최선의 경우에만 동작" 하는 구조다. 또 fallible start 뒤에 cleanup 을 등록하면 start 실패 시 등록 자체가 일어나지 않는다. | Accepted | — |
| ADR-002 | 2026-08-19 | `BackgroundTaskRunner` 에 **admission 종료(closed 플래그)** 를 추가하고, drain 은 `done 예외 소비 → timeout → cancel → 재await → 집합 비우기` 순으로 한다. | 현재 drain 은 timeout 후 미완료 태스크를 **경고만 하고 버린다**. 버려진 태스크는 이후 engine dispose 와 경합하고, 예외를 아무도 읽지 않아 "Task exception was never retrieved" 로만 남는다. drain 중 새 태스크가 들어오면 종료가 끝나지 않는다. | Accepted | — |
| ADR-003 | 2026-08-19 | 파일 handler 를 `QueueHandler` 뒤로 옮기고 `QueueListener` 가 **별도 스레드**에서 실제 파일 I/O 를 수행한다. queue 는 **bounded**(maxsize 유한)이며 가득 차면 **드롭하고 카운터를 올린다**. | 현재 production/staging 은 `RotatingFileHandler` 를 root 에 직접 붙인다. 파일 쓰기와 로테이션이 event loop 스레드를 블로킹한다. 무한 queue 로 바꾸면 블로킹 대신 **메모리 증가**로 문제가 옮겨갈 뿐이라 상한을 둔다. | Accepted | — |
| ADR-004 | 2026-08-19 | SQL/driver 로거의 DEBUG·INFO 를 **기본 차단**하고 WARNING 이상은 통과시킨다. `LOG_SQL_ECHO_ENABLED=true` 는 development/test 에서만 유효하며, staging/production 에서 켜면 **기동을 실패**시킨다. | SQL 본문에는 파라미터가 그대로 들어간다. Phase 1 의 `RedactingFilter` 는 알려진 키워드만 마스킹하므로 SQL 전문 노출을 막지 못한다. opt-in 을 환경으로 제한하지 않으면 "잠깐 켜둔" 설정이 운영에 남는다. | Accepted | — |
| ADR-005 | 2026-08-19 | Celery 는 **prefork 만** 지원 대상으로 선언한다(사용자 확정, REQ-009). `worker_process_init` 에서 부모 상속 pool 을 폐기하고 child loop/engine 을 만들며, `worker_process_shutdown` 에서 멱등 정리한다. 문서는 **구조 예시 수준**임을 명시하고 Windows 로컬은 `--pool=solo` 를 안내한다. | fork 로 상속된 커넥션은 부모·자식이 같은 소켓을 공유해 MySQL 패킷 순서가 뒤엉킨다(`Commands out of sync`). 그런데 이건 **동시 실행이 겹쳐야 재현**되므로 개발에서는 멀쩡하고 운영에서 처음 터진다. gevent/eventlet 은 그린스레드 모델이라 `run_async()` 의 asyncio 루프와 동시성 모델이 충돌하고, 제대로 쓰려면 태스크를 동기 드라이버로 다시 써야 한다 — 이 저장소에 그 요구가 없다. 지원 범위를 좁히고 **문서에 명시**하는 편이 정직하다. | Accepted | — |
| ADR-006 | 2026-08-19 | `home/__init__.py` 의 import-time `register_sink()` 를 제거하고, registry 가 호출하는 **명시적 init hook** 으로 옮긴다. | import 부작용은 "무엇을 import 하면 무엇이 일어나는가" 를 추적 불가능하게 만든다. 테스트가 모듈을 import 하는 것만으로 sink 가 등록되면, 테스트 순서에 따라 결과가 달라진다. | Accepted | — |
| ADR-007 | 2026-08-19 | 단계별 timeout 은 **단일 monotonic deadline** 에서 배분한다(전체 20초: task 5s, DB dispose 10s, logging 5s, cleanup 예비). 각 단계 timeout 의 **합**으로 전체 예산을 정의하지 않는다. | 단계 timeout 을 각각 두면 최악의 경우 합이 전체 예산을 넘어 오케스트레이터의 강제 종료(SIGKILL)에 걸린다. 그러면 정리가 아예 안 된 상태로 죽는다. | Accepted | — |

## 4. 불가침 제약 (이 그룹에서 절대 깨지 않는 것)

| ID | 제약 | 근거 |
|---|---|---|
| C-1 | ORM/Raw Base(`app/core/repositories/**`)와 예제 기능(`catalog`, `reports`)을 **변경하지 않는다**. | 계획서 §8 이 명시적으로 분리를 요구한다. 섞으면 회귀 원인을 가릴 수 없다. |
| C-2 | 기존 621 tests 는 전부 유지된다. 삭제·비활성화로 수를 줄이지 않는다. | MIG-001 의 감소 감시선. |
| C-3 | 공개 라우트 인벤토리 **22 paths / 37 operations** 를 바꾸지 않는다. | 런타임 하드닝은 공개 API 계약과 무관하다. |
| C-4 | 로그·응답에 SQL 본문·파라미터·드라이버 원문을 남기지 않는다. | ORM/Raw 그룹의 C-5 를 승계한다. |
| C-5 | `AppRegistry` 의 `discover()` 는 **부작용이 없어야** 한다 — 실행해도 metadata 와 장기 자원 수가 변하지 않는다. | 계획서 §5, ORM/Raw 그룹 C-9 승계. |
| C-6 | SQLAdmin 인증 백엔드는 **영구 비목표**(2026-08-12 결정). 방어선은 staging/production fail-fast 다. | ORM/Raw 그룹 ADR-005 승계. 이 그룹에서 뒤집지 않는다. |

## 5. 변경 이력
- v0.1 (2026-08-19): 최초 작성. REQ-001~008, ADR-001~007, C-1~C-6 확립.
- v0.2 (2026-08-19): REQ-009 추가 — 사용자가 Celery 지원 pool 을 prefork 하나로 확정하고
  문서 톤을 "구조 예시 수준" 으로 낮추도록 결정. ADR-005·R-101 에 반영.
