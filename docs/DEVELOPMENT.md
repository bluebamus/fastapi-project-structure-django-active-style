# 개발 안내

## 1. 새 기능 추가

```bash
uv run python -m scripts.new_app orders              # app/features/orders/ 생성
uv run python -m scripts.new_app orders --with-admin # admin.py 까지
```

`scripts/new_app.py` 가 만드는 구조:

```text
app/features/orders/
  __init__.py                 비워 둔다(import 부작용 금지)
  api/routers/router.py       orders_router — /api 아래 자동 마운트, v1 서브라우터를 /v1/orders 로 포함
  api/routers/v1/orders.py    접근 수준을 선언한 예시 뷰
  models/ schemas/ services/ repositories/ dependencies/ tests/
  admin.py                    (--with-admin) admin_views 목록
```

이미 있는 앱 이름은 거부합니다(`--force` 로 덮어쓰기). 생성 뒤 서버를 다시 띄우면 라우터가 붙습니다. `main.py`,
`migrations/env.py`, `app/features/admin.py`, `app/celery/app.py` 는 고치지 않습니다.

채우는 순서:

1. **모델** — `models/` 에 `Base` 와 `app/core/models/models_base.py` 의 mixin(UUID PK, `created_at`·`updated_at`
   — `UTCDateTime`)으로 정의합니다. 시각은 `timezone_settings.now()` 같은 UTC aware 값만 넣습니다.
2. **Repository** — 일반 CRUD 는 `BaseRepository[Model, str]` 를 상속하고 `model = ...` 만 둡니다
   (`app/features/catalog/repositories/product_repository.py`). 엔티티가 아닌 집계는 `RawRepositoryBase` 로 SQL 을
   모듈 상수에 두고 named bind 와 `query_name` 으로 실행합니다
   (`app/features/reports/repositories/sales_report_repository.py`). 요청 값으로 SQL 문자열을 조립하지 않습니다.
3. **Service** — `BaseService` 를 상속하고 Repository 를 만들어 씁니다. 수정·삭제에 소유권이 있으면
   `OwnershipPolicy` 를 생성자로 받습니다. 커밋은 하지 않고 `commit()` 만 노출합니다(`BaseService` 가 제공).
4. **Dependency** — 조회용은 `get_read_only_db_session`, 변경용은 `get_writer_db_session` 을 받아 Service 를
   조립만 합니다(`app/features/catalog/dependencies/catalog_dependencies.py`).
5. **View** — 뷰마다 `dependencies=[Public]` 같은 접근 수준을 선언합니다(선언이 없으면 기동이 멈춥니다). 로그인
   사용자가 필요하면 인자 `principal: CurrentPrincipal`. 쓰기 핸들러는 응답 전에 `await service.commit()` 을 한 번
   부릅니다 — 커밋 실패가 성공 응답으로 바뀌지 않게 하려는 것입니다.
6. **선택 모듈** — 관리 화면은 `admin.py` 의 `admin_views`, 부팅 훅은 `apps.py` 의 `ready()`(빠르고 멱등, I/O
   금지), Celery 태스크는 `tasks.py`(요청 밖이므로 `background_db_session()` 으로 세션을 엽니다).
7. **마이그레이션** — 아래 3절.

## 2. 테스트

### 구조

| 위치 | 대상 |
|------|------|
| `app/features/<name>/tests/` | 그 기능의 API 동작(상태 코드·검증·응답·권한·소유권·페이지네이션)과 트랜잭션 경계 |
| `tests/core/` | `app/core` — 레지스트리, DB 세션·라우터, repository Base, 보안, 미들웨어, 자원 수명주기, 마이그레이션 |
| `tests/utils/` | 로깅·페이지네이션 |
| `tests/scripts/` | `scripts/` 의 동작 |
| `tests/` 바로 아래 | 앱 전체 조립 — 자동 배선, 예외 처리기, 관리 화면, 권한 표, lifespan, Celery 브리지 |

공용 헬퍼: `tests/session_overrides.py`(운영 Dependency 와 같은 읽기 전용·writer 표시를 거는 세션 override),
`tests/auth_headers.py`(실제 `TokenService` 로 서명한 Bearer 헤더), `tests/core/conftest.py`(가짜 앱 패키지를 디스크에
만드는 `fake_app` 픽스처).

### 작성 규칙

- DB 는 `sqlite+aiosqlite:///:memory:`(StaticPool)에 `Base.metadata.create_all` 로 만들고, 세션 Dependency 는
  `app.dependency_overrides.update(session_overrides(maker))` 로 바꿉니다. 세션을 직접 yield 하는 override 를 새로
  쓰지 않습니다 — 읽기 전용 표시가 빠지면 조회 핸들러의 몰래 쓰기를 잡지 못합니다.
- Redis 는 fakeredis 를 `app.dependency_overrides[get_redis]` 나 `app.state.redis` 로 넣습니다. 실제 Redis·MySQL
  에 붙는 테스트는 두지 않습니다.
- 인증은 `get_current_principal` 을 override 하지 않고 `tests/auth_headers.py` 의 헤더를 보냅니다.
- 사용자가 관찰하는 동작이나 깨지면 사고가 나는 불변식을 검사합니다. 문서 문구·파일 위치·이름을 검사하는 테스트는
  쓰지 않습니다. 같은 동작을 여러 파일에서 중복 검사하지 않습니다.
- pytest 설정(`pyproject.toml`)은 `asyncio_mode = "auto"`, `--strict-markers`, `DeprecationWarning` 을 오류로 올립니다.
  skip·xfail 은 게이트가 실패로 판정하므로 쓰지 않습니다.

```bash
uv run python -m pytest app/features/catalog          # 한 기능
uv run python -m pytest tests/core -k registry        # 이름으로 고르기
```

### 커버리지

`tests` 게이트가 `--cov=app --cov-config=pyproject.toml --cov-report=term-missing` 으로 측정·출력합니다. 하한은
`pyproject.toml` 의 `[tool.coverage.report] fail_under` 하나가 정하며, 명령줄 `--cov-fail-under` 는 쓰지 않습니다.

## 3. 마이그레이션

`migrations/env.py` 는 런타임과 같은 `AppRegistry` 로 모든 앱의 모델을 import 해 `Base.metadata` 를 대상으로 삼고,
URL 은 `db_settings.ALEMBIC_URL` 에서 받습니다 — 기본은 primary DSN 의 드라이버를 `pymysql` 로 바꾼 것이고,
`ALEMBIC_DATABASE_URL` 을 주면 그 값을 씁니다. `UTCDateTime` 은 렌더 훅(`render_alembic_type`)이 MySQL
`DATETIME(6)` variant 로 적습니다.

```bash
uv run alembic revision --autogenerate -m "add orders"   # 모델 변경 후
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic heads                                     # head 가 하나인지
```

- 리비전은 `migrations/versions/0001_baseline_schema.py`(현재 전체 스키마) 다음으로 쌓입니다.
- autogenerate 결과는 반드시 읽고 고칩니다. 특히 SQLite 에 대고 만든 경우 server default 가 방언 문자열로 렌더될
  수 있으니 모델과 같은 표현(`sa.false()` 등)으로 바꿉니다.
- `tests/core/test_migrations.py` 가 빈 SQLite 에 `upgrade head` 후 모델과 차이가 없는지, `downgrade base` 뒤 테이블이
  남지 않는지 확인합니다. 모델만 바꾸고 리비전을 빠뜨리면 이 테스트가 실패합니다.
- 운영은 `DEBUG=false` 로 띄워 기동 시 `create_all` 을 끄고 Alembic 만 씁니다. 여러 worker 로 띄울 때도 마찬가지입니다
  (`DEBUG=true` 의 테이블 생성이 프로세스마다 동시에 돕니다).

## 4. 검증 게이트와 CI

`scripts/review_gate.py` 가 검사 목록과 판정을 소유하고, 로컬과 CI 가 같은 명령을 실행합니다.

| 그룹 | 내용 |
|------|------|
| `static` | `ruff check .`, `ruff format --check .`, `mypy .`, `bandit -ll -q -r app main.py config.py` |
| `tests` | 전체 pytest + 커버리지, `--collect-only`. 요약에 skipped·xfailed·xpassed·deselected 가 있으면 실패 |
| `structure` | `alembic heads` |
| `supply` | 워크플로의 Action 이 40자리 commit SHA 로 고정됐는지, 추적 파일에 비밀값처럼 보이는 문자열이 없는지 |
| `docs` | `README.md`·`docs/*.md`·워크플로가 백틱으로 적은 경로와 대입 형태(이름 뒤에 등호)로 적은 환경 변수가 실제로 있는지 |
| `files` | 내용 없는 `.py`(`__init__.py` 제외)가 없는지 |
| `deps` | `pip-audit --strict`(uv.lock 기준 취약점, 네트워크 필요) |

```bash
uv run python -m scripts.review_gate                  # 전체
uv run python -m scripts.review_gate --group static docs
```

CI(`.github/workflows/ci.yml`)는 push·PR·주 1회 일정에 `uv sync --locked` 뒤 `--group static structure supply docs
files deps` 와 `--group tests` 를 실행합니다. 의존성을 바꾸면 `uv lock` 으로 `uv.lock` 을 함께 갱신합니다.
