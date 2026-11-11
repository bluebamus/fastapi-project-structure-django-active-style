# FastAPI Project Structure — Django Active Style

Django 의 `INSTALLED_APPS`·`startapp` 감각을 FastAPI 로 옮긴 프로젝트 골격입니다. 이 저장소가 보여 주려는 것은
**앱 자동 배선**입니다. `app/features/<name>/` 디렉터리를 만들면(직접 또는 `scripts/new_app.py` 로) 그 앱의
라우터·모델·관리 화면·Celery 태스크가 중앙 목록 없이 결선되고, `main.py`·`migrations/env.py`·관리 화면 조립부는
손대지 않습니다. 계약이 틀린 앱(라우터 이름 오타, `admin_views` 누락, 접근 수준을 선언하지 않은 뷰)은 조용히
빠지지 않고 기동을 멈춥니다.

그 밖의 골격: router → service → repository 계층, ORM(`BaseRepository`)과 Raw SQL(`RawRepositoryBase`) 두 가지
데이터 접근 예제, 읽기 전용/쓰기 세션 분리와 선택적 replica 라우팅, JWT 인증과 뷰 단위 접근 수준, 슈퍼유저 전용
SQLAdmin(`/admin`), 접속 로그 미들웨어, Celery 워커.

## 빠른 시작

필요한 것: [uv](https://docs.astral.sh/uv/), MySQL 8.x, Redis 7.0 이상. Python 은 `.python-version`(3.14)을
uv 가 맞춥니다(지원 하한 3.13).

```bash
uv sync                      # 의존성 설치(개발 도구 포함)
cp .env.example .env         # PowerShell: Copy-Item .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # 키 세 개를 각각 만들어 .env 에 넣는다
```

`.env` 에서 최소한 다음을 채웁니다.

| 설정 | 이유 |
|------|------|
| `ACCESS_TOKEN_SECRET_KEY`, `REFRESH_TOKEN_SECRET_KEY`, `SESSION_SECRET_KEY` | 예시 값(`change-this-...`)이거나 32자 미만이면 기동이 멈춥니다. access 와 refresh 키는 서로 달라야 합니다 |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | 빈 비밀번호·예시 비밀번호는 거부됩니다. 데이터베이스는 미리 만들어 둡니다 |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` | Redis 는 필수입니다(rate limit·refresh 토큰·관리 세션). 기동 때 연결과 버전(7.0+)을 확인합니다 |

로컬에서 MySQL 을 컨테이너로 띄운다면 예를 들어 이렇게 합니다(비밀번호는 `.env` 의 `MYSQL_PASSWORD` 와 같게).

```bash
docker run -d --name fastapi-mysql -p 3306:3306 -e MYSQL_ROOT_PASSWORD=<비밀번호> -e MYSQL_DATABASE=fastapi_db mysql:8.4
```

## 실행

```bash
uv run python main.py                      # SERVER_HOST:SERVER_PORT, DEBUG=true 면 reload
uv run uvicorn main:app --reload --port 8000
```

- `DEBUG=true`(개발 기본): 기동 때 모든 모델 테이블을 만들고(`create_all`), `/docs`(Scalar)·`/openapi.json` 을 엽니다.
- `DEBUG=false`: 테이블을 만들지 않으므로 먼저 `uv run alembic upgrade head` 를 적용합니다. API 문서는 닫힙니다.
- `GET /health` 는 프로세스 생존, `GET /ready` 는 DB·Redis 왕복까지 확인합니다(실패 시 503).
- 관리 화면 `/admin` 은 활성 슈퍼유저만 들어갑니다. 계정은 스크립트로 만듭니다.

```bash
uv run python -m scripts.create_superuser --username admin --email admin@example.com
```

Celery 워커와 스케줄러(접속 로그 집계, 매일 03:30 보존 기간 지난 접속 로그 삭제):

```bash
uv run celery -A app.celery.app:celery_app worker --loglevel=INFO   # Windows: --pool=solo 추가
uv run celery -A app.celery.app:celery_app beat --loglevel=INFO     # 배포마다 하나만
```

## 설정

설정은 `config.py` 의 Settings 클래스들이 `.env` 와 환경 변수에서 읽고, 전체 목록과 설명은 `.env.example` 에
있습니다. 기동 시 다음을 검사해 위반을 한 번에 모아 보고하고 멈춥니다.

- `.env` 가 없으면 `ENV`, 세 서명·세션 키, `MYSQL_HOST`·`MYSQL_USER`·`MYSQL_PASSWORD`·`MYSQL_DATABASE` 가 환경
  변수로 직접 와야 합니다(컨테이너 배포).
- 모든 ENV(test 제외): 예시·짧은·같은 키, 빈/예시 MySQL 비밀번호, 예시 Redis 비밀번호.
- `ENV=staging`·`production` 만: `DEBUG=true`, `CORS_ALLOW_ORIGINS` 의 `*`, `LOG_SQL_ECHO_ENABLED=true`,
  `LOG_LEVEL=DEBUG`.

배포 전에 특히 볼 값: 프록시 뒤라면 `TRUSTED_PROXY_HOPS`(앞단 프록시 수 — 클라이언트 IP·로그인 rate limit 의
기준), 관리 화면을 쓰지 않으면 `ADMIN_DISABLED=true`, 읽기 replica 를 쓰면 `DB_ROUTER_ENABLED`·
`DB_REPLICATION_ENABLED`·`MYSQL_REPLICA_HOSTS`.

## 테스트와 검증

테스트는 SQLite(aiosqlite)와 가짜 Redis(fakeredis)만 쓰므로 외부 서비스 없이 돕니다. pytest 설정이 `ENV=test`·
`DEBUG=true` 를 넣고 `tests/` 와 `app/features/*/tests/` 를 함께 수집합니다.

```bash
uv run python -m pytest                                  # 전체
uv run python -m scripts.review_gate --list              # 게이트 그룹 목록
uv run python -m scripts.review_gate --group static structure supply docs files deps
uv run python -m scripts.review_gate --group tests       # 커버리지 측정 + skip·xfail 0 확인
```

CI(`.github/workflows/ci.yml`)는 위 두 게이트 명령을 그대로 실행합니다. 게이트 구성은
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) 에 있습니다.

## 문서 안내

| 문서 | 내용 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 디렉터리 구조, 앱 자동 배선, 계층, DB 세션·라우팅, 인증·권한, 관리 화면, 미들웨어, 로깅, Celery, 수명주기 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 새 기능 추가, 테스트 구조와 작성 규칙, 마이그레이션, 게이트·CI |
