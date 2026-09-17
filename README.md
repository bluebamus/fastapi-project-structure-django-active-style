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
- **JWT 인증** — OAuth2 password flow, access/refresh 토큰, bcrypt.
- **운영 안전장치** — staging/production 에서 위험한 설정이면 기동 거부, 오류 응답에 내부 정보 비노출,
  접속 로그 비동기 수집, 로그 비밀값 마스킹.
- **검증 게이트** — 로컬과 CI 가 같은 `scripts/review_gate.py` 로 정적 검사·테스트·공급망·문서를 판정.

## 기술 스택

| 구분 | 기술 |
|---|---|
| Framework | FastAPI 0.141 (Python 3.14, 최소 3.12) |
| ORM / DB | SQLAlchemy 2.0 async · MySQL(aiomysql) |
| Validation / Settings | Pydantic v2 · pydantic-settings |
| Migration | Alembic |
| Redis | startup 연결 검증(필수) · Celery broker/backend |
| Task Queue | Celery |
| Admin / API Docs | SQLAdmin · Scalar |
| Auth | OAuth2 Password + PyJWT + bcrypt |
| Tooling | uv · ruff · mypy · bandit · pytest · pip-audit |

## 구조 한눈에

```text
main.py            조립: 앱 자동 발견·결선 + 미들웨어·예외·문서·lifespan·Admin
config.py          설정 단일 출처 (Pydantic Settings) + 배포 안전 게이트
app/features/      기능 앱 — 디렉터리 존재 = 등록 선언
  auth · blog · catalog(ORM 예제) · home(접속 로그) · reply · reports(Raw 예제) · sns · user
app/core/          registry · db(세션·라우팅) · Base 모델/Repository/Service · 미들웨어 · 자원 관리
app/celery/        중앙 Celery 앱과 태스크
app/utils/         로깅 · JWT/bcrypt · 페이지네이션 · 검증
migrations/        Alembic (런타임과 같은 registry 로 모델 수집)
scripts/           new_app.py(앱 생성기) · review_gate.py(검증 게이트)
tests/             횡단 테스트 (기능 테스트는 app/features/<name>/tests/)
docs/              guides(현행) · specs(고정 기준선) · crp(검수 이력)
```

```text
요청 → 미들웨어(접속 로그·CORS) → Router → Depends(get_<name>_service) → Service(session) → Repository → DB
                                     └ 쓰기 핸들러가 응답 전에 await service.commit()
```

앱 등록 규약(찾는 파일 다섯 가지, 오류 정책, `apps.py` 의 `ready()` 훅, Django 대응 범위), 기동·종료
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

**→ 파일 순서·결과 API 의미·MySQL 검증까지: [docs/guides/orm-raw-workflow.md](docs/guides/orm-raw-workflow.md)**

---

## 빠른 시작

저장소 루트에서 실행합니다. 셸 예시는 Bash 기준이고, PowerShell 은 따로 적었습니다.

### 1. 설치

```bash
uv sync
cp .env.example .env        # PowerShell: Copy-Item -LiteralPath .env.example -Destination .env
```

`.env` 가 없어도 기본값으로 뜨지만 Redis·MySQL 주소가 기본값(localhost)이어야 합니다. 프로세스
환경변수가 `.env` 보다 우선하고, `.env.example` 은 자동으로 읽히지 않습니다. 이미 `.env` 가 있다면
덮어쓰지 말고 필요한 항목만 확인합니다.

### 2. Redis 만으로 HTTP 배선 확인

**Redis 는 항상 필요합니다.** 앱은 startup 에서 `REDIS_HOST`/`REDIS_PORT` 로 `ping()` 하고, 실패하면
시작하지 않습니다(`DEBUG=false` 로도 우회되지 않습니다).

```bash
docker run --rm -d --name fastapi-redis -p 6379:6379 redis:7-alpine
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
| `GET /ready` | 503 | writer DB 의 `SELECT 1` 이 실패한다 (Redis 는 보지 않는다) |
| 기능 API (`/api/v1/...`) | 500 | MySQL 이 필요하다 |
| `/docs`, `/openapi.json` | 404 | `DEBUG=false` 가 문서를 끈다 |

`DEBUG=true`(기본값)면 기동 때 테이블 자동 생성을 시도하므로 MySQL 이 없으면 startup 이 실패합니다.
**API 문서를 켜는 스위치와 MySQL 을 요구하는 스위치가 같다**는 점이 첫 실행에서 가장 헷갈립니다.
DB 없이 구조만 볼 때는 `ADMIN=false`, `ACCESS_LOG_ENABLED=false` 도 함께 고려합니다.

### 3. MySQL 을 더해 기능 API·문서까지

```bash
docker run -d --name fastapi-mysql -p 3306:3306 \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  -e MYSQL_DATABASE=fastapi_db \
  mysql:8
uv run uvicorn main:app --reload --port 8000
```

기본 설정(`MYSQL_HOST=localhost`, 사용자 `root`, 빈 비밀번호, `fastapi_db`)에 맞춘 **로컬 전용**
예시입니다. 직접 만든 MySQL 이라면 `CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE
utf8mb4_unicode_ci;` 로 데이터베이스를 먼저 만듭니다(자동 생성은 테이블만 만듭니다).
`python main.py` 로 실행하면 `SERVER_HOST`·`SERVER_PORT`(기본 `0.0.0.0:8000`)와 `DEBUG` 에 따른 reload 를
씁니다.

| 주소 | 조건 |
|---|---|
| http://localhost:8000/docs (Scalar) · `/openapi.json` | `DEBUG=true` |
| http://localhost:8000/admin | `ADMIN=true` (**인증 없음**) |
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
[개발 가이드 §10](docs/guides/orm-raw-workflow.md)에 있습니다.

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
(`MYSQL_TEST_PORT` 로 변경).

```bash
docker compose -f compose.test.yaml up -d --wait
uv run python -m pytest -m mysql
docker compose -f compose.test.yaml down -v
```

`uv run pytest` 대신 `python -m pytest` 를 씁니다(콘솔 스크립트가 다른 인터프리터를 집은 전례).
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
| `ADMIN` | `true` | `/admin` 마운트. **인증 없음** (DEBUG 와 독립) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `localhost` / `6379` / `0` / 없음 | startup `ping()` 대상, Celery broker |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | `localhost` / `3306` / `root` / `""` / `fastapi_db` | primary(writer) DB |
| `DB_ROUTER_ENABLED` / `DB_REPLICATION_ENABLED` / `MYSQL_REPLICA_HOSTS` | `false` / `false` / `[]` | 읽기/쓰기 분리 (선택) |
| `ACCESS_TOKEN_SECRET_KEY` / `REFRESH_TOKEN_SECRET_KEY` | `change-this-...` | JWT 서명 키. 배포 전 서로 다른 값으로 교체 |
| `CORS_ALLOW_ORIGINS` | `["*"]` | JSON 배열로 지정 |
| `TRUST_PROXY_HEADERS` | `false` | 리버스 프록시 뒤에서만 `true` — 접속 로그 IP 에 X-Forwarded-For 사용 |
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

`SESSION_*`·`SMTP_*`·`UPLOAD_*`·`API_VERSION` 은 설정만 있고 이를 쓰는 기능은 아직 없습니다. 설정 로딩
순서와 클래스별 소비 지점, 로그 구성은 [ARCHITECTURE §4·§5](docs/guides/ARCHITECTURE.md)를 봅니다.

---

## 운영 배포

**앱이 막는 것.** `ENV=staging` 또는 `ENV=production` 이면 `config.py` 의 `validate_deployment_safety()` 가
다음 중 하나라도 있으면 **기동을 거부**하고 위반을 한 번에 보여 줍니다.

- `DEBUG=true` · `ADMIN=true`
- `change-this-` 로 시작하는 access/refresh/session 키, 또는 access 와 refresh 키가 같음
- `CORS_ALLOW_ORIGINS` 의 `*` · `LOG_SQL_ECHO_ENABLED=true`

**사람이 확인할 것.**

| # | 확인 | 이유 |
|---|---|---|
| 1 | `ENV` 를 실제 환경 값으로 넘겼는가 | 기본값 `development` 에서는 위 게이트가 돌지 않는다 |
| 2 | 트래픽 전환 전에 `alembic upgrade head` 를 적용했는가 | 서버 기동은 migration 을 하지 않는다 |
| 3 | 외부 노출이 필요 없으면 `SERVER_HOST=127.0.0.1` 인가, 프록시·방화벽에서 `/admin` 을 막았는가 | 기본 바인딩은 `0.0.0.0` 이다 |
| 4 | 프록시 뒤라면 `TRUST_PROXY_HEADERS=true` 이고 프록시가 외부 전달 헤더를 지우는가 | 아니면 접속 로그 IP 가 위조되거나 프록시 IP 로 찍힌다 |
| 5 | readiness 는 `/ready`, Redis 는 별도로 감시하는가 | `/health` 는 DB·Redis 를 보지 않는다 |
| 6 | 공개할 CRUD 에 인가를 붙였는가 | 현재 예제 API 에는 인증·소유권 검사가 없다 |

**`/admin` 에는 인증이 없습니다.** 인증 백엔드는 붙이지 않기로 확정했고(영구 비목표), 기본값 `true` 는
로컬에서 바로 DB 를 들여다보기 위한 의도된 선택입니다. 켜져 있으면 도달 가능한 누구나 데이터를
조회·수정·삭제하고 CSV 로 내보낼 수 있습니다(비밀번호 해시만 제외). 개발 서버를 네트워크에 노출할
때는 `ADMIN=false` 를 둡니다. 보안 경계와 현재 한계 전체는 [ARCHITECTURE §10](docs/guides/ARCHITECTURE.md)
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
| 인증 `auth` | POST | `/api/v1/auth/register` (JSON, 201 · 사용자명 중복 409) |
| | POST | `/api/v1/auth/login` (**form-urlencoded**, 200 · 불일치 401) |
| | POST | `/api/v1/auth/refresh` (JSON `{"refresh_token": ...}`, 200 · 무효 401) |
| | GET | `/api/v1/auth/me` (Bearer access 토큰) |
| 공통 | GET | `/health` (liveness) · `/ready` (DB readiness, 실패 503) |

`/api/v1/home/access-logs/stats` 는 `{total_count, device_types[], os_list[], browsers[]}` 를 돌려줍니다.
모든 오류는 `{"error_code", "message", "detail"}` 형식이고, 처리되지 않은 예외는 `DEBUG` 와 무관하게
고정 메시지의 500 입니다.

### 인증 흐름

```bash
# 1) 가입 — 비밀번호 8자 이상
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@example.com","password":"secret-pw-1234"}'

# 2) 로그인 — OAuth2 password flow 규격이라 form 전송 (curl -d 기본값)
curl -X POST localhost:8000/api/v1/auth/login -d 'username=alice&password=secret-pw-1234'
# → {"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer"}

# 3) 보호 엔드포인트
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'

# 4) 재발급 — access·refresh 를 둘 다 새로 받는다
curl -X POST localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' -d '{"refresh_token":"<refresh_token>"}'
```

access 30분, refresh 7일(`ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`), HS256 입니다. 토큰 종류가
섞이면 거부되고, 비활성 사용자는 로그인·재발급에서 막힙니다. 서버 측 토큰 폐기 목록은 없어 유출된
refresh 토큰은 만료까지 유효합니다.

---

## 새 기능 추가

중앙 파일은 열지 않습니다.

1. **생성** — `uv run python -m scripts.new_app <name> [--with-admin]`. 이름은 파이썬 식별자여야 하고, 이미
   있는 앱은 덮어쓰지 않습니다(`--force` 로만). 생성기는 뼈대만 만듭니다.
2. **작성** — 데이터 접근 방식(ORM/Raw)을 정하고 모델·migration·스키마·Repository·Service·
   Dependency·엔드포인트·테스트를 씁니다. 라우터 변수명은 반드시 `<name>_router` 입니다.
3. **재시작** — 라우터가 `/api` 에, 모델이 `Base.metadata` 에, `admin_views` 가 SQLAdmin 에 붙습니다.

파일 순서·체크리스트·세션 선택·테스트는 [개발 가이드](docs/guides/orm-raw-workflow.md)에 있습니다.
Celery 태스크는 기능 폴더가 아니라 `app/celery/tasks.py` 에 둡니다.

---

## 자주 막히는 지점

| 증상 | 원인 | 조치 |
|---|---|---|
| startup 에서 `Redis 연결 실패` | Redis 미기동, 주소·포트·비밀번호 오류 | `REDIS_*` 와 서버 확인. `DEBUG=false` 로 우회되지 않는다 |
| startup 에서 `Can't connect to MySQL server` | `DEBUG=true` 기본값이 테이블 생성을 시도 | MySQL 을 띄우거나 `DEBUG=false` |
| staging/production 에서 `안전하지 않은 설정으로 기동할 수 없습니다` | 배포 게이트 | 메시지의 설정을 모두 고친다 ([운영 배포](#운영-배포)) |
| `/docs` 가 404 | `DEBUG=false` | `DEBUG=true` (MySQL 필요) |
| 기능 API 만 500, `/ready` 503 | 앱은 떴지만 DB 가 없다 | MySQL 준비 |
| 새 기능이 마운트되지 않음 | 디렉터리명이 식별자가 아니거나 `_` 로 시작, `__init__.py` 없음, 라우터 변수명이 `<name>_router` 가 아님 | [ARCHITECTURE §2](docs/guides/ARCHITECTURE.md). 파일 **안의** import 오류라면 조용히 넘어가지 않고 기동이 실패한다 |
| startup 에서 `AppContractError` | `router.py`/`admin.py` 의 export 가 규약과 다르거나 두 앱이 같은 객체를 내보냄 | 오류 메시지의 앱과 export 를 고친다 |
| 기동 INFO 로그가 안 보임 | `LOG_LEVEL`/`LOG_CONSOLE_LEVEL` 명시값이 우선 | [ARCHITECTURE §5](docs/guides/ARCHITECTURE.md) |

---

## 문서 안내

이 저장소의 문서 목록은 여기 하나뿐입니다.

| 순서 | 문서 | 무엇을 답하나 |
|---|---|---|
| 1 | 이 README | 무엇인가, 어떻게 띄우나, 어떤 API 가 있나, 운영 전에 무엇을 확인하나 |
| 2 | [docs/guides/orm-raw-workflow.md](docs/guides/orm-raw-workflow.md) | **새 기능을 어떻게 만드나** — ORM/Raw 선택, 파일 순서, 세션·트랜잭션, migration, 테스트 |
| 3 | [docs/guides/ARCHITECTURE.md](docs/guides/ARCHITECTURE.md) | **실행 중에 어떻게 조립되나** — 앱 자동 등록, 설정·로깅, 기동·종료, 요청 처리, DB 세션·라우팅, 보안 경계 |

| 경로 | 성격 | 언제 보나 |
|---|---|---|
| `docs/guides/` | **현행 문서.** 코드 기준으로 유지하고 `review_gate` docs 그룹이 경로·환경변수를 검사한다 | 개발할 때 |
| [docs/specs/django-style-app-automation.md](docs/specs/django-style-app-automation.md) | **고정 기준선.** 앱 자동 등록 요구사항(`FR-*`·`NFR-*`·`SEC-*` 등 — 코드 주석이 인용)과 설계 근거 | 규칙의 원래 의도를 볼 때 |
| [docs/specs/orm-raw-repository/](docs/specs/orm-raw-repository/) | **고정 기준선.** ORM/Raw 착수 명세 3종 — [requirements](docs/specs/orm-raw-repository/requirements.md) · [development-plan](docs/specs/orm-raw-repository/development-plan.md) · [workflow-guide](docs/specs/orm-raw-repository/workflow-guide.md) (코드 주석의 `workflow-guide §N` 출처) | 규칙의 원래 의도를 볼 때 |
| [docs/crp/](docs/crp/) | **검수 이력(append-only).** 그룹별 결함 대장·잔여 위험·라운드 로그 — `orm-raw-repository`(ORM/Raw Base·예제·게이트), `runtime-lifecycle`(자원 정리·로깅 큐·Celery 워커), `docs-learnability`(이 문서 체계) | "이 코드가 왜 이렇게 생겼나" 를 추적할 때 |

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
