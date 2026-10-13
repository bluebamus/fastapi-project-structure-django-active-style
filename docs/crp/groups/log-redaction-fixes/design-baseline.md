# Design Baseline — log-redaction-fixes (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준(authoritative baseline)**. charter(코드 계약)와 달리
> 이 문서는 *"사용자가 무엇을, 왜 요구했는가"* 의 영속 기록이다. **모든 추가 작업은 여기 기록된
> Active 요구사항과 불가침 제약을 위반하지 않아야 한다**(요구사항 회귀 방지). 새 요청이 올 때마다
> §2 에 append 하고, 설계 결정은 §3 에 ADR 로 고정한다. append-only — 항목은 지우지 않고
> 상태(Active/Superseded)만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)** — 핵심 갈림길(목적·범위·비가역·계약)만 질문, 자명한 건 기본값 + 한 줄 고지.
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-13 · 변경 이력:
- 2026-10-13: 최초 선택 = 보통. 사유 — 요청과 명세(감독자 작성)가 항목·테스트·문서 범위를 정했고 사용자가
  접속 로그 원문 저장 유지·커버리지 하한 0 을 직접 결정했다. 남은 갈림길(마스킹 단계 선택)은 ADR-002 로 고지.

> 안전 하한선: 어느 수준도 파괴적·외부영향·계약변경 STOP 은 못 건너뛴다.

## 1. 목적 / 배경

리뷰가 권장한 항목을 고친다. ① `RedactingFilter` 가 `exc_info` 의 traceback 을 보지 않아(필터 주석에 ceiling 으로
적혀 있던 구멍, orm-raw-repository R-007) `logger.exception(...)` 의 DSN·비밀번호가 콘솔·uvicorn 로그에 그대로 찍혔고,
`Authorization: Bearer …` 는 메시지에서도 가려지지 않았다. ② 전역 `StarletteHTTPException` 핸들러가 `exc.headers` 를
버려 405 에 `Allow` 가 없었다. ③ Redis 요구 버전이 어디에도 근거와 함께 적혀 있지 않고 기동 시 확인도 없었다.
④(추가 요청) 커버리지 하한이 주석 처리된 80 으로만 남아 있고 CI 는 커버리지를 재지 않았다.
접속 로그의 원문 저장은 사용자 결정으로 그대로 둔다.

## 2. 요구사항 레지스터 (요청 히스토리 — append-only)

| Req-ID | 날짜 | 요청(원문 요약) | 도출된 요구사항 | 상태 | 연결 |
|---|---|---|---|---|---|
| REQ-001 | 2026-10-13 | "권장 하는 항목에 대해 수정해줘. … 접속 로그가 session_id 쿠키, Referer, XFF 헤더를 원문 그대로 저장하는 로그는 그대로 유지해줘. … 405 응답에 allow 헤더를 넘겨주는 것으로 수정해줘. … redis도 적절하게 다시 정의해줘." (원칙 유지: 같은 목적은 하나의 모듈 클래스, 조합은 주입, 모든 단계 단위 테스트·fail-on-revert) | ① traceback·체인·stack_info 마스킹(모든 핸들러 경로, 규칙 정본 하나) ② 접속 로그 원문 저장 유지 기록 ③ HTTP 예외 헤더 보존 ④ Redis 최소 버전을 명령에서 도출·기동 시 확인·문서 일치 ⑤ 엔드포인트 보호 현황 조사(보고만) ⑥ 모든 문서 반영 | Active | ADR-001~ADR-006 |
| REQ-002 | 2026-10-13 | "0%로 정의해줘. 기본 설정은 0%이며 차후 사용자가 필요한 수준만큼 설정하는 것으로 정의하고 싶다. 최초는 다른 기능들이 제대로 동작하는지 여부 확인이 중요하다." | ① `fail_under = 0` 명시(정본 한 곳) ② CI·게이트는 측정·출력만, `--cov-fail-under` 금지 ③ 계약 테스트 ④ 문서·올리는 법 | Active | ADR-007 |

## 3. 설계 결정 기록 (ADR — 확정 후 불변)

| ADR-ID | 날짜 | 결정 | 근거 | 상태 | supersedes |
|---|---|---|---|---|---|
| ADR-001 | 2026-10-13 | `fix/log-redaction` 브랜치(main `179bfe1` 기준)에서 진행한다. 변경마다 단위 테스트와 fail-on-revert 를 확인하고 검사(ruff·mypy·`pytest -m "not mysql"` skip 0·게이트 structure/supply/docs)를 통과시킨 뒤 단계별로 커밋한다. 병합·푸시는 감독자가 한다. | 사용자 규칙(피처 브랜치·PR 없음). | Active | — |
| ADR-002 | 2026-10-13 | **traceback 마스킹은 필터 단계에서 한다.** `RedactingFilter.filter` 가 `exc_info` 를 `logging.Formatter().formatException` 으로 미리 렌더해 `exc_text` 에 고정한 뒤 `redact()` 를 통과시키고, `stack_info` 도 같은 함수로 가린다. `logging.Formatter.format` 은 `exc_text` 가 있으면 다시 만들지 않으므로 어떤 포매터든 가린 본문을 찍는다. 규칙은 `redact()` 하나에 `Bearer <토큰>` 정규식을 더했다(정본 유지). 우리 dictConfig 밖에서 생기는 핸들러에는 같은 필터를 단다 — `redact_handlers()`(멱등)를 `configure_logging()` 이 uvicorn 로거 3개에, Celery `after_setup_logger`·`after_setup_task_logger` 수신자가 워커 로거에 부른다. | 포매터 단계(`TzFormatter.formatException` 오버라이드)는 마스킹 책임을 필터·포매터 두 클래스로 쪼개고, 포매터가 우리 것이 아닌 경로(uvicorn CLI 의 `DefaultFormatter`, Celery 포매터, queue 의 기본 포매터)를 덮지 못한다. 필터는 이미 모든 핸들러에 걸려 있는 한 지점이다(같은 목적은 한 클래스). 재현: 수정 전 console·uvicorn 에서 DSN·`password=`·Bearer 가 그대로, 파일 경로는 `QueueHandler.prepare` 가 traceback 을 메시지에 접어 넣어 DSN·`password=` 는 가려졌지만 Bearer 는 노출. uvicorn CLI 는 앱 import **전에** 자기 핸들러(propagate=False)를 세우고, Celery 워커는 root 를 가로채므로 둘 다 우리 필터를 거치지 않았다. SQLAlchemy 등 나머지 서드파티 로거는 root 로 전파돼 이미 덮인다. DEBUG 500 응답에 `str(exc)` 를 싣는 경로는 없음을 확인했다(`general_exception_handler` 는 고정 메시지·`detail=null`, `tests/test_exception_handler_leak.py`). | Active | — |
| ADR-003 | 2026-10-13 | **접속 로그의 `session_id` 쿠키·Referer·X-Forwarded-For 원문 저장은 사용자 결정으로 유지한다.** 코드·테스트를 바꾸지 않는다. | 사용자 결정(REQ-001 원문). 로그 마스킹(ADR-002)은 애플리케이션 로그 파이프라인 대상이고 접속 로그 테이블은 별개다. 수용 위험은 residual-risk R-401. | Active | — |
| ADR-004 | 2026-10-13 | 전역 `StarletteHTTPException` 핸들러(FastAPI `HTTPException` 도 이 핸들러로 온다)는 본문을 `ErrorResponse` 로 바꾸되 `headers=exc.headers` 를 그대로 싣는다. `AppException` 핸들러는 이미 `exc.headers` 를 싣고 있었고, `RequestValidationError`·일반 `Exception` 핸들러는 실어 올 헤더가 없다. | Starlette 라우터는 405 를 `HTTPException(405, headers={"Allow": …})` 로 던진다 — 핸들러가 헤더를 버려 RFC 9110 의 `Allow` 필수 조항을 어겼다. 같은 경로로 401 `WWW-Authenticate`·429 `Retry-After` 도 보존된다. | Active | — |
| ADR-005 | 2026-10-13 | **Redis 최소 버전은 코드가 보내는 명령의 도입 버전 최댓값 = 7.0** 이다(`EXPIRE … NX` 7.0 > `GETDEL` 6.2 > `SET … EX` 2.6.12 > `INCR`·`TTL`·`SADD`·`SMEMBERS`·`DEL`). 상수 `REDIS_MIN_VERSION = (7, 0)` 과 명령→버전 표를 `app/core/redis.py`(Redis provider 모듈)에 두고, `check_redis_version()` 을 lifespan 의 Redis `ping()` 직후(`resources.start_redis`) 부른다. 미만이면 `RedisVersionError` 로 기동을 멈춘다. `INFO` 가 `ResponseError`(권한 거부·명령 이름 변경)면 WARNING 후 계속, `redis_version` 을 읽지 못해도 WARNING 후 계속, 연결 오류 등은 그대로 올린다. | 낮은 Redis 에서는 기동이 되고 첫 로그인 rate limit 이 `ResponseError` 로 500 이 된다 — Redis 필수 정책(service-hardening ADR-008)과 같은 무게로 기동에서 막는다. 관리형 Redis 의 INFO 차단은 버전 문제가 아니므로 막지 않는다. fakeredis(2.39)는 INFO 를 지원하지 않아(`unknown command 'info'`) 테스트·스모크는 경고 경로를 탄다 — 기존 lifespan 테스트의 가짜 클라이언트에 `info()` 를 더했다. 계약 테스트가 소스의 `expire(…, nx=True)`·`getdel(` 과 상수를 대조한다. 문서의 "Redis 7.4" 는 compose 고정 이미지의 사실이라 유지하고 "최소 7.0" 근거를 함께 적었다. | Active | — |
| ADR-006 | 2026-10-13 | 명세 §5(엔드포인트 보호 현황)는 **읽기 전용 조사**로, 결과는 감독자 보고에만 싣고 코드는 바꾸지 않는다. 조사로 드러난 구조적 한계(기본 거부 없음)는 residual-risk R-406 으로 남긴다. | 명세. 판단은 사용자 몫이다. | Active | — |
| ADR-007 | 2026-10-13 | **커버리지 하한 기본값은 0(사용자 결정)이고 정본은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나다.** CI 단위 단계와 `tests` 게이트는 `--cov=app --cov-config=pyproject.toml --cov-report=term-missing` 으로 측정·출력만 하고 `--cov-fail-under` 를 두지 않는다. `term-missing:skip-covered` 는 쓰지 않는다. `--cov-config` 를 명시한다. | 사용자 결정(REQ-002) — 처음에는 기능 동작 확인이 우선. 값이 두 곳에 있으면 어긋난다. `--cov-config` 가 없으면 pytest-cov 6.3 이 서브프로세스에 설정 경로를 넘기지 않아(`.coveragerc` 부재 → `os.pathsep`) 자식이 branch 없는 기본 설정으로 측정하고, 합치기가 `Can't combine statement coverage data with branch data` INTERNALERROR 로 끝났다(실측, 서브프로세스 테스트 다수). skip-covered 요약 줄("N files skipped …")은 SKIP 판정과 같은 단어를 쓴다. 이 저장소에는 85% 를 고정하던 테스트·ADR 이 없다(주석 처리된 `# fail_under = 80` 뿐) — Superseded 대상 없음. | Active | — |

## 4. 불가침 제약 (INVARIANT REQUIREMENTS)

- C-1: 마스킹 규칙의 정본은 `app/utils/logs/filters.py` 의 `redact()` 하나다. 다른 경로는 `RedactingFilter` 를 달아 재사용한다 — ADR-002.
- C-2: 접속 로그 원문 저장(`session_id`·Referer·XFF)은 사용자 결정 없이 바꾸지 않는다 — ADR-003.
- C-3: 예외 응답 본문 형식(`error_code`·`message`·`detail`)은 유지한다 — ADR-004.
- C-4: Redis 최소 버전 상수와 코드가 쓰는 명령은 함께 움직인다(계약 테스트) — ADR-005.
- C-5: 커버리지 하한은 pyproject 한 곳. 명령줄 하한 금지 — ADR-007.
- C-6: 전체 suite skip 0, 기존 테스트를 느슨하게 만들어 통과시키지 않는다. 동작이 바뀐 테스트는 run-log 에 이유를 적는다(admin-login C-7 승계).

## 5. 변경 이력
- v0.1 (2026-10-13): 최초 작성. REQ-001·REQ-002, ADR-001~ADR-007, C-1~C-6. orm-raw-repository R-007 에 상태 주석 append.
