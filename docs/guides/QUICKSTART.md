# QUICKSTART — 처음 보는 사용자를 위한 최소 실행 경로

이 저장소는 MySQL·Redis·Celery·SQLAdmin·JWT·DB read/write 라우팅을 모두
포함한다. 전부 이해하고 시작할 필요는 없다. 이 문서는 **가장 먼저 무엇만 알면 되는지**만
다룬다. 전체 구조는 [ARCHITECTURE.md](./ARCHITECTURE.md), 전체 설정은 [../../README.md](../../README.md).

검토 기준: **2026-09-17 현재 작업 트리**. 설정·자원·요청·종료는
[서버 수명 HTML 안내서](./server-lifecycle-guide.html), MVC·주입·비동기·신규 뷰/테이블 작성은
[개발 HTML 지침서](./feature-development-guide.html)를 함께 읽는다.

---

## 1단계 — Redis를 준비해 최소 HTTP 배선 확인

MySQL 없이 앱 배선부터 확인할 수 있지만, startup 단계의 연결 검증을 통과하려면 Redis는 필요하다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
uv sync
DEBUG=false uv run uvicorn main:app --port 8000
```

위 환경변수 지정은 Bash 문법이다. PowerShell에서는 다음처럼 실행한다.

```powershell
$env:DEBUG = "false"
uv run uvicorn main:app --port 8000
# 서버 종료 후 필요하면 개발 기본값으로 복원
Remove-Item Env:DEBUG
```

저장소 루트에서 실행한다. 실제 `.env`가 있으면 DB·Redis 값이 기본값과 다를 수 있다.
운영체제 환경변수는 `.env`보다 우선하며 `.env.example`은 자동 fallback이 아니다.

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","version":"0.1.0"}
```

앱은 시작하면서 `REDIS_HOST`/`REDIS_PORT`로 `ping()`을 호출하며, 연결되지 않으면 startup을
중단한다. 위 단계는 Redis만 사용해 HTTP 배선이 정상인지 확인하는 용도다.

### 이 상태에서 되는 것 / 안 되는 것

| | 동작 | 이유 |
|---|---|---|
| `GET /health` | ✅ | DB를 건드리지 않는다 |
| `GET /ready` | ❌ 503 | writer DB의 SELECT 1 검사가 실패한다. Redis runtime 가용성은 검사하지 않는다 |
| `GET /api/v1/blog/posts` 등 기능 API | ❌ 500 | MySQL 연결이 필요하다 |
| `GET /docs` (Scalar), `/openapi.json` | ❌ 404 | **`DEBUG=false` 가 문서를 끈다** (운영 보안 기본값) |

> API 문서를 보려면 `DEBUG=true` 여야 하고, `DEBUG=true` 는 MySQL을 요구한다(2단계).
> 이 둘이 한 스위치에 묶여 있다는 점이 첫 실행에서 가장 헷갈리는 부분이다.

`/health`는 liveness, `/ready`는 DB readiness이다. startup Redis ping 성공이 이후의 Redis
정상 상태까지 보장하지는 않는다. `DEBUG=false`에서 DB 없이 확인 가능한 것은 최소 HTTP
배선이며, 실제 기능·관리 화면·접속 로그 저장에는 DB가 필요하다.

---

## 2단계 — 기능 API까지 쓰려면 MySQL 추가

### 왜 필요한가

`DEBUG=true`(기본값)면 앱 시작 시 `create_db_tables()` 가 실행된다. 즉 **아무 설정 없이
`uvicorn main:app` 을 그냥 실행하면 MySQL이 없어서 startup 단계에서 실패한다.**

```text
[startup] 테이블 생성 단계의 연결 오류 예시 (표현은 드라이버·버전에 따라 다름)
(2003, "Can't connect to MySQL server on 'localhost'")
```

Redis ping이 먼저 성공해야 DB 생성 단계까지 도달한다. DB 서버 미기동뿐 아니라
호스트·포트·방화벽·인증 설정도 확인한다.

### MySQL 띄우기

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8
```

기본 설정값(`MYSQL_HOST=localhost`, `MYSQL_USER=root`, `MYSQL_PASSWORD=""`,
`MYSQL_DATABASE=fastapi_db`)에 맞춘 로컬 예시다. DB 준비 완료·접속 권한과 Redis 가용성도
확인한다. 빈 root 비밀번호는 로컬 전용이며 운영에 사용하지 않는다.

```bash
uv run uvicorn main:app --reload --port 8000
```

- API 문서: <http://127.0.0.1:8000/docs>
- 기능 API: `GET /api/v1/blog/posts`

---

## 환경 변수 — 무엇이 필수인가

설정 문자열은 모두 기본값이 있어 `.env` 없이도 읽히지만, 기본 주소의 Redis 서버는 반드시
접속 가능해야 한다. 처음에 의미 있는 것은 아래 정도이고, 나머지는 나중에 봐도 된다.

| 변수 | 기본값 | 첫 실행에서의 의미 |
|---|---|---|
| `DEBUG` | `true` | true=개발 테이블 생성 + `/docs` 켜짐 / false=둘 다 꺼짐. false여도 DB API·`/ready`·접속 로그 저장에는 MySQL 필요. Redis ping은 양쪽 모두 필수 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | `localhost` / `6379` / `0` | startup `ping()` 대상. 연결 실패 시 서버가 시작되지 않는다 |
| `ADMIN` | `true` | `/admin` 관리 화면이 **기본으로 켜진다**. ⚠️ **인증이 없다** — 아래 주의 참고 |
| `MYSQL_HOST` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `root` / `""` / `fastapi_db` | 위 docker 명령과 맞춰져 있다 |
| `DB_ROUTER_ENABLED` | `false` | 기본은 단일 엔진. read/write 분리는 선택 기능 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | 로컬은 그대로 둬도 되지만 **배포 전 반드시 교체** |

> **⚠️ `ADMIN=true` 가 기본값이고 `/admin` 에는 인증이 없습니다.**
> 로컬 개발에서 바로 DB 를 들여다볼 수 있도록 한 **의도된 기본값**이지만, 그 말은
> 앱에 도달할 수 있는 누구나 사용자·게시글·접속로그를 조회·수정·삭제하고 CSV 로
> 내보낼 수 있다는 뜻입니다(비밀번호 해시만 제외). **운영·스테이징은 `ADMIN=false`**
> 를 명시하거나 리버스 프록시에서 `/admin` 을 막으세요.

**Active 저장소의 추가 규칙:** ENV=staging/production이면 `validate_deployment_safety()`가
config import 중 실행된다. DEBUG=false·ADMIN=false를 명시하고 토큰·세션 비밀키를 안전한
값으로 교체해야 한다. 두 토큰 키는 서로 달라야 한다. wildcard CORS·SQL echo도 허용하지 않는다. 프록시에서
/admin을 차단하더라도 현재 ADMIN=true 기동 검증을 우회하지 못한다.

전체 목록은 [`.env.example`](../../.env.example).

`.env` 를 쓰려면:

```bash
cp .env.example .env
```

PowerShell: `Copy-Item -LiteralPath .env.example -Destination .env`.
기존 `.env`가 있으면 덮어쓰지 않고 필요한 항목만 확인한다.
`DEBUG=false`의 미지정 로그 레벨은 INFO이다. `LOG_LEVEL`·`LOG_CONSOLE_LEVEL` 명시값은
DEBUG보다 우선하므로 false여도 DEBUG 로그가 출력될 수 있다. 시작 로그의 `(DEBUG=%s)`는
메시지의 표시값이지 출력 조건문이 아니다.

---

## 선택 기능 — 지금은 몰라도 된다

기본 실행 경로에 **필요 없는** 것들이다. 필요해질 때 해당 문서를 보면 된다.

| 기능 | 필요 인프라 | 기본 상태 | 언제 보면 되나 |
|---|---|---|---|
| Celery 비동기 태스크 | startup에서 확인한 Redis | 꺼짐(워커 미기동) | 백그라운드 작업이 필요해질 때 |
| DB read/write 라우팅 | replica MySQL | 꺼짐 | 읽기 부하 분리가 필요할 때 |
| Alembic 마이그레이션 | MySQL | — | 운영 배포 시 (`DEBUG=false` 면 테이블 자동 생성이 꺼진다) |
| SQLAdmin 관리자 화면 | (앱 내장) | **켜짐** | `/admin` 으로 바로 접근. 인증 없음(위 주의) |

---

## 테스트 — 인프라 불필요

단위 테스트는 in-memory SQLite와 가짜 Redis를 쓰므로 외부 인프라 없이 돌아간다.
`pyproject.toml` 의 pytest 설정이 `DEBUG=true`·`ENV=test` 를 주입하고 `tests/` 와
`app/features/*/tests/` 를 함께 수집한다.

```bash
uv run python -m pytest --basetemp .pytest_tmp
uv run ruff check .
uv run mypy . --cache-dir .mypy_tmp
```

`mysql` 마커 테스트(`tests/integration/`)는 MySQL 8.4 가 `127.0.0.1:3310` 에 없으면 **skip** 된다.
로컬에서 skip 없이 보려면 전용 컨테이너를 띄운다(포트는 `MYSQL_TEST_PORT` 로 변경 가능).

```bash
docker compose -f compose.test.yaml up -d --wait
uv run python -m pytest -m mysql
docker compose -f compose.test.yaml down -v
```

CI 와 같은 판정(정적 검사·구조·공급망·문서·의존성 취약점·테스트)은 한 명령으로 돌린다.
`deps` 그룹은 네트워크가, `tests` 그룹은 skip 0 판정이라 MySQL 이 필요하다.

```bash
uv run python -m scripts.review_gate --list          # 그룹 목록
uv run python -m scripts.review_gate --group static docs
```

> `pytest` 가 아니라 **`python -m pytest`** 를 쓴다. 콘솔 스크립트(`uv run pytest`)가
> 다른 인터프리터를 집어 import 가 어긋난 전례가 있어 이쪽을 표준으로 삼는다.
> CI(`.github/workflows/ci.yml`)도 같은 형태로 돌린다 — gate job 은 `-m "not mysql"`,
> MySQL job 은 `compose.test.yaml` 을 띄워 `-m mysql` 과 전체 suite 를 돌린다.
>
> `--cache-dir .mypy_tmp` 는 로컬 편의용이다. **게이트 판정용 mypy 는 캐시를 지우고**
> 돌린 결과만 유효하다 — 따뜻한 캐시가 통과로 잘못 기록된 전례가 있어 CI 는 캐시를
> 복원하지 않는다.

---

## 새 기능 추가

디렉터리를 만들면 끝이다 — **중앙 파일 편집이 없다**.

```bash
uv run python -m scripts.new_app orders --with-admin
```

`--with-admin`은 선택 옵션이므로 관리 화면이 필요 없으면 생략한다. 같은 이름의 앱이 이미 있으면
생성기는 덮어쓰지 않고 중단한다(정말 다시 만들 때만 `--force`). 앱 이름은 파이썬 식별자(snake_case)여야
한다. 생성기는 패키지 골격·빈 `orders_router`·의존성 예시 주석(+ 빈 `admin_views`)만 만든다 —
`models/models.py`·스키마·Repository·Service·View·테스트와 migration은 별도로 완성한다
(ORM/Raw 선택은 [orm-raw-workflow.md](./orm-raw-workflow.md)).

`AppRegistry` 가 부팅 시 `app/features/*` 를 훑어 라우터(`<name>_router`)·모델·`admin_views`
를 자동 결선하므로 `main.py`·`migrations/env.py`·중앙 Admin 목록을 열지 않는다.
회귀 가드: `tests/test_app_autowiring.py`(임시 앱 결선 + 중앙 파일 해시 불변),
`tests/test_router_registration.py`(발견된 앱의 라우터 마운트).

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동·주소/포트/인증 오류 | REDIS_* 설정과 서버 가용성 확인. DEBUG=false로 우회되지 않음 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL을 띄우거나 `DEBUG=false` |
| `/docs` 가 404 | `DEBUG=false` 에서는 문서가 꺼진다 | `DEBUG=true` (MySQL 필요) |
| 기능 API만 500 | 앱은 떴지만 DB가 없다 | 2단계 진행 |
| 새 기능이 마운트 안 됨 | 디렉터리명이 파이썬 식별자가 아니거나 `_` 로 시작, 또는 라우터 변수명이 `<name>_router` 가 아님 | 규약 확인 (README 「앱 자동 등록 규약」). 파일 **내부** import 오류라면 조용히 넘어가지 않고 기동이 실패한다 |

---

## 과거 실행 기록과 현재 검토 범위

**2026-09-17:** 현재 코드·설정·문서 연결을 검토했다. 아래 실행 수치와 HTTP 결과는
**Redis 필수 startup 검증 도입 전의 과거 기록**이며 현재 테스트 수나 Redis 없이 기동할 수
있다는 근거가 아니다. 현재 실제 서버·MySQL·Redis 성공 연결 검증을 새로 수행한 기록은 아니다.
같은 날 외부 인프라 없이 확인한 것: `uv run python -m pytest` 675 passed · 31 skipped(전부 `mysql`
마커 — MySQL 컨테이너 없음), `--collect-only` 706건, `python -m scripts.new_app --help` 옵션
(`--category`·`--with-admin`·`--force`) 일치.

**과거 확인: 2026-08-12** (FastAPI 0.141.x, Python 3.14). 아래는 당시 실제로 실행하거나
설정값을 읽어 대조한 결과다.

| 항목 | 방법 | 결과 |
|---|---|---|
| `DEBUG=false` 기동 → `/health` | 요청 | **200** `{"status":"healthy","version":"0.1.0"}` — 위 응답 예시와 일치 |
| `DEBUG=false` → `/docs` · `/openapi.json` | 요청 | **404** 둘 다 |
| 기본값(`DEBUG=true`) + MySQL 없음 → startup 실패 | 기동 | 확인 |
| 표의 기본값 전부 | `config.py` 필드 기본값 직접 읽기 | 일치 (`DEBUG`·`ADMIN`·MySQL 4종·`DB_ROUTER_ENABLED`·토큰 키 2종) |
| pytest / ruff / mypy | 실행 | 186 passed · 청정 · 146 files Success |

MySQL `docker run` 이후 경로는 이 환경에 Docker 가 없어 **실행 확인하지 못했다.** 설정
기본값과 대조해 작성했으므로, 다를 경우 이 문서를 고쳐 주기 바란다.
