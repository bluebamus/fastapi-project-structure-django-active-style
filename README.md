# FastAPI Project Structure — Django Active Style

Repository 패턴과 계층 분리를 적용한 FastAPI 프로젝트 골격입니다.

**Django 스타일 앱 자동 등록**을 씁니다. `app/features/<name>/` 디렉터리를 만드는 것만으로 그 앱의
라우터·모델·관리 화면이 결선되고, `main.py`·`migrations/env.py`·중앙 Admin 목록은 손대지 않습니다.
데이터 접근은 ORM 과 Raw SQL 두 방식을 각각 완결된 예제 기능으로 보여 줍니다.

## 목차

- [특징](#특징) · [기술 스택](#기술-스택) · [구조 한눈에](#구조-한눈에)
- [ORM / Raw 데이터 접근](#orm--raw-데이터-접근)
- [빠른 시작](#빠른-시작) · [스키마 관리](#스키마-관리--자동-생성에서-alembic-으로) · [테스트](#테스트)
- [환경 설정](#환경-설정) · [운영 배포](#운영-배포)
- [API](#api) · [새 기능 추가](#새-기능-추가) · [자주 막히는 지점](#자주-막히는-지점)
- [문서 안내](#문서-안내)

---

## 특징

- **앱 자동 등록** — `AppRegistry` 가 `app/features/*` 를 발견해 `<name>_router` 를 `/api` 에 마운트하고,
  모델을 `Base.metadata` 에, `admin_views` 를 SQLAdmin 에 등록합니다. 잘못된 계약은 조용히 넘기지 않고
  기동을 멈춥니다.
- **계층 분리** — View(Router) → Dependency → Service → Repository → DB.
- **명시적 트랜잭션 경계** — Dependency 는 Service 를 조립만 하고, 커밋은 **쓰기 핸들러 본문**이
  응답 전에 `await service.commit()` 으로 한 번 합니다(UnitOfWork 없음).
- **읽기/쓰기 세션 분리** — 조회는 `get_read_only_db_session`(쓰기 시도 시 예외), 변경은
  `get_writer_db_session`. 선택적으로 replica 라우팅.
- **ORM 과 Raw SQL** — `BaseRepository`(catalog 예제)와 `RawRepositoryBase`(reports 예제).
- **JWT 인증** — OAuth2 password flow, access/refresh 토큰(refresh 회전·재사용 탐지·로그아웃),
  Argon2 해시(기존 bcrypt 해시는 로그인 때 이전), 로그인·가입 rate limit.
- **인가** — 슈퍼유저/일반 2단계. 글 수정·삭제는 작성자 본인 또는 슈퍼유저, 관리 API 는 슈퍼유저 전용
  ([권한 표](#권한-표)). 첫 슈퍼유저는 `scripts/create_superuser.py` 로 만든다.
- **관리 화면** — SQLAdmin `/admin` 은 활성 슈퍼유저 로그인(Bootstrap 로그인 화면, 서명 세션 쿠키)
  뒤에 있고, `ADMIN_DISABLED=true` 면 경로·링크·로그까지 통째로 사라진다
  ([admin 인증 안내서](docs/guides/admin-auth-guide.html)).
- **운영 안전장치** — staging/production 에서 위험한 설정이면 기동 거부, 오류 응답에 내부 정보 비노출,
  접속 로그 비동기 수집, 로그 비밀값 마스킹(메시지·예외 traceback·stack — uvicorn·Celery 핸들러 포함).
- **검증 게이트** — 로컬과 CI 가 같은 `scripts/review_gate.py` 로 정적 검사·테스트·공급망·문서를 판정.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Framework | FastAPI 0.141 (Python 3.14, 최소 3.13 — `TypeVar(default=...)` 사용) |
| ORM / DB | SQLAlchemy 2.0 async · MySQL(aiomysql) |
| Validation / Settings | Pydantic v2 · pydantic-settings |
| Migration | Alembic |
| Redis | **7.0 이상**(rate limit 의 `EXPIRE … NX`) — startup 연결·버전 검증(필수) · Celery broker/backend · refresh 토큰 저장소 · rate limit |
| Task Queue | Celery |
| Admin / API Docs | SQLAdmin · Scalar |
| Auth | OAuth2 Password + PyJWT + pwdlib(Argon2) |
| Tooling | uv · ruff · mypy · bandit · pytest · pip-audit |

## 구조 한눈에

```text
main.py            조립: 앱 자동 발견·결선 + 미들웨어·예외·문서·lifespan·Admin
config.py          설정 단일 출처 (Pydantic Settings) + 배포 안전 게이트
app/features/      기능 앱 — 디렉터리 존재 = 등록 선언
  auth · blog · catalog(ORM 예제) · home(접속 로그) · reply · reports(Raw 예제) · sns · user
app/core/          registry · db(세션·라우팅) · Base 모델/Repository/Service · 미들웨어 · 자원 관리
                   · security(JWT 발급·검증 · refresh 저장소 · rate limit · 해시 · 인증 주체·소유권)
app/celery/        Celery 앱·실행 기반 (태스크는 기능별 tasks.py, registry 가 발견)
app/utils/         로깅 · 페이지네이션 · 검증
migrations/        Alembic (런타임과 같은 registry 로 모델 수집)
scripts/           new_app.py(앱 생성기) · review_gate.py(검증 게이트) · create_superuser.py(첫 관리자)
tests/             횡단 테스트 (기능 테스트는 app/features/<name>/tests/)
docs/              guides(현행) · specs(고정 기준선) · crp(검수 이력)
```

```text
요청 → 미들웨어(접속 로그·CORS) → Router → Depends(get_<name>_service) → Service(session) → Repository → DB
                                     └ 쓰기 핸들러가 응답 전에 await service.commit()
```

앱 등록 규약(찾는 파일 여섯 가지, 오류 정책, `apps.py` 의 `ready()` 훅, Django 대응 범위), 기동·종료
순서, 세션·라우팅은 [ARCHITECTURE](docs/guides/ARCHITECTURE.md)에 있습니다.

---

## ORM / Raw 데이터 접근

두 방식을 모두 지원하고, 각각 완결된 예제 기능이 있습니다. 새 기능을 만들기 전에 어느 쪽인지 먼저
정합니다.

| | ORM | Raw SQL |
|---|---|---|
| **언제** | 일반 CRUD, 엔티티 단위 조작 | 복잡한 집계·윈도 함수·CTE, 성능 민감 조회, 저장 프로시저 |
| **돌려주는 것** | 엔티티(식별자·수명주기 있음) | 계산 결과(행) |
| **Base** | `BaseRepository[Model, PK타입]` | `RawRepositoryBase` |
| **예제 기능** | `app/features/catalog/` (상품 CRUD) | `app/features/reports/` (일별 매출) |
| **공개 API** | `/api/v1/catalog/products` | `GET /api/v1/reports/sales/daily` |

**기본값은 ORM 입니다.** Raw 는 위 상황에서 고르는 도구이고, 판단이 애매하면 돌려주는 것이 엔티티인가
계산 결과인가를 봅니다. 두 방식의 공통 규칙:

- commit 은 쓰기 View 가 응답 직전에 한 번만 — Repository 도 Dependency 도 하지 않습니다
- 조회는 `get_read_only_db_session`, 변경은 `get_writer_db_session` — Raw 라고 쓰기 세션을 쓰지 않습니다
- SQL 은 상수, 값은 named bind — 요청 값으로 SQL 을 조립하면 정적 검사가 막습니다
- Raw 결과(`RowMapping`)는 Service 에서 DTO 로 바꿉니다

**→ 파일 순서·결과 API 의미·MySQL 검증까지: [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md)**

---

## 빠른 시작

저장소 루트에서 실행합니다. 셸 예시는 Bash 기준이고, PowerShell 은 따로 적었습니다.

### 1. 설치

```bash
uv sync
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # 키마다 한 번씩, 세 번 실행
```

`.env` 에서 아래를 바꿉니다. 바꾸지 않으면 **개발 환경에서도 기동하지 않습니다**(설정 검사). 오류
메시지에 고칠 설정 이름이 나오므로 그대로 따라 고치면 됩니다.

| 설정 | 할 일 |
|---|---|
| `ACCESS_TOKEN_SECRET_KEY`·`REFRESH_TOKEN_SECRET_KEY`·`SESSION_SECRET_KEY` | 위 명령으로 만든 값을 **서로 다르게** 넣는다(32자 이상) |
| `MYSQL_PASSWORD` | 3단계에서 띄울 MySQL 의 비밀번호와 같은 값. 비워 두거나 예시 값이면 거부 |
| `SMTP_PASSWORD` | 메일을 안 쓰면 **비운다**. 예시 값을 남겨 두면 거부 |

`.env` 가 없으면 기동하지 않습니다. 파일 없이 환경 변수로 주입하는 경우(컨테이너)는 `ENV`·비밀 키 3종·
`MYSQL_HOST/USER/PASSWORD/DATABASE` 가 모두 있어야 합니다. 프로세스 환경변수가 `.env` 보다 우선하고,
`.env.example` 은 자동으로 읽히지 않습니다. 이미 `.env` 가 있다면 덮어쓰지 말고 필요한 항목만 확인합니다.
테스트(`ENV=test`, pytest 가 지정)는 이 검사를 하지 않습니다.

### 2. Redis 만으로 HTTP 배선 확인

**Redis 는 항상 필요합니다.** 앱은 startup 에서 `REDIS_HOST`/`REDIS_PORT` 로 `ping()` 하고, 실패하면
시작하지 않습니다(`DEBUG=false` 로도 우회되지 않습니다). 이어서 `INFO server` 로 버전을 확인해
**7.0 미만이면 시작하지 않습니다** — 코드가 쓰는 명령 중 가장 늦게 생긴 것이 rate limit 의 `EXPIRE … NX`(7.0)
입니다(`GETDEL` 6.2, `SET … EX` 2.6.12). INFO 가 막힌 관리형 Redis 면 WARNING 을 남기고 계속합니다.

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine   # 7.0 이상이면 된다
DEBUG=false uv run uvicorn main:app --port 8000
curl http://127.0.0.1:8000/health      # {"status":"healthy","version":"0.1.0"}
```

```powershell
$env:DEBUG = "false"
uv run uvicorn main:app --port 8000
Remove-Item Env:DEBUG      # 끝나면 개발 기본값으로 복원
```

| 이 상태에서 | 결과 | 이유 |
|---|---|---|
| `GET /health` | 200 | DB 를 건드리지 않는다 |
| `GET /ready` | 503 | writer DB 의 `SELECT 1` 이 실패한다 (DB 와 Redis 가 모두 응답해야 200) |
| 기능 API (`/api/v1/...`) | 500 | MySQL 이 필요하다 |
| `/docs`, `/openapi.json` | 404 | `DEBUG=false` 가 문서를 끈다 |

`DEBUG=true`(기본값)면 기동 때 테이블 자동 생성을 시도하므로 MySQL 이 없으면 startup 이 실패합니다.
**API 문서를 켜는 스위치와 MySQL 을 요구하는 스위치가 같다**는 점이 첫 실행에서 가장 헷갈립니다.
DB 없이 구조만 볼 때는 `ADMIN_DISABLED=true`, `ACCESS_LOG_ENABLED=false` 도 함께 고려합니다.

### 3. MySQL 을 더해 기능 API·문서까지

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD='<.env 의 MYSQL_PASSWORD 와 같은 값>' \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8
uv run uvicorn main:app --reload --port 8000
```

기본 설정(`MYSQL_HOST=localhost`, 사용자 `root`, `fastapi_db`)에 맞춘 **로컬 전용** 예시입니다. 빈
비밀번호는 개발 환경에서도 설정 검사가 거부하므로 비밀번호를 지정합니다. 직접 만든 MySQL 이라면 `CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE
utf8mb4_unicode_ci;` 로 데이터베이스를 먼저 만듭니다(자동 생성은 테이블만 만듭니다).
`python main.py` 로 실행하면 `SERVER_HOST`·`SERVER_PORT`(기본 `0.0.0.0:8000`)와 `DEBUG` 에 따른 reload 를
씁니다.

| 주소 | 조건 |
|---|---|
| http://localhost:8000/docs (Scalar) · `/openapi.json` | `DEBUG=true` |
| http://localhost:8000/admin | `ADMIN_DISABLED=false`(기본). **슈퍼유저 로그인 필요** — [첫 관리자 만들기](#첫-관리자-만들기) |
| http://localhost:8000/health · `/ready` | 항상 |

### 스키마 관리 — 자동 생성에서 Alembic 으로

스키마를 만드는 경로는 **둘** 이고, 어느 쪽을 쓸지는 시점이 정합니다.

| 경로 | 언제 | 동작 |
|---|---|---|
| `create_db_tables()` | 개발 초기 | `DEBUG=true` 일 때 기동마다 실행. `Base.metadata` 의 테이블 중 **없는 것만** 만든다 |
| Alembic | 그 이후 전부 | `alembic upgrade head`. 변경 이력이 파일로 남고 되돌릴 수 있다 |

**개발 초기에는 자동 생성을 씁니다.** 모델을 하루에도 몇 번씩 바꾸는 단계에서는 DB 를 지우고 다시
띄우는 것이 가장 빠른 마이그레이션입니다. `DEBUG=true` 로 그냥 띄우면 됩니다.

**잃으면 안 되는 데이터가 처음 들어오는 순간 Alembic 으로 넘어갑니다.** 팀원이 합류했거나, 스테이징에
배포했거나, 지우면 곤란한 시드가 쌓였다면 이미 그 시점입니다.

```bash
# 1. 지금 스키마를 첫 revision 으로 못박는다
uv run alembic revision --autogenerate -m "baseline"
uv run alembic upgrade head

# 2. 이후 모델을 바꿀 때마다 (생성된 파일은 사람이 검토한다)
uv run alembic revision --autogenerate -m "무엇을 바꿨는지"
uv run alembic upgrade head
```

> **전환 후에는 `DEBUG=false` 로 둡니다.** `create_db_tables()` 는 이미 있는 테이블을 건드리지 않아
> 컬럼 변경은 모른 척합니다. 위험한 것은 새 모델입니다 — 자동 생성이 **마이그레이션 없이 테이블을
> 만들어 버리고**, Alembic 이력과 실제 DB 가 갈라져 배포 뒤 "운영에만 테이블이 없다" 로 드러납니다.

**처음부터 Alembic 을 써도 됩니다.** 코드나 설정을 바꿀 필요가 없습니다. `create_db_tables()` 는
SQLAlchemy `create_all` 이고 `checkfirst=True` 로 이미 있는 테이블을 건너뛰므로, Alembic 을 먼저
적용하면 기동 시 자동 생성은 no-op 입니다.

```bash
uv run alembic revision --autogenerate -m "initial"
uv run alembic upgrade head
uv run uvicorn main:app --reload     # DEBUG=true 여도 자동 생성은 할 일이 없다
```

다만 모델을 추가하고 revision 없이 서버를 띄우면 자동 생성이 그 테이블을 먼저 만듭니다. Alembic 을
쓰기로 했다면 `DEBUG=false` 가 가장 확실합니다 — 자동 생성 경로 자체가 실행되지 않습니다.

**여러 worker 로 띄운다면** (`uvicorn --workers N`, gunicorn) 각 프로세스가 이 경로를 돌아 동시 DDL 이
됩니다. 지원하는 기동 방식은 `python main.py` / `uvicorn main:app` 단일 프로세스이고, 다중 worker 는
`DEBUG=false` + Alembic 이 유일한 안전한 조합입니다. 현재 revision 체인과 `env.py` 동작은
[ARCHITECTURE §12](docs/guides/ARCHITECTURE.md), 작성 절차는
[개발 가이드 §10](docs/guides/DEVELOPMENT.md)에 있습니다.

### 테스트

단위 테스트는 SQLite 와 가짜 Redis 를 쓰므로 외부 인프라 없이 돕니다. pytest 설정이 `DEBUG=true`·
`ENV=test` 를 주입하고 `tests/` 와 `app/features/*/tests/` 를 함께 수집합니다.

```bash
uv run python -m pytest                       # 전체 (mysql 마커는 MySQL 이 없으면 skip)
uv run ruff check . && uv run mypy .
uv run python -m scripts.review_gate --list   # 게이트 그룹: static tests structure supply docs deps
uv run python -m scripts.review_gate --group static structure docs
```

`mysql` 마커 테스트(`tests/integration/`)는 MySQL 8.4 가 `127.0.0.1:3310` 에 있어야 돕니다
(`MYSQL_TEST_PORT` 로 변경). 같은 파일의 `redis-test` 는 lifespan·`/ready` 를 실물로 볼 때 쓰는
Redis 7.4 입니다(최소 요구 7.0 이상인 고정 이미지. `127.0.0.1:6381`, `REDIS_TEST_PORT` 로 변경 — 앱이 쓰게
하려면 `REDIS_PORT` 도 같은 값으로). 단위 테스트는 가짜 클라이언트를 주입하므로 Redis 없이 돕니다.

```bash
docker compose -f compose.test.yaml up -d --wait
uv run python -m pytest -m mysql
docker compose -f compose.test.yaml down -v
```

`uv run pytest` 대신 `python -m pytest` 를 씁니다(콘솔 스크립트가 다른 인터프리터를 집은 전례).
**커버리지**는 CI 의 단위 테스트 단계와 `tests` 게이트가 `--cov=app --cov-config=pyproject.toml --cov-report=term-missing` 으로 측정·출력합니다.
하한은 `pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나가 정하고 **기본값은 0**(하한 없음)입니다 —
처음에는 기능이 제대로 동작하는지 확인하는 것이 우선이라서입니다. 하한이 필요해지면 그 값 하나만 올립니다
(명령줄 `--cov-fail-under` 는 쓰지 않는다. 올리는 법은 [개발 가이드 §11](docs/guides/DEVELOPMENT.md)).
`tests` 게이트는 skip 0 을 요구하므로 MySQL 이 필요하고, `deps` 게이트는 네트워크가 필요합니다. CI 는
gate job(`-m "not mysql"`)과 MySQL job(`compose.test.yaml` + `-m mysql` + 전체 suite)으로 나뉩니다.

---

## 환경 설정

전체 목록과 설명은 [`.env.example`](.env.example) 에 있습니다(`config.py` 와의 일치를 테스트가
강제합니다). 처음에 의미 있는 것은 이 정도입니다.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `DEBUG` | `true` | 개발 모드 — 아래 표 |
| `ENV` | `development` | `development`/`test`/`staging`/`production`. 로그 구성과 배포 게이트가 따른다 |
| `ADMIN_DISABLED` | `false` | `true` 면 `/admin` 을 아예 만들지 않는다(404, 응답·로그에 경로 없음). `false` 면 마운트하고 **슈퍼유저 로그인**을 요구한다 (DEBUG 와 독립). 예전 `ADMIN` 은 이 설정으로 바뀌었고 남아 있으면 기동하지 않는다 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `localhost` / `6379` / `0` / 없음 | startup `ping()`·버전(7.0 이상) 확인 대상, Celery broker |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `3306` / `root` / `""` / `fastapi_db` | primary(writer) DB |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` / `MYSQL_REPLICA_HOSTS` | `false` / `false` / `[]` | replica 라우팅 (선택). read-only 세션의 쓰기 차단은 이 설정과 **무관하게** 항상 동작한다 |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` / `SESSION_SECRET_KEY` | `change-this-...` | JWT 서명 키 둘과 `/admin` 세션 쿠키 서명 키. 배포 전 서로 다른 값으로 교체 — 생성: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ALLOW_ORIGINS` | `["*"]` | JSON 배열로 지정 |
| `TRUSTED_PROXY_HOPS` | `0` | 앱 앞의 신뢰 리버스 프록시 수. `0` 은 전달 헤더 무시, `N` 은 X-Forwarded-For 의 오른쪽에서 N번째를 접속 IP 로 사용. **프록시 뒤 배포면 반드시 설정**(운영 배포 확인 4) |
| `ACCESS_LOG_ENABLED` | `true` | 접속 로그 수집 |
| `LOG_LEVEL` / `LOG_CONSOLE_LEVEL` | 미설정 | 미설정이면 DEBUG 에 따라 DEBUG/INFO |
| `SERVER_HOST` / `SERVER_PORT` | `0.0.0.0` / `8000` | `python main.py` 직접 실행 시 바인딩 |

| 동작 | `DEBUG=true` | `DEBUG=false` |
|---|---|---|
| 기본 로그 레벨 | DEBUG | INFO |
| 테이블 자동 생성 | 실행 (없는 테이블만) | 안 함 (Alembic) |
| `/docs`, `/openapi.json` | 켜짐 | 404 |
| `python main.py` reload | 켜짐 | 꺼짐 |
| 500 응답 상세 | 숨김 | 숨김 |

`SESSION_SECRET_KEY` 는 `/admin` 세션 쿠키 서명에, `SESSION_COOKIE_NAME` 은 접속 로그의 session_id 기록에만
쓰입니다(API 인증은 JWT 만). `SESSION_EXPIRE_SECONDS`·`SMTP_*`·`UPLOAD_*`·`API_VERSION` 은 설정만 있고
이를 쓰는 기능은 아직 없습니다. 설정 로딩
순서와 클래스별 소비 지점, 로그 구성은 [ARCHITECTURE §4·§5](docs/guides/ARCHITECTURE.md)를 봅니다.

---

## 운영 배포

**앱이 막는 것.** `config.py` import 마지막의 설정 검사가 아래에 해당하면 **기동을 거부**하고 위반을
한 번에 보여 줍니다(메시지에는 설정 이름만). `ENV=test` 는 검사하지 않습니다.

| 검사 | 적용 ENV |
|---|---|
| `.env` 가 없고 `ENV`·비밀 키 3종·`MYSQL_HOST/USER/PASSWORD/DATABASE` 가 환경 변수로도 없음(`validate_env_source`) | test 외 전부 |
| placeholder 인 access/refresh/session 키(앞뒤 공백 제거·소문자화 후 `change-this` 를 포함하거나 `your-` 로 시작하거나 빈 값 — `config.is_placeholder_secret`), 32자 미만, access 와 refresh 가 같음. `.env.example` 의 키 예시는 일부러 이 규칙에 걸린다 | test 외 전부 |
| placeholder 인 `MYSQL_PASSWORD`(**빈 값 포함** — 무인증 DB 계정). `REDIS_PASSWORD`·`SMTP_PASSWORD` 는 빈 값이 정당한 구성이라 값이 있을 때만 검사한다 | test 외 전부 |
| 예전 설정 `ADMIN` 이 `.env`·환경 변수에 남아 있음(`validate_renamed_settings` — `ADMIN_DISABLED` 로 바뀌었고 의미가 반대) | test 외 전부 |
| `DEBUG=true` · `CORS_ALLOW_ORIGINS` 의 `*` · `LOG_SQL_ECHO_ENABLED=true` · `LOG_LEVEL=DEBUG`(롤백 상세에 SQL 본문과 바인딩된 값이 남는다) | staging·production |

**사람이 확인할 것.**

| # | 확인 | 이유 |
|---|---|---|
| 1 | `ENV` 를 실제 환경 값으로 넘겼는가 | 기본값 `development` 에서는 위 표의 staging·production 검사가 돌지 않는다. `.env` 없이 환경 변수로 주입하는 배포는 `ENV` 가 없으면 기동 거부 |
| 2 | 트래픽 전환 전에 `alembic upgrade head` 를 적용했는가 | 서버 기동은 migration 을 하지 않는다 |
| 2a | 첫 관리자를 만들었는가 — `scripts/create_superuser.py`(대화형 또는 `--password-stdin`, [첫 관리자 만들기](#첫-관리자-만들기)) | 관리 API(사용자·상품 쓰기·리포트·접속 로그)는 슈퍼유저 전용이고 API 로는 첫 슈퍼유저를 만들 수 없다. 이 계정이 `/admin` 로그인 계정이기도 하다 |
| 2b | 관리 화면을 쓰는가 — 쓰지 않으면 `ADMIN_DISABLED=true`. 쓰면 `/admin` 이 **슈퍼유저 로그인**을 요구하고 세션 쿠키 서명 키가 `SESSION_SECRET_KEY` 임을 확인했는가 | 끄면 `/admin` 경로·링크·로그가 모두 사라진다. 켜면 로그인 세션은 `SESSION_SECRET_KEY` 로 서명되고 staging/production 에서 Secure 쿠키라 HTTPS 가 필요하다. 키를 바꾸면 관리 세션이 모두 끊긴다([admin 인증 안내서](docs/guides/admin-auth-guide.html)) |
| 3 | 외부 노출이 필요 없으면 `SERVER_HOST=127.0.0.1` 인가 | 기본 바인딩은 `0.0.0.0` 이다. 관리 화면을 켰다면 프록시·방화벽으로 `/admin` 접근 범위를 좁히는 것도 권장한다 |
| 4 | 프록시 뒤라면 `TRUSTED_PROXY_HOPS` 를 앞단 프록시 단 수로 설정했는가 | `0` 이면 모든 클라이언트가 프록시 IP 하나로 보여 접속 로그와 로그인 rate limit(API·`/admin`)이 전체 사용자를 한 사람으로 취급한다. 실제보다 크게 잡으면 IP 위조가 가능하다 |
| 4a | Redis 가 **7.0 이상**인가 | rate limit 이 `EXPIRE … NX`(7.0)를 쓴다. 낮으면 기동이 멈춘다. 관리형 Redis 가 `INFO` 를 막으면 확인을 건너뛰고 WARNING 만 남기므로(`Redis 버전 확인 불가`) 그때는 운영자가 버전을 직접 확인한다 |
| 5 | readiness 를 `/ready` 에 걸었는가 | `/ready` 는 DB 와 Redis 를 모두 본다(각 2초). `/health` 는 둘 다 보지 않는다 |
| 6 | 새로 더한 엔드포인트가 [권한 표](#권한-표)에 분류됐는가 | 예제 API 는 인증·소유권·슈퍼유저 검사를 갖췄다. 새 엔드포인트는 직접 보호해야 하고, 분류하지 않으면 `tests/test_authorization.py` 가 실패한다 |
| 7 | 기존 MySQL 데이터가 있다면 `e5a7c9d1f3b5`(KST→UTC 시각 전환) 적용 **전에 백업**하고, 그 시각이 `+09:00`(Asia/Seoul 벽시계)으로 저장됐는지 확인했는가 | 리비전이 `+09:00 → UTC` 로 옮긴다. 다른 시간대로 쌓인 DB 는 적용 전에 리비전의 `_LOCAL_OFFSET` 상수를 그 오프셋으로 바꾼다([ARCHITECTURE §12](docs/guides/ARCHITECTURE.md)) |

**`/admin` 은 슈퍼유저 로그인이 필요합니다.** SQLAdmin 에 붙인 `AdminAuthBackend` 가 활성 슈퍼유저만
들여보내고(매 요청 DB 확인 — 강등·비활성화는 다음 요청부터 막힌다), 로그인 시도는 API 로그인과 같은
한도로 따로 셉니다(`admin:rl:`). 세션은 `/admin` 전용 서명 쿠키(`admin_session`, `Path=/admin`,
`SameSite=Strict`, HttpOnly, 8시간, staging/production 은 Secure)이고 API 인증에는 쓰이지 않습니다.
관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true` 로 경로 자체를 없앱니다. 설계·흐름·위협 모델은
[admin 인증 안내서](docs/guides/admin-auth-guide.html), 보안 경계 전체는 [ARCHITECTURE §10](docs/guides/ARCHITECTURE.md)
에 있습니다.

---

## API

`app.openapi()` 실측 **22 경로 / 37 오퍼레이션**입니다. 경로를 바꾸면 이 표와
`tests/test_route_inventory.py` 를 함께 갱신합니다. 목록은 `skip`·`limit` 페이지 조회, 생성은 201,
삭제는 204 입니다.

| 기능 | 메서드 | 경로 |
|---|---|---|
| 블로그 `blog` | GET · POST | `/api/v1/blog/posts` |
| | GET · PATCH · DELETE | `/api/v1/blog/posts/{post_id}` |
| 댓글 `reply` | GET · POST | `/api/v1/reply/replies` |
| | GET · PATCH · DELETE | `/api/v1/reply/replies/{reply_id}` |
| SNS `sns` | GET · POST | `/api/v1/sns/posts` |
| | GET · PATCH · DELETE | `/api/v1/sns/posts/{post_id}` |
| 사용자 `user` | GET · POST | `/api/v1/user/users` |
| | GET · PATCH · DELETE | `/api/v1/user/users/{user_id}` |
| 상품 `catalog` (ORM 예제) | GET · POST | `/api/v1/catalog/products` |
| | GET · PATCH · DELETE | `/api/v1/catalog/products/{product_id}` |
| 매출 `reports` (Raw 예제) | GET | `/api/v1/reports/sales/daily?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` |
| 접속 로그 `home` | GET | `/api/v1/home/access-logs` (목록) · `/recent` · `/by-ip/{ip_address}` · `/by-user/{user_id}` · `/stats` |
| 인증 `auth` | POST | `/api/v1/auth/register` (JSON, 201 · 사용자명 중복 409 · 초과 429) |
| | POST | `/api/v1/auth/login` (**form-urlencoded**, 200 · 불일치 401 · 초과 429) |
| | POST | `/api/v1/auth/refresh` (JSON `{"refresh_token": ...}`, 200 · 무효·재사용 401) |
| | POST | `/api/v1/auth/logout` (JSON `{"refresh_token": ...}`, 204 · 무효 401) |
| | GET | `/api/v1/auth/me` (Bearer access 토큰) |
| 공통 | GET | `/health` (liveness) · `/ready` (DB·Redis readiness, 실패 503) |

`/api/v1/home/access-logs/stats` 는 `{total_count, device_types[], os_list[], browsers[]}` 를 돌려줍니다.
모든 오류는 `{"error_code", "message", "detail"}` 형식이고, 처리되지 않은 예외는 `DEBUG` 와 무관하게
고정 메시지의 500 입니다. HTTP 예외가 실어 온 헤더는 본문 형식을 바꿔도 그대로 실립니다 — 허용되지 않은
메서드의 405 는 `Allow`(예: `DELETE /health` → `Allow: GET`), 401 은 `WWW-Authenticate`, 429 는 `Retry-After`.

### 권한 표

권한은 **슈퍼유저/일반 2단계**입니다. 공개 = 토큰 없이, 인증 = 로그인한 누구나, 소유자 = 작성자 본인(사용자
리소스는 본인) 또는 슈퍼유저, 관리자 = 슈퍼유저 전용. 토큰이 없거나 만료·위조면 401, 권한이 없으면 403
입니다. 같은 표가 `tests/test_authorization.py` 의 `POLICY` 로 고정돼 있어 분류되지 않은 새 엔드포인트는
테스트가 막습니다.

| 엔드포인트 | 공개 | 인증 | 소유자 | 관리자 |
|---|---|---|---|---|
| `GET /health` · `GET /ready` | ● | | | |
| `POST /api/v1/auth/register` · `/login` · `/refresh` · `/logout` | ● | | | |
| `GET /api/v1/auth/me` | | ● | | |
| `GET` blog·sns·reply 목록·단건 (`/api/v1/blog/posts[/{post_id}]` 등) | ● | | | |
| `POST` blog·sns·reply (작성자는 로그인 사용자로 기록) | | ● | | |
| `PATCH` · `DELETE` blog·sns·reply 단건 | | | ● | |
| `GET /api/v1/catalog/products[/{product_id}]` | ● | | | |
| `POST` · `PATCH` · `DELETE` catalog | | | | ● |
| `GET /api/v1/reports/sales/daily` | | | | ● |
| `GET /api/v1/home/access-logs*` (5개) | | | | ● |
| `GET` · `POST /api/v1/user/users` (목록·생성 — 생성은 비밀번호 필수) | | | | ● |
| `GET` · `PATCH /api/v1/user/users/{user_id}` (`is_active`·`is_superuser` 변경은 관리자만) | | | ● | |
| `DELETE /api/v1/user/users/{user_id}` | | | | ● |

- blog·sns·reply 의 `author`·`author_id` 는 서버가 로그인 사용자로 채웁니다. 요청 본문의 `author` 는
  무시되고 수정할 수 없습니다. 작성자 컬럼이 생기기 전의 글(`author_id` 가 null)은 관리자만 고칩니다.
- 사용자를 비활성화·강등·삭제하면 그 사용자의 refresh 토큰이 모두 폐기됩니다. 이미 발급된 access
  토큰은 만료(기본 15분)까지 남습니다 — 권한은 토큰의 `su` claim 으로 판정하고 DB 를 다시 보지 않습니다.
- `/admin`(SQLAdmin)은 이 표와 별개로 **슈퍼유저 로그인**(서명 세션 쿠키)을 요구합니다. API 의 Bearer
  토큰으로는 들어갈 수 없고, 관리 세션 쿠키로 API 를 호출할 수도 없습니다([운영 배포](#운영-배포)).

### 인증 흐름

```bash
# 1) 가입 — 비밀번호 8자 이상
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'

# 2) 로그인 — OAuth2 password flow 규격이라 form 전송 (curl -d 기본값)
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer","expires_in":900}

# 3) 보호 엔드포인트
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'

# 4) 재발급(회전) — access·refresh 를 둘 다 새로 받는다. 쓴 refresh 는 다시 쓸 수 없다
curl -X POST localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' -d '{"refresh_token":"<refresh_token>"}'

# 5) 로그아웃 — 그 로그인 세션(family)의 refresh 를 모두 끊는다 (204)
curl -X POST localhost:8000/api/v1/auth/logout \
  -H 'Content-Type: application/json' -d '{"refresh_token":"<refresh_token>"}'
```

access 15분, refresh 7일(`ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`), 기본 HS256
(`JWT_ALGORITHM` 은 HS256/HS384/HS512 만)입니다. 토큰에는 `iss`·`aud`·`jti`·`nbf` 가 들어가고 검증 때
모두 확인합니다. access 토큰에는 사용자명과 슈퍼유저 여부(`su`)가 들어가며, 보호 엔드포인트는 DB 를
조회하지 않고 이 값으로 판정합니다. 토큰 종류가 섞이면 거부되고, 비활성 사용자는 로그인·재발급에서
막힙니다.

- **refresh 회전·재사용 탐지** — refresh 토큰은 한 번 쓰면 소비됩니다(Redis). 이미 쓴 토큰이 다시
  오면 탈취로 보고 그 로그인 세션(family)의 토큰을 모두 폐기합니다 — 정상 사용자도 다시 로그인해야
  합니다. access 토큰은 폐기 수단이 없어 만료까지 유효하므로 짧게 둡니다.
- **rate limit** — 로그인은 IP+사용자명 5회/60초·IP 20회/60초, 가입은 IP 5회/시간(`AUTH_*` 설정).
  `/admin` 로그인도 같은 로그인 한도를 쓰되 키를 따로 셉니다.
  초과하면 429 와 `Retry-After` 헤더. 로그인이 성공하면 IP+사용자명 카운터를 지웁니다. 프록시 뒤라면
  `TRUSTED_PROXY_HOPS` 를 맞추세요 — 0 이면 모든 사용자가 프록시 IP 하나로 함께 막힙니다.
- **비밀번호** — Argon2(pwdlib)로 저장합니다. 이전 버전의 bcrypt 해시는 로그인에 성공할 때 Argon2 로
  바꿔 저장합니다(점진 이전).

### 첫 관리자 만들기

가입(`/register`)은 항상 일반 사용자를 만들고, 관리자 API 는 관리자만 쓸 수 있으므로 첫 관리자는
운영 스크립트로 만듭니다(Django `createsuperuser` 와 같은 역할). `alembic upgrade head` 뒤에 실행합니다.

```bash
# 대화형 — 비밀번호를 두 번 묻는다(화면에 표시하지 않음)
uv run python -m scripts.create_superuser --username admin --email admin@example.com

# 자동화 — 표준 입력 한 줄에서 비밀번호를 읽는다(인자·셸 기록에 남기지 않는다)
printf '%s' "$ADMIN_PASSWORD" | uv run python -m scripts.create_superuser \
  --username admin --email admin@example.com --password-stdin

# 이미 있는 사용자를 관리자로 승격 — 비밀번호는 --set-password 를 줄 때만 바꾼다
uv run python -m scripts.create_superuser --username alice
```

스크립트는 API 와 같은 부품(`background_db_session`, core `get_password_hasher` 의 Argon2,
`UserRepository`)으로 조립하고 한 번 커밋합니다. 만든 계정으로 `/admin` 에도 로그인합니다
(`ADMIN_DISABLED=false` 일 때). 그 뒤의 관리자는 관리자가 `POST /api/v1/user/users`
(`"is_superuser": true`) 또는 `PATCH /api/v1/user/users/{user_id}` 로 만듭니다.

---

## 새 기능 추가

중앙 파일은 열지 않습니다.

1. **생성** — `uv run python -m scripts.new_app <name> [--with-admin]`. 이름은 파이썬 식별자여야 하고, 이미
   있는 앱은 덮어쓰지 않습니다(`--force` 로만). 생성기는 뼈대만 만듭니다.
2. **작성** — 데이터 접근 방식(ORM/Raw)을 정하고 모델·migration·스키마·Repository·Service·
   Dependency·엔드포인트·테스트를 씁니다. 라우터 변수명은 반드시 `<name>_router` 입니다.
3. **재시작** — 라우터가 `/api` 에, 모델이 `Base.metadata` 에, `admin_views` 가 SQLAdmin 에 붙습니다.

파일 순서·체크리스트·세션 선택·테스트는 [개발 가이드](docs/guides/DEVELOPMENT.md)에 있습니다.
Celery 태스크는 기능 폴더의 선택 모듈 `tasks.py` 에 둡니다. 워커가 registry 로 발견하므로 중앙 목록을
고치지 않고, 앱을 지우면 그 앱의 태스크도 워커에서 빠집니다.

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| `.env 파일이 없고, 필수 설정이 …` | `.env` 가 없다 | 빠른 시작 1단계. 컨테이너라면 메시지에 나온 환경 변수를 주입 |
| `ENV=development 에서 안전하지 않은 설정으로 기동할 수 없습니다` | `.env` 의 비밀 키·비밀번호가 예시 값·빈 값·32자 미만 | 빠른 시작 1단계 표대로 고친다 |
| `설정 ADMIN 은 ADMIN_DISABLED 로 바뀌었습니다` | `.env`·환경 변수에 예전 `ADMIN` 이 남아 있다 | 예전 값이 false 였다면 `ADMIN_DISABLED=true` 로, 아니면 그 줄을 지운다 |
| `/admin` 로그인 뒤 계속 로그인 화면으로 돌아온다 | staging/production 은 세션 쿠키가 Secure 라 HTTP 에서는 붙지 않는다. 또는 슈퍼유저가 아니거나 비활성 | HTTPS 로 접속(프록시의 TLS 종료 포함). 계정은 `scripts/create_superuser.py` 로 승격 |
| `/admin` 로그인이 429 | 로그인 시도 한도 초과(`AUTH_LOGIN_*`, 창 60초) | `Retry-After` 만큼 기다린다. 프록시 뒤인데 `TRUSTED_PROXY_HOPS` 가 0 이면 모든 사용자가 한 IP 로 묶인다 |
| startup 에서 `Redis 연결 실패` | Redis 미기동, 주소·포트·비밀번호 오류 | `REDIS_*` 와 서버 확인. `DEBUG=false` 로 우회되지 않는다 |
| startup 에서 `RedisVersionError: Redis x.y 은(는) 지원하지 않습니다` | Redis 가 7.0 미만 | 7.0 이상으로 올린다(rate limit 의 `EXPIRE … NX`) |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| staging/production 에서 `안전하지 않은 설정으로 기동할 수 없습니다` | 배포 게이트 | 메시지의 설정을 모두 고친다 ([운영 배포](#운영-배포)) |
| `/docs` 가 404 | `DEBUG=false` | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500, `/ready` 503 | 앱은 떴지만 DB 가 없다 | MySQL 준비 |
| 기능 API 는 정상인데 `/ready` 503 | 기동 뒤 Redis 가 끊겼다(로그 `[Readiness] Redis 점검 실패`) | Redis 상태·`REDIS_*` 확인 |
| 새 기능이 마운트되지 않음 | 디렉터리명이 식별자가 아니거나 `_` 로 시작, `__init__.py` 없음, 라우터 모듈 경로가 `api/routers/router.py` 가 아님(변수명이 틀린 경우는 아래 `AppContractError` 행) | [ARCHITECTURE §2](docs/guides/ARCHITECTURE.md). 파일 **안의** import 오류라면 조용히 넘어가지 않고 기동이 실패한다 |
| startup 에서 `AppContractError` | `router.py`/`admin.py` 의 export 가 규약과 다르거나 두 앱이 같은 객체를 내보냄 | 오류 메시지의 앱과 export 를 고친다 |
| 기동 INFO 로그가 안 보임 | `LOG_LEVEL`/`LOG_CONSOLE_LEVEL` 명시값이 우선 | [ARCHITECTURE §5](docs/guides/ARCHITECTURE.md) |

---

## 문서 안내

이 저장소의 문서 목록은 여기 하나뿐입니다. 위에서부터 읽는 순서입니다.

| 문서 | 역할 | 언제 보나 |
|---|---|---|
| 이 README | 개요 · 빠른 시작 · API 목록 · 운영 전 확인 · 문서 안내 | 처음 받았을 때 |
| [docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md) | 구조 · 런타임 동작 레퍼런스 — 앱 자동 등록, 설정·로깅, 기동·종료, 요청 처리, DB 세션·라우팅, 보안 경계 | 실행 중에 무엇이 어떻게 조립되는지 찾을 때 |
| [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md) | 기능 개발 가이드 — ORM/Raw 선택, 파일 순서, 세션·트랜잭션, migration, 테스트, 체크리스트 | 새 기능을 만들 때 |
| [docs/guides/server-lifecycle-guide.html](docs/guides/server-lifecycle-guide.html) | 서버 수명주기 안내서 — 설정 → 기동 → 요청 → 종료를 도식으로 추적 (브라우저로 연다) | 기동·종료 흐름을 한 번에 따라가 볼 때 |
| [docs/guides/feature-development-guide.html](docs/guides/feature-development-guide.html) | 신규 뷰·테이블 개발 안내서 — catalog·reports 요청을 따라가는 도식 설명 (브라우저로 연다) | 개발 가이드를 예제 흐름으로 익힐 때 |
| [docs/guides/admin-auth-guide.html](docs/guides/admin-auth-guide.html) | admin 인증 안내서 — `/admin` 로그인·세션 범위(관리 전용)·`ADMIN_DISABLED`·위협 모델·운영 (브라우저로 연다) | 관리 화면 인증을 이해하거나 바꿀 때 |
| [docs/specs/orm-raw-repository/requirements.md](docs/specs/orm-raw-repository/requirements.md) | 고정 기준선 — ORM/Raw 착수 요구명세 | 규칙의 원래 의도를 볼 때 |
| [docs/specs/orm-raw-repository/development-plan.md](docs/specs/orm-raw-repository/development-plan.md) | 고정 기준선 — ORM/Raw 개발 계획 | 규칙의 원래 의도를 볼 때 |
| [docs/specs/orm-raw-repository/workflow-guide.md](docs/specs/orm-raw-repository/workflow-guide.md) | 고정 기준선 — ORM/Raw 지침 원본 (코드 주석의 `workflow-guide §N` 출처) | 규칙의 원래 의도를 볼 때 |
| [docs/specs/django-style-app-automation.md](docs/specs/django-style-app-automation.md) | 고정 기준선 — 앱 자동 등록 요구사항(`FR-*`·`NFR-*`·`SEC-*` 등, 코드 주석이 인용)과 설계 근거 | 자동 등록 규칙의 원래 의도를 볼 때 |
| [docs/crp/groups/](docs/crp/groups/) | 검수 이력(append-only) — `orm-raw-repository`(ORM/Raw Base·예제·게이트), `runtime-lifecycle`(자원 정리·로깅 큐·Celery 워커), `docs-learnability`(이 문서 체계), `service-hardening`(인증·인가·rate limit·UTC), `admin-login`(관리 화면 로그인·`ADMIN_DISABLED`), `log-redaction-fixes`(traceback 마스킹·예외 헤더·Redis 최소 버전·커버리지 하한) | "이 코드가 왜 이렇게 생겼나" 를 추적할 때 |

`docs/guides/` 는 **현행 문서**라 코드 기준으로 유지하고, `review_gate` docs 그룹이 Markdown 의 백틱
경로와 HTML 의 `<code>` 경로·환경변수를 검사합니다. HTML 안내서는 흐름을 요약하고 표·목록의 원문은
Markdown 문서에 둡니다.

문서 유지 규칙:

- 코드와 문서가 다르면 **코드가 정답**입니다. 현행 문서를 고치고, 기준선(`docs/specs/`)과 이력
  (`docs/crp/`)의 내용은 고쳐 쓰지 않습니다(파일을 옮길 때의 경로 문자열만 예외).
- 한 주제는 한 문서가 소유합니다. 다른 문서는 링크만 겁니다.
- 정확히 `YYYY-MM-DD` 이름인 폴더는 로컬 작업 기록이라 `.gitignore` 가 제외합니다. 남길 내용은
  위 문서로 옮깁니다.
- 규칙 대부분은 문서가 아니라 **테스트가 강제**합니다. 학습 경로 자체도
  `tests/test_docs_learnability.py` 가 지킵니다(진입점·링크·예제 실재).

---

## 참고 자료

- [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/) ·
  [Pydantic v2](https://docs.pydantic.dev/latest/) · [Alembic](https://alembic.sqlalchemy.org/)

## 라이선스

MIT License
