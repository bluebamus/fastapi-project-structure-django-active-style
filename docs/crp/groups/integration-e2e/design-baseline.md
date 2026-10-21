# Design Baseline — integration-e2e (기준 설계 문서)

> 이 그룹의 **요구사항·설계 결정의 단일 기준**. append-only — 항목은 지우지 않고 상태만 바꾼다.

## 0. 질의 수준 (Autonomy Level)

- [ ] **적극(Thorough)**
- [x] **보통(Balanced)**
- [ ] **간략(Lean)**

선택: **보통** · 선택일: 2026-10-20 · 사유 — 사용자가 계획서(§0 결정·§2 작업·§3 테스트·§5 확인)를 확정했고, 감독자 명세가
W0 와 저장소별 포트·docker 허용 범위를 정했다. 관측 3건은 사용자가 별도로 결정했다(REQ-002).

## 1. 목적 / 배경

병합된 main 위에서 앱 전체를 실제 프로세스(uvicorn·Celery·Chromium)·실제 MySQL 복제·실제 Redis 로 돌려, 모든 API
operation·관리 화면·백그라운드·장애·운영 경로를 검사하고 그 결과를 영구 스위트(`tests/e2e/`, 마커 `e2e`)와 CI job 으로 남긴다.

## 2. 요구사항 레지스터 (append-only)

| ID | 날짜 | 요구 | 출처 | 상태 |
|---|---|---|---|---|
| REQ-001 | 2026-10-20 | 통합 테스트 진행 — 계획서 W0~W9, L1~L6. 통과 기준: 실패 0·skip 0·xfail 0·인벤토리 빈 칸 0·로그 비밀값 grep 0. 찾은 결함은 테스트를 먼저 고정하고 별도 커밋으로 고친다(정책 변경은 멈추고 보고) | 사용자("통합 테스트 진행해줘") + 계획서 + 명세 | 완료 |
| REQ-002 | 2026-10-20 | 관측 3건 결정 반영: (b) Redis 장애 → 503·traceback 한 번·연결 유지, (c) replica 연결 오류 → primary 한 번 재시도 + WARNING, `/ready` 그대로, (a) 기동 초기 줄도 프로세스별 파일에 | 사용자 결정(e2e-policy-fixes 명세) | 완료 |
| REQ-003 | 2026-10-21 | e2e 정책 결정 2차 7건: (1) OpenAPI 422 = 실제 본문 (2) 처리되지 않은 500 의 traceback 한 번·keep-alive (3) 모든 401 `WWW-Authenticate: Bearer` (4) CLI 비밀번호 변경도 세션 폐기·Redis 불가면 실패 (5) 인증 사용자 조회는 primary (6) 관리 화면 Redis 장애는 모두 503 (7) CSRF 폼 본문 상한 413·필드 400. 추가 결정: 결정 2 는 ① 미들웨어로 직접 받기, 의존성은 `aiomysql[rsa]` 로 통일 | 사용자 결정(e2e-policy-2 명세·추가 결정) | 완료 |

## 3. 설계 결정 (ADR)

### ADR-001 E2E 환경은 `compose.e2e.yaml` 로 분리한다
- 결정: 기존 `compose.test.yaml`(mysql 마커용 단일 MySQL, container_name·포트 고정)에 붙이지 않고 별도 파일·프로젝트(`itest-active`).
- 이유: 복제를 붙이면 mysql 마커 실행도 무거워지고, 고정 container_name 은 다른 compose 와 겹친다. 이미지 digest 는 두 파일이 같다.
- 데이터는 tmpfs — `down` 만으로 정리(-v 불필요). 복제는 replica 의 init 스크립트가 GTID 자동 위치(`SOURCE_AUTO_POSITION`)로 붙고, healthcheck 는
  IO·SQL 스레드와 앱 DB 복제를 본다. 비밀번호는 실행마다(`E2E_MYSQL_PASSWORD`, 복제 계정 한계로 32자 이하).
- init 스크립트는 `mysql` 클라이언트를 쓴다 — `/mnt/c` 의 0777 은 실행 권한이 붙어 entrypoint 가 source 대신 실행하므로 헬퍼 함수가 없다.

### ADR-002 하네스 자식 프로세스는 `.env` 를 읽지 않는다
- 결정: uvicorn·Celery·Alembic·스크립트를 산출물 폴더를 cwd 로 띄우고(`env_file=".env"` 는 cwd 기준), OS 변수 몇 개만 물려준 뒤 앱 설정을
  모두 명시한다(`ENV=staging`, `DEBUG=false`, 라우터·복제 켬, `TRUSTED_PROXY_HOPS=1`, 파일 로그, rate limit 창 6초).
- 이유: 로컬 `.env` 가 결과를 바꾸지 못하게 한다(W0 사고의 일반화). staging 이라 파일 로그·Secure 쿠키·배포 안전 검사가 실제와 같다.

### ADR-003 `-m e2e` 일 때만 수집한다(ignore, deselect 아님)
- 결정: `tests/e2e/conftest.py` 의 `pytest_ignore_collect`.
- 이유: review gate `tests` 그룹(MySQL job)은 전체 suite 에서 deselected 0 을 요구한다. deselect 로 빼면 그 판정이 깨진다.

### ADR-004 primary 장애는 `offline_mode=ON` 으로, Redis·replica 는 컨테이너 정지로 주입한다
- 결정: primary 컨테이너를 멈추면 tmpfs 스키마가 사라지므로 `SET GLOBAL offline_mode=ON`(앱 계정 연결 끊고 새 연결 거부)으로 정지를
  흉내 낸다. replica 는 실제로 멈추고 다시 띄우면 primary binlog 를 GTID 로 처음부터 받아 복구된다 — 복구는 GTID 따라잡기까지 기다린다.

### ADR-005 의존성
- dev `playwright`(L4 실제 브라우저), dev `pytest-timeout`(테스트마다 시간 제한 — 관리 화면 이동 중 정지 방지, 기본 300초, `E2E_TEST_TIMEOUT`).
- 런타임 `pymysql[rsa]`(= `cryptography`) — F-001.

### ADR-006 Redis 연결 장애는 전역 핸들러에서 503 으로 끝낸다 (REQ-002 b, F-004)
- 결정: `main._register_exception_handlers` 에 `redis.exceptions.ConnectionError`·`TimeoutError` 핸들러 —
  `ServiceUnavailableException`(503 `SERVICE_UNAVAILABLE`) 본문, `logger.error(exc_info)` 한 번.
- 이유: 그 예외가 전역 `Exception` 핸들러로 가면 Starlette `ServerErrorMiddleware` 가 500 을 보낸 뒤 예외를 다시 올리고, uvicorn 이
  traceback 을 한 번 더 남기며 transport 를 닫는다(클라이언트는 응답 대신 연결 리셋). 클래스별 핸들러는 `ExceptionMiddleware` 안에서
  끝나 다시 올라가지 않는다. 한 곳에서 처리하므로 Redis 를 쓰는 API(로그인·가입 rate limit, refresh 저장소: login·refresh·logout,
  사용자 비활성화·강등·삭제의 refresh·관리 세션 폐기) 전부에 같이 적용된다. 관리 화면은 자기 세션 미들웨어가 이미 503 이다.
- 범위 밖: `ResponseError` 등 명령 오류는 버그라 500 그대로.

### ADR-007 replica 연결 오류 → primary 로 한 번 재시도 (REQ-002 c, F-005)
- 결정: `RoutingSession._execute_internal`(SQLAlchemy 2.0 의 `execute`·`scalars`·`get` 공통 지점)에서 DBAPIError 를 잡아, **read-only
  세션이고 지금 replica 에 있으며 연결 계열 오류**(MySQL 1040·1053·2002·2003·2005·2006·2013·2055·3032 또는 `connection_invalidated`)일 때만
  rollback → writer 고정 → 같은 구문을 한 번 다시 실행하고 WARNING(오류 클래스·코드만) 한 줄.
- 이유: read-only 세션은 쓰기가 없어 rollback 으로 잃을 것이 없다. 쓰기·routed 세션은 트랜잭션 안의 쓰기와 섞일 수 있어 제외.
  복제 지연은 오류가 아니므로 대상이 아니다. 라우터가 꺼진 구성은 reader 가 없어 변화 0. `/ready` 는 그대로(writer·Redis).
- 한계: 이후 같은 세션의 읽기도 writer 로 간다(세션 단위 고정). 실패를 기억하는 회로 차단기는 없다 — 요청마다 replica 를 먼저 시도한다(R-1105).

### ADR-008 프로세스 종류는 진입점으로 정한다 (REQ-002 a, F-006 — logging-overhaul ADR-001 개정)
- 결정: `app.utils.logs.config._process = process_from_argv(sys.argv)` — `celery` CLI·`python -m celery` 면 `celery`, 그 밖은 `app`.
  Celery 로깅 신호(`on_setup_logger`)가 한 번 더 확정한다(기존 그대로).
- 이유: 신호를 기다리면 설정 로드 직후 줄(`[database] 라우팅 구성` 등)이 웹 파일 `app.log` 로 갔다(logging-overhaul R-902).
  모듈 import 로 정하지 않고 argv 로 정하므로 웹이 Celery 모듈을 import 해도 웹 줄은 `app.log` 다. beat 도 `celery.log` 를 쓴다.
- 웹·`python main.py`·`uvicorn main:app` 은 이미 가장 이른 줄부터 `app.log` 에 남고 있었다(e2e 로 확인) — 바뀌지 않는다.

### ADR-009 OpenAPI 422 는 앱 생성 시 문서 후처리 한 곳에서 실제 형식으로 바꾼다 (REQ-003 결정 1, P-001)
- 결정: `main.py` 의 `app.openapi` 를 감싸 FastAPI 가 붙인 422 `HTTPValidationError` 참조를 `ErrorResponse` 로 바꾸고,
  쓰이지 않게 된 `HTTPValidationError`·`ValidationError` 컴포넌트를 지운다. 응답은 그대로다.
- 이유: 라우트마다 `responses={422: ...}` 를 달면 새 라우트가 빠뜨린다. 앱 수준 `responses` 는 파라미터가 없는 operation
  (`/health`)에도 422 를 광고해 거짓 문서가 된다. 후처리는 FastAPI 가 422 를 붙인 operation 만 정확히 고친다.
- 계약: `tests/test_openapi_contract.py::test_every_422_documents_the_actual_error_body`, e2e L2 검증 오류 칸이 광고 스키마로 실제 본문을 검증.

### ADR-010 CLI 비밀번호 변경은 커밋 전에 API 와 같은 폐기를 한다 (REQ-003 결정 4, P-002)
- 결정: `scripts/create_superuser.py --set-password`(기존 사용자)는 해시를 바꾼 뒤 **커밋 전에** `revoke_user_access`(API·관리 화면과
  같은 함수)로 refresh family 와 관리 세션을 끊는다. Redis 클라이언트는 수명주기와 같은 설정·타임아웃으로 만든다.
  `RedisError` 면 종료 코드 2, 커밋하지 않으므로 비밀번호도 그대로다. 새 사용자 생성·승격만은 Redis 를 쓰지 않는다.
- 순서: 폐기 → 커밋. 커밋이 실패하면 세션만 끊기고 비밀번호는 그대로다(안전한 쪽).

### ADR-011 인증 사용자 조회는 read-only 세션을 primary 에 고정한다 (REQ-003 결정 5)
- 결정: `get_current_user` 가 받은 read-only 세션에 `using_writer(session)` 를 건다 — 쓰기 차단(read-only)은 그대로, 조회만 primary.
- 이유: 새 의존성을 만들면 테스트의 세션 override(`tests/session_overrides.py`)까지 늘려야 하고, 빠뜨리면 테스트가 실제 DB 로 샌다.
- 한계: 같은 요청에서 같은 read-only 의존성을 쓰는 다른 조회도 primary 로 간다(FastAPI 의존성 캐시). 지금은 `/me` 만 쓴다(R-1108).

### ADR-012 CSRF 폼 버퍼링 상한은 미들웨어 상수로 둔다 (REQ-003 결정 7)
- 결정: `AdminCsrfMiddleware` 가 폼 본문을 버퍼링하기 전에 `Content-Length` 가 10 MiB 를 넘으면 읽지 않고 413, 없거나 거짓이면
  읽는 도중 누적 크기가 넘는 순간 413. 필드 하나 1 MiB 상한은 starlette 폼 파서 기본값(`max_part_size`)이 집행하고, 파서 예외
  (필드 초과·깨진 폼)는 400 이다(이전에는 "토큰 없음"으로 보아 403).
- 상한을 설정으로 두지 않은 이유: 이 모듈의 다른 상한(`_LOG_USERNAME_MAX` 등)도 상수이고, 관리 화면의 큰 업로드(CSV 가져오기)는
  헤더로 토큰을 보내 버퍼링 경로를 지나지 않는다.
- 결정 7 은 명세에 다른 실행 환경 몫으로 표시돼 있었지만, 이 저장소의 미들웨어도 같은 무제한 버퍼링을 하고 있어 같은 결정을 적용했다.

### ADR-013 처리기가 없는 예외는 가장 바깥 사용자 미들웨어에서 받는다 (REQ-003 결정 2 ①, P-003)
- 결정: `main.py` 의 `@app.middleware("http")` `answer_unhandled_exception` — `call_next` 의 예외를 기존 `Exception` 처리기
  (`general_exception_handler`, 로그 형식·마스킹·본문 그대로)로 응답한다. 가장 나중에 등록해 사용자 미들웨어 중 가장 바깥
  (`ServerErrorMiddleware` 바로 안쪽)에 둔다 — CORS·UserInfo 안에서 난 예외도 받는다. `DEBUG=true` 면 다시 던진다(기존 동작).
- 이유: Starlette `ServerErrorMiddleware` 는 처리기로 응답한 뒤 예외를 다시 던지고(`starlette/middleware/errors.py` 186행),
  uvicorn 은 그 예외를 `Exception in ASGI application` 으로 한 번 더 기록하고 응답이 시작됐으므로 transport 를 닫는다
  (`uvicorn/protocols/http/h11_impl.py` 414~420행).
- 범위: 본문 전송 중의 예외는 `call_next` 가 돌려준 뒤라 여기 오지 않는다(기존대로). 관리 화면(sqladmin 하위 Starlette 앱)은 자기
  `ServerErrorMiddleware` 가 먼저 평문 500 을 보내므로 해당하지 않는다(R-1109).

### ADR-014 cryptography 는 `aiomysql[rsa]` 로 선언한다 (REQ-003 추가 결정, F-001 개정)
- 결정: `aiomysql[rsa] (>=0.3.0,<0.4.0)`(= `PyMySQL[rsa]` = `cryptography`), Alembic 이 직접 쓰는 `pymysql>=1.2.0` 은 추가 옵션 없이.
  `uv lock` 의 차이는 의존성 표기뿐 — `cryptography` 는 lock 에 그대로다. 계약: `tests/core/test_mysql_auth_dependency.py`.
