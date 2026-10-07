# Design Baseline — orm-raw-repository (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-08-18 · 변경 이력:
- 2026-08-18: 최초 선택 = 보통. 사유 — `docs/specs/orm-raw-repository/` 의 요구명세·개발계획·
  워크플로 지침 3종이 이미 확정 설계 문서로 존재하여 기획(P)·설계(D) 대부분이 선행 확정됨.
  남은 질문은 Phase 경계·비가역 작업(커밋/푸시) 승인에 한정한다.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

FastAPI 워크플로우와 Django 스타일 `AppRegistry` 자동 발견·결선을 유지한 채, SQLAlchemy ORM 기반
데이터 접근과 `text()` 기반 Raw SQL 데이터 접근을 **Repository 구현만 다른 두 계층**으로 고도화한다.
DI·Service·세션 선택·트랜잭션 경계·검증·라우터 구성·문서·예외·테스트 기준은 두 방식이 동일해야 한다.
근거 문서는 `docs/specs/orm-raw-repository/` 의 requirements / development-plan / workflow-guide 3종이다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-08-13 | default-structure 저장소의 `docs/specs/orm-raw-repository/` 문서를 이 프로젝트 docs 에 같은 경로로 복사 | 설계·계획 문서 3종을 이 저장소 기준선으로 반입 | Active | 문서 3종(untracked) |
| REQ-002 | 2026-08-18 | "docs/orm-raw-repository/ 문서는 설계 및 개발계획서다. 이를 참고로 작업을 진행해줘" | 계획서 Phase 0~9 를 **독립 게이트·독립 커밋**으로 순차 실행. 이번 라운드는 Phase 0(기준선 확정, 코드 무변경)까지. | Active | ADR-001 · run-log Round 0 · ledger F-001~F-007 |
| REQ-003 | 2026-09-18 | "default, passive와 같이 active도 get_writer_db_session, get_read_only_db_session 만 사용하도록" | 기능 코드(`app/features/**`)의 세션 Dependency 를 **쓰기=`get_writer_db_session` / 읽기=`get_read_only_db_session` 둘로 고정**한다. `get_routed_db_session` 은 코어에 남기되 승인된 특수 경로 전용으로 격하한다. | Active | ADR-006 |
| REQ-004 | 2026-09-18 | "다는 제안하는 방법으로 진행하고, 차후 추가를 해야 하거나 변경을 해야 하는 상황이 있을 수 있으니 관련한 문서에 가이드를 반영해줘 라는 제안하는 방법으로 진행하고 관련한 작업에 대해 차후 추적할 수 있도록 관련한 문서에 반영해줘." | 읽기 전용 세션의 Raw SQL 판정을 **선두 단어 → 괄호 깊이 0 단어 스캔**으로 바꿔 읽기 전용 CTE(`WITH ... SELECT`) 조회를 통과시킨다. 판정을 확장·변경하는 절차를 `docs/guides/DEVELOPMENT.md` §6.5 에 가이드로 남긴다. | Active | ADR-007 |
| REQ-005 | 2026-09-21 | 신규 공개된 `anyio` 권고 3건(CVE-2026-63374 · CVE-2026-64847 · CVE-2026-63349, fix 4.14.2)을 해소 | `pip-audit` 가 다시 0 이 되도록 `anyio` 를 4.14.2 이상으로 올린다. `anyio` 는 starlette·httpx·watchfiles 를 통해 들어오는 **전이 의존**이므로 `pyproject.toml` 에는 손대지 않고 `uv.lock` 만 갱신한다. | Active | ADR-008 |
| REQ-006 | 2026-09-21 | "남은 버전 격차를 최신으로 맞춰라 — sqladmin 0.31.0 → 0.32.0. 함께 `asyncio_default_fixture_loop_scope` 를 명시하라" | 보안이 아닌 **버전 격차** 하나만 좁힌다. `uv lock --upgrade-package sqladmin` 으로 lock 만 갱신하고(`pyproject.toml` 의 `sqladmin (>=0.20.0,<1.0.0)` 은 무변경), `[tool.pytest.ini_options]` 에 `asyncio_default_fixture_loop_scope = "function"` 을 명시해 pytest-asyncio 의 향후 기본값을 지금 고정한다. 경고 정책(`filterwarnings`)은 이번 범위 밖이다. | Active | ADR-009 |
| REQ-007 | 2026-09-28 | "테스트 경고 정책을 조여서, 앞으로 오는 deprecation 이 게이트에 드러나게 하라" | `[tool.pytest.ini_options].filterwarnings` 의 블랭킷 `ignore::DeprecationWarning` · `ignore::PendingDeprecationWarning` 을 `error::` 로 바꿔 폐기 예고가 게이트를 빨갛게 만들도록 한다. `UserWarning` 은 건드리지 않고, 설치본 `fastapi.testclient` 모듈의 `StarletteDeprecationWarning` 1건은 `ignore` 를 추가하지 않고 보이는 채로 둔다. 예외를 만들기 전에 원인을 고치고, 남기는 `ignore` 에는 반드시 이유를 적는다. | Active | ADR-010 |
| REQ-008 | 2026-09-29 | "권고 없는 버전 격차도 좁혀라" | `redis`·`uvicorn` 이 5.x·0.34 에 묶여 있다. 취약점은 없으나 격차가 커질수록 나중 상향이 위험해진다. Celery 체인의 호환 천장을 먼저 확인하고 올린다 | Active | ADR-011 |
| REQ-009 | 2026-09-29 | "skip 차단이 실제로 동작하는지 확인하라" | 게이트의 조용한 SKIP 판정이 색상 코드 때문에 무력화돼 있는지 확인하고, 실제 출력 모양으로 회귀 테스트를 세운다 | Active | ADR-012 |
| REQ-010 | 2026-10-07 | ".env 의 기본값은 제거하지 말아줘. 다만 .env 가 없는 경우 예외처리로 에러가 출력되는 기능은 필요하다 … 기본값 혹은 잘못된 정보는 모두 내부의 예외처리 코드로 문제 여부가 확인되어야 한다" → "배포에서도 인증 없는 admin 이 필요한 경우가 있다" → "남은 저장소에서도 동일한 문제가 존재한다면 같은 조건의 작업을 진행해줘" | ① `.env` 가 없으면 원인을 알려 주며 멈춘다 — 파일 없이 환경 변수로 주입하는 배포는 필수 값이 모두 있으면 통과. ② 예시 값·잘못된 값은 개발 환경에서도 오류. ③ 배포 환경의 `ADMIN=true` 를 무조건 거부하던 게이트(F-006)를 **확인 플래그**로 완화 — 인증 없는 `/admin` 이 배포에서도 필요하다. ④ push 가 없는 주에도 의존성 권고를 보도록 CI 주간 실행. 코드 기본값·`.env.example` 의 기본값과 주석은 유지 | ADR-013 | Active |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-08-18 | Phase 0~9 를 순차 진행하되 각 Phase 를 독립 게이트·독립 커밋으로 분리한다. runtime/lifecycle(Phase 1) 과 ORM/Raw(Phase 3~8) 는 서로 섞지 않는다. | development-plan §10. 회귀 원인 분리와 롤백 단위 확보. | Accepted | — |
| ADR-002 | 2026-08-18 | ORM Base 와 Raw Base 는 서로 상속하지 않는다. 세션·예외·로깅 정책만 공유한다. | development-plan §1. 만능 Base 통합은 두 접근의 계약을 오염시킨다. | Accepted | — |
| ADR-003 | 2026-08-18 | 신규 기능은 `app/features/*` 규약 자동 발견으로만 결선한다. `main.py` 에 기능별 `include_router()` 를 추가하지 않는다. | development-plan §12 비목표. Django 스타일 자동배선이 이 저장소의 정체성. | Accepted | — |
| ADR-004 | 2026-08-18 | SQL 은 Repository 만 소유하고, commit 은 쓰기 View 가 성공 응답 전에 정확히 한 번 수행한다. | workflow-guide §1·§7. 트랜잭션 경계 단일화. | Accepted | — |
| ADR-005 | 2026-08-18 | SQLAdmin 에 인증 백엔드를 붙이지 않는다(**영구 비목표**). `ADMIN` 기본값 True 도 의도된 개발 편의 기본값으로 유지한다. 무인증 `/admin` 에 대한 방어선은 "인증 추가" 가 아니라 **staging/production 기동 거부(fail-fast)** 로 둔다. | 선행 확정 결정(2026-08-12, `config.py` ADMIN 필드 주석)을 그대로 승계한다. Phase 0 에서 이 결정을 모르고 F-006 을 "인증 백엔드 주입" 으로 적었다가 요구사항 회귀가 될 뻔했다. | Accepted | — |
| ADR-006 | 2026-09-18 | 기능 코드의 세션 Dependency 는 `get_writer_db_session` 과 `get_read_only_db_session` **둘뿐**이다. `get_routed_db_session` 은 정의·export 를 유지하되 기능에서 쓰지 않으며, `tests/core/test_session_dependency_names.py` 가 `app/features/**` 를 AST 로 훑어 강제한다. | 세 의존성의 본문은 세션에 표시를 심는 한 줄만 다르고, 실제 분기는 `RoutingSession.get_bind()` 가 쿼리마다 한다. 쓰기 핸들러가 routed 를 쓰면 **첫 쿼리가 SELECT 일 때 replica 로 나갔다가** 쓰기에서 writer 로 옮겨붙어, 한 요청이 두 서버를 오간다. 의도를 진입점에 선언하면 그 창이 사라지고, 읽는 사람이 라우터 내부를 몰라도 핸들러의 의도를 읽을 수 있다. 부수 효과로 `tests/test_read_path_no_commit.py` 의 검사 범위가 넓어져 catalog 쓰기 라우트와 `/ready` 가 처음 검사에 들어왔다. | Accepted | — |
| ADR-007 | 2026-09-18 | 읽기 전용 세션의 Raw SQL 판정을 **괄호 깊이 0 의 단어 스캔**(`_depth0_words`)으로 바꾼다. `words[0]` 이 `select`/`with` 이고 깊이 0 에 쓰기 키워드(`insert`·`update`·`delete`·`replace`·`merge`·`into`·`set`)가 없을 때만 통과시킨다. 따옴표 미종료·괄호 불일치는 거부로 떨어진다(fail-closed). multi-statement 거부와 `_LOCKING_READ` 검사는 그대로 둔다. SQL parser 의존성은 도입하지 않는다. | 실측 비대칭: **ORM `select(...).cte()` 는 통과하는데 같은 SQL 로 컴파일되는 `text("WITH r AS (SELECT ...) SELECT ...")` 만 차단**됐다 — 가드가 SQL 의 위험성이 아니라 파싱 못 하는 형식을 막고 있었다. 게다가 거부 메시지가 "쓰기에는 `get_writer_db_session()` 을 사용하세요" 로 끝나 **읽기를 하려던 개발자를 writer(primary) 세션으로 떠밀었다** — 복제 분산이 사라지는 잘못된 방향이다. 거부 자체의 근거(F-036 의 MySQL 8.4 실측: `WITH ... UPDATE`·`WITH ... DELETE` 는 유효한 쓰기, `WITH ... INSERT`·`REPLACE` 는 문법 오류)는 여전히 옳고, 바꾼 것은 결론이 아니라 판별 방법이다. CTE 정의는 전부 괄호 안에 있으므로 깊이 0 의 단어가 곧 최상위 구문이다. 적대적 케이스 24건(문자열 안의 키워드, `''` 이스케이프, 역따옴표 식별자, 중첩 서브쿼리, 미종료 따옴표, 괄호 불일치, multi-statement, `LOAD DATA ... INTO`)을 `tests/core/test_read_only_guard.py` 에 고정했고, `_TOP_LEVEL_WRITE` 에서 `update`·`set` 을 빼면 `WITH ... UPDATE` 케이스 2건이 실패함을 확인했다(fail-on-revert). | Accepted | residual-risk R-001 (읽기 전용 CTE 조회도 함께 막히는 잔여 위험 — 해소됨) |
| ADR-008 | 2026-09-21 | 전이 의존의 취약점은 `uv lock --upgrade-package <이름>` 으로 **lock 만** 올린다. `pyproject.toml` 에 하한 제약을 추가해 직접 의존으로 끌어올리지 않는다. 이번 `anyio` 권고 3건도 이 방식으로 4.14.0 → 4.14.2 만 갱신했다. | `anyio` 는 starlette 1.6.0 · httpx 0.28.1 · watchfiles 1.2.0 가 요구하는 전이 의존이다. 여기에 우리 하한을 적어두면 upstream 이 요구 범위를 바꿀 때 **우리 제약과 충돌**하고, 그 충돌은 해소가 급한 다음 보안 상향을 막는다. F-032 가 상향한 것들은 전부 직접 의존이었으므로 그때의 전례를 그대로 적용할 수 없다. 실측으로 `--upgrade-package anyio` 만으로 4.14.2 가 들어옴을 확인했고, lock diff 는 `anyio` 한 패키지로 한정됐다(다른 패키지 버전 변화 0). 다만 uv 가 `requires-python >= 3.13` 아래에서 해석을 갈라 `python_full_version < '3.15'` → 4.14.2, `>= '3.15'` → 4.15.1 두 갈래를 적었다 — 양쪽 모두 수정 버전 이상이라 권고는 어느 인터프리터에서도 해소된다. 재현 기준선: `uv.lock` SHA-256 `30A353A3252853ABEBBE75CB6527C81CA0FB06B70EC28946CE31E33CFCEE723D` (Round 10 의 `2CBBBFA5...` 에서 변경). | Accepted | — |
| ADR-009 | 2026-09-21 | 권고가 없는 **버전 격차**도 lock 갱신으로 좁힌다. 단 ADR-008 의 방식을 그대로 쓴다 — `uv lock --upgrade-package <이름>` 으로 lock 만 올리고, 이미 새 버전을 허용하는 `pyproject.toml` 제약은 좁히지 않는다. 더불어 pytest-asyncio 의 `asyncio_default_fixture_loop_scope` 를 `"function"` 으로 **명시**한다. | `sqladmin 0.31.0 → 0.32.0` 은 보안이 아니라 격차였고, 기존 제약 `(>=0.20.0,<1.0.0)` 이 이미 0.32.0 을 허용하므로 제약을 올릴 이유가 없다 — 하한을 올리면 ADR-008 이 지적한 upstream 충돌 위험만 늘어난다. 실측으로 lock diff 는 `sqladmin` 한 패키지(3줄)로 한정됐다. 0.32.0 이 요구하는 `starlette>=0.50,<2.0` · `sqlalchemy>=2.0` 은 현재 조합(starlette 1.6.0 · sqlalchemy 2.0.51)이 이미 만족해 연쇄 상향 0건. 이 저장소가 쓰는 `ModelView` 속성 22종(`column_list`·`column_formatters`·`can_export`·`export_types` 등)이 0.32.0 에도 전부 존재함을 실측했고, admin 전용 테스트 40건이 그대로 통과한다. `asyncio_default_fixture_loop_scope` 는 pytest-asyncio 플러그인의 `pytest_configure` 가 미지정일 때 `PytestDeprecationWarning` 을 내는 값인데, 기존 `filterwarnings = ["ignore::DeprecationWarning", ...]` 가 그 경고를 삼켜 **아무도 보지 못하는 상태**였다. 경고문이 예고한 향후 기본값을 지금 적어두면 pytest-asyncio 가 올라갈 때 픽스처 루프 범위가 조용히 바뀌는 것을 막는다. 명시 전후로 통과 수 변화 0(788 passed / 32 deselected, 경고 1건 — 둘 다 동일). 경고를 드러내는 `filterwarnings` 정책 변경은 이번 범위에서 의도적으로 제외했다. 재현 기준선: `uv.lock` SHA-256 `68BAB932EAC432667B0860C25EFEA50D4275DBF0FB9718390ED05AE95D1A271B` (ADR-008 의 `30A353A3...` 에서 변경). | Accepted | — |
| ADR-010 | 2026-09-28 | 테스트의 deprecation 정책은 **블랭킷 억제가 아니라 `error::`** 로 둔다. `filterwarnings = ["error::DeprecationWarning", "error::PendingDeprecationWarning"]`. 예외(`ignore`)는 원인을 고칠 수 없음이 실측으로 확인된 건에만, 이유 주석과 함께 붙인다. `UserWarning` 은 `error` 로 올리지 않는다. | 블랭킷 `ignore` 는 폐기 예고를 하나도 남김없이 게이트 밖으로 밀어낸다 — 실제로 ADR-009 가 다룬 pytest-asyncio 의 `PytestDeprecationWarning` 이 그렇게 삼켜져 아무도 보지 못했다. 이 커밋 전에 `-W always` 로 억제를 걷고 전체 스위트(788건)와 `-m mysql`(32건)을 실측한 결과 `DeprecationWarning`·`PendingDeprecationWarning` 은 **0건**이었으므로 예외 목록 없이 곧장 `error::` 로 전환했다(sqlite3 `datetime` 어댑터 폐기 경고도 나오지 않아 `conftest.py` 의 어댑터 등록은 불필요했다). `error::` 가 실제로 무는지는 `DeprecationWarning` 을 내는 임시 테스트로 확인했다(`E DeprecationWarning: probe` 로 실패 → 파일 삭제). `UserWarning` 을 `error` 로 올리지 않는 이유는 `starlette.exceptions` 의 `StarletteDeprecationWarning` 이 `UserWarning` 을 상속하기 때문이다 — 켜는 순간 서드파티 경고 하나가 빌드 전체를 인질로 잡는다. 남아 있는 `fastapi.testclient` 의 ``Using `httpx` with `starlette.testclient` is deprecated`` 1건은 `ignore` 로 덮지 않고 보이는 채로 둔다(`httpx2` 전환은 별건). 전후로 통과 수 변화 0: 788 passed / 32 deselected / skip 0 / 경고 1건, `-m mysql` 32 passed. | Accepted | — |
| ADR-011 | 2026-09-29 | `redis` 를 5.3.1 → **6.4.0**, `uvicorn[standard]` 를 0.34.3 → **0.54.0** 으로 올린다. 둘 다 직접 의존이므로 ADR-008 의 lock-only 방식이 아니라 `pyproject.toml` 제약을 함께 옮긴다. 단 `redis` 상한은 `<7.0.0` 으로 적고 **`<6.5` 는 적지 않는다**. | 권고는 이번에 0건이다 — 순수 버전 격차 해소다. redis 최신은 8.1.0 이지만 `kombu[redis]` 가 `redis!=4.5.5,!=5.0.2,<6.5,>=4.5.2` 를 요구해 Celery 를 쓰는 한 해석 천장이 **6.4.0** 이다. 그 `<6.5` 를 우리 쪽에 베끼지 않는 이유는 ADR-008 과 같다 — 남의 제약을 복제하면 upstream 이 범위를 바꿀 때 우리가 따라 움직이지 않아 충돌한다. 천장은 resolver 에 맡기고 우리는 "redis-py 6.x 로 동작한다" 만 선언한다. uvicorn 은 0.x 에서 마이너 20개를 건너뛰므로 추정하지 않고 실측했다. lock 에서 움직인 패키지는 이 둘뿐이고, 게이트 6그룹(static·tests·structure·supply·docs·deps) 전부 통과 — 통과 수 변화 0. | Accepted | — |
| ADR-012 | 2026-09-29 | `judge_pytest_summary()` 는 판정 **전에 ANSI 색상 코드를 걷어낸다.** 회귀 테스트는 평문이 아니라 색상이 섞인 **실제 출력 모양**으로 시험한다. | 이 판정은 조용한 SKIP 을 막으려고 둔 것인데, **실전에서 한 번도 동작한 적이 없었다.** pytest 는 파이프로 캡처해도 요약에 색상을 섞어 `3 skipped` 앞 글자가 `m`(단어 문자)이 되고, 그러면 정규식의 단어 경계가 성립하지 않아 항상 빈 목록을 돌려준다. 실측으로 확인했다: 색상이 섞인 실제 요약을 넣으면 `[]`, 같은 내용을 평문으로 넣으면 1건. 기존 테스트가 전부 평문 요약이라 **판정이 죽어 있는데도 초록이었다** — 테스트가 지키려던 것을 지키지 못한 전형이다. 그래서 고침과 함께 색상 케이스를 회귀 테스트로 박았고, ANSI 제거를 무력화하는 변이에서 2건이 죽는 것을 확인했다(55 passed → 2 failed). 오탐 방향도 함께 지킨다: 색상이 섞인 깨끗한 요약과 `0 skipped` 는 통과여야 한다. | Accepted | — |
| ADR-013 | 2026-10-07 | ① `validate_env_source()` 신설: `ENV != test` 이고 `.env` 가 없으면 `REQUIRED_WITHOUT_ENV_FILE`(`ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE`)이 환경 변수에 모두 있어야 한다. ② `validate_deployment_safety()` 의 비밀값 검사(placeholder 키·같은 JWT 키·예시 비밀번호)를 test 외 **모든 ENV** 로 넓히고 비밀 키 32자 미만을 더한다. DEBUG·CORS `*`·SQL echo·`LOG_LEVEL=DEBUG` 는 staging/production 그대로. ③ `AppSettings.ADMIN_ALLOW_UNAUTHENTICATED: bool = False` 신설 — staging/production 의 `ADMIN=true` 는 이 확인이 있으면 기동하고(`main.py` 가 매 기동 WARNING), 없으면 위반. ④ CI 워크플로 `env: ENV: test` 와 주 1회 `schedule` | ① 코드 기본값을 지우지 않으면서 기본값만으로 뜨는 경로를 닫는다. 컨테이너는 비밀값을 환경 변수로 받는 편이 안전하므로 파일을 강제하지 않는다. `ENV` 를 필수 목록에 넣어, 파일 없는 배포에서 `ENV` 누락으로 게이트가 꺼지는 경로도 닫힌다. ② 사용자 원칙 "잘못된 설정은 오류로 인지해 고친다". 테스트 스텁의 짧은 키는 32자 이상으로 올렸다. ③ F-006 의 "배포 환경에서 무인증 Admin 기동 금지" 를 사용자 요구(배포에서도 무인증 admin 이 필요할 수 있음)로 재정의한다 — 실수(기본값 그대로)와 의도를 가른다. 조용히 마운트를 생략하는 대안은 설정과 동작이 어긋나고, IP 허용 목록은 프록시 헤더 신뢰 문제로 우회된다. ④ 게이트가 `config` 를 import 하므로 `.env` 없는 CI 는 ENV=test 여야 한다. 사용자 승인 (2026-10-07) | Accepted | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: `main.py` 에 기능별 `include_router()`/중앙 router·Admin 목록을 추가하지 않는다 — ADR-003 에서 비롯.
- C-2: SQL 실행은 Repository 계층만 수행한다. View/Service 는 SQL 을 갖지 않고, Repository/Dependency 는 commit 하지 않는다 — ADR-004 에서 비롯.
- C-3: 기존 271 tests 와 18 paths / 30 operations 골든 인벤토리는 보존한다. 기존 자동배선 테스트를 삭제하거나 느슨하게 만들지 않는다 — REQ-002 에서 비롯.
- C-4: 전체 suite 의 skip / xfail / deselected 는 0 이다. MySQL marker 가 전부 skip 된 초록 결과는 실패로 처리한다 — development-plan §10.
- C-5: SQL / driver / ORM / commit / Alembic 로그와 오류 응답에 sentinel secret, SQL 원문, params, DSN 이 노출되지 않는다 — development-plan §13.
- C-6: 사용자 입력을 Raw SQL 문자열에 보간하지 않는다. 바인딩 파라미터만 사용한다 — workflow-guide §6.
- C-7: ORM Base 와 Raw Base 는 상속 관계를 갖지 않는다 — ADR-002 에서 비롯.
- C-8: SQLAdmin 에 인증 백엔드를 추가하지 않는다. `ADMIN` 기본값을 "보안 기본값" 명목으로 False 로 되돌리지 않는다. staging/production 에서 `ADMIN=true` 는 `ADMIN_ALLOW_UNAUTHENTICATED=true` 확인이 있어야 기동한다(ADR-013, 2026-10-07 — 그 전에는 무조건 거부였다) — ADR-005 에서 비롯.
- C-9: 기능 패키지 `__init__.py` 는 라우터·모델·DB 모듈을 import 하지 않는다(초기화 훅 제외). 발견과 결선을 분리한 상태를 유지한다 — Phase 1 에서 비롯.

## 5. 변경 이력
- v0.1 (2026-08-18): 최초 작성. REQ-001/002, ADR-001~004, C-1~C-7 확정. Phase 0 기준선과 연결.
- v0.2 (2026-08-18): Phase 1 수행 중 선행 확정 결정(2026-08-12 Admin 인증 영구 비목표)을 발견해 ADR-005·C-8 로 승계. 패키지 init 경량화 계약을 C-9 로 고정.
- v0.3 (2026-09-18): REQ-003 · ADR-006 등록 — 기능 코드의 세션 Dependency 를 writer/read-only 둘로 고정하고 AST 회귀 테스트로 강제.
- v0.4 (2026-09-18): REQ-004 · ADR-007 등록 — 읽기 전용 Raw SQL 판정을 괄호 깊이 0 단어 스캔으로 교체해 읽기 전용 CTE 를 허용하고, residual-risk R-001 을 supersede 했다. 판정 확장·변경 가이드를 `docs/guides/DEVELOPMENT.md` §6.5 에 추가.
- v0.5 (2026-09-21): REQ-005 · ADR-008 등록 — 신규 `anyio` 권고 3건을 `uv lock --upgrade-package anyio` 로만 해소(4.14.0 → 4.14.2, `pyproject.toml` 무변경). 전이 의존 취약점의 처리 방식을 ADR 로 고정하고 새 lock 해시를 기록.
- v0.6 (2026-09-21): REQ-006 · ADR-009 등록 — 권고 없는 버전 격차 `sqladmin 0.31.0 → 0.32.0` 을 lock 만 갱신해 좁히고(연쇄 상향 0건), `asyncio_default_fixture_loop_scope = "function"` 을 명시해 pytest-asyncio 의 향후 기본값을 고정. 새 lock 해시 기록.
- v0.7 (2026-09-28): REQ-007 · ADR-010 등록 — 테스트 `filterwarnings` 를 블랭킷 `ignore::` 에서 `error::DeprecationWarning`·`error::PendingDeprecationWarning` 으로 전환. `-W always` 실측에서 deprecation 0건이라 예외 목록 없이 전환했고, `UserWarning` 과 `StarletteDeprecationWarning` 1건은 손대지 않았다. 통과 수 변화 0(788 + 32).
- v0.8 (2026-09-29): REQ-008 · ADR-011 등록 — `redis 5.3.1 → 6.4.0`(천장은 `kombu[redis]` 의 `<6.5`), `uvicorn 0.34.3 → 0.54.0`. 권고 0건 상태의 격차 해소이며 lock 에서 움직인 패키지는 둘뿐이다. 부수: 닫지 않던 파일 핸들 1건을 `Path.read_text()` 로 바꿔 `ResourceWarning` 을 없앴다(실측 1 → 0).
- v0.9 (2026-09-29): REQ-009 · ADR-012 등록 — `judge_pytest_summary()` 가 ANSI 색상 코드 때문에 실전에서 아무것도 잡지 못하던 것을 고쳤다. 색상이 섞인 실제 출력 모양으로 회귀 테스트 3건을 추가했고 변이 검증(2 failed)으로 확인했다.
- v0.10 (2026-10-07): REQ-010 · ADR-013 등록 — 설정 검사 확장(`.env` 출처, 개발 환경 예시 비밀값·짧은 키), 배포 환경 `ADMIN=true` 를 확인 플래그로 완화(C-8 갱신), CI 주간 실행.
