# Django 식 앱 자동 등록을 FastAPI 로 — 설계와 개발 내역

> **이 문서의 목적.** 이 저장소가 무엇을 위해 존재하고, 그 목적을 위해 어떤 설계 결정을
> 내렸으며, 실제로 무엇을 만들었는지 한 자리에 남긴다. 구조·사용법의 기준 문서는
> [`../../README.md`](../../README.md) 이고, 이 문서는 **"왜 이렇게 만들었는가"** 를 다룬다.
>
> 작성일: 2026-08-12 · 대상: `fastapi-project-structure-django-active-style`

---

## 1. 이 프로젝트가 풀려는 문제

FastAPI 로 프로젝트가 커지면 거의 예외 없이 같은 지점에서 마찰이 생긴다.

```python
# main.py — 앱이 늘어날수록 이 파일이 계속 자란다
from app.features.blog.api.routers.router import blog_router
from app.features.home.api.routers.router import home_router
from app.features.reply.api.routers.router import reply_router
from app.features.sns.api.routers.router import sns_router
from app.features.user.api.routers.router import user_router

app.include_router(blog_router, prefix="/api")
app.include_router(home_router, prefix="/api")
...
```

기능을 하나 추가할 때마다 **중앙 파일 세 곳**을 같이 고쳐야 한다.

| 고쳐야 하는 곳 | 빠뜨리면 생기는 일 |
|---|---|
| `main.py` 의 `include_router` | 엔드포인트가 통째로 안 뜬다 |
| Alembic `env.py` 의 모델 import | **마이그레이션에서 테이블이 조용히 누락된다** |
| Admin 등록 목록 | 관리 화면에서 그 모델만 사라진다 |

세 가지 모두 **에러 없이 조용히 실패**한다는 공통점이 있다. 특히 두 번째는 운영 배포
후에야 드러난다 — 실제로 이 저장소도 그 함정에 빠진 적이 있다(§5-1).

Django 는 앱 registry와 로딩 규약으로 모델·관리자 발견 문제를 풀었다. URL은 여전히
프로젝트 `urls.py`에서 명시적으로 `include()`해야 한다. **이 저장소는 Django의 앱
registry와 자동 모델·관리자 발견 아이디어를 FastAPI로 가져오고, 프로젝트 고유 규약으로
라우터 자동 등록까지 확장하되, 한 걸음 더 나아가 선언 목록조차 없앤다.** Django를
사용하거나 Django와 호환되는 구조가 아니라, Django의 앱 구성 방식을 참고한 FastAPI
전용 구조다.

> **핵심 명제:** `app/features/<name>/` 에 폴더가 존재한다는 사실 자체가 등록이다.

---

## 2. 설계 — 세 가지 결정

### 2-1. 발견(discovery)과 결선(wiring)을 분리한다

이 구조에서 가장 중요한 설계 결정이다. `AppRegistry` 는 두 가지 일을 하는데, 그 둘을
의도적으로 갈라 놓았다.

```
discover()  →  "어떤 앱이 있는가"     ← 저장소마다 다른 부분
install_*() →  "그 앱을 어떻게 엮는가"  ← 모든 저장소가 공유하는 부분
```

`app/core/registry.py:105` 의 `discover()` 는 `pkgutil.iter_modules` 로 `app.features`
직계 하위 패키지를 훑어 목록을 만든다. 언더스코어로 시작하는 것은 제외하고, 이름
알파벳순으로 정렬한다(발견 순서를 결정적으로 만들기 위해서다).

그 뒤의 `install_routers()` · `import_models()` · `install_admin()` 은 **목록의 출처를
전혀 모른다.** 목록만 받으면 컨벤션대로 엮는다.

이 분리 덕분에 자매 저장소 `passive-style` 은 `discover()` **한 메서드만** 갈아끼워
`config.INSTALLED_APPS` 목록을 읽는 Django 원본에 더 가까운 방식이 된다. 나머지 결선
로직은 두 저장소가 동일하다. 자동이냐 수동이냐는 철학의 차이처럼 보이지만, 코드
차원에서는 메서드 하나로 격리돼 있다.

### 2-2. 컨벤션을 최소한으로 정한다

발견된 앱에서 찾는 것은 넷뿐이다. 전부 **선택**이며, 없으면 건너뛴다.

| 경로 | 찾는 것 | 없으면 |
|---|---|---|
| `api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱 |
| `models/` | import 부수효과로 `Base.metadata` 등록 | 모델 없는 앱 |
| `admin.py` | `admin_views: list[type]` | 관리 화면 미노출 |
| `__init__.py` | import-time 부수효과 | 아무 일 없음 |

라우터 export 이름에는 `<name>_router`라는 단일 이름 규칙을 적용한다
(`registry.py:51`). `home` 앱이면 `home_router`다. 이와 별도로 위 표의 파일 경로와
export 형태도 자동 발견을 위한 구조 규약이다. 규약을 늘리지 않은 이유는 단순하다 —
규약이 많아질수록 "왜 안 붙지"를 디버깅할 지점도 같이 늘어난다.

### 2-3. `__init__.py` 를 확장 훅으로 쓴다

Django의 `AppConfig.ready()`와 **역할상 유사한 프로젝트 전용 초기화 훅**이다. 발견
과정에서 각 앱 패키지를 실제로 `import`하므로, `__init__.py`에 쓴 코드가 부팅 시점에
실행된다. 다만 앱 registry 준비 후 호출되는 Django의 공식 생명주기 훅과 달리, 이것은
Python 패키지 import 시점에 의존한다. 따라서 무거운 초기화나 DB 접근이 아니라 빠르고
멱등적인 등록 작업만 두어야 한다.

이 저장소는 그 자리를 **의존 방향을 뒤집지 않기 위해** 쓴다. `home` 앱은 접속 로그를 DB
에 저장해야 하는데, 그 저장을 수행하는 미들웨어는 `core` 에 있다. `core` 가 `home` 을
import 하면 `features → core` 의존 방향이 깨진다. 그래서 반대로 한다:

```python
# app/features/home/__init__.py
from app.features.home.access_log_sink import register_sink

register_sink()   # 부팅 시 core 미들웨어에 자신을 등록한다
```

`core` 는 `AccessLogSink` 라는 Protocol 과 등록 슬롯만 두고, 누가 채우는지 모른다
(`app/core/middlewares/access_log_sink.py`). 미들웨어는 슬롯이 비어 있으면 조용히
아무 일도 하지 않으므로, **`home` 앱이 없는 상태에서도 애플리케이션은 정상 동작한다.**

> **규칙: `core` 는 도메인을 모른다.** 도메인이 `core` 에 자신을 연결해야 할 때는 직접
> import 가 아니라 등록 훅을 통한다.

---

## 3. Django 대응표

| Django | 이 저장소 | 차이 |
|---|---|---|
| `INSTALLED_APPS` | **없음** — 디렉터리 존재가 곧 등록 | 선언조차 생략 |
| `AppConfig.ready()` | 앱 `__init__.py` 의 import-time 등록 훅 | 역할은 유사하나 생명주기 보장은 다름 |
| `startapp` | `scripts/new_app.py` | 생성 후 등록 단계 불필요 |
| `admin.py` + `admin.site.register` | `admin.py` 의 `admin_views` 리스트 | 전역 싱글턴 대신 명시적 리스트 |
| `models.py` 자동 발견 | `models/` import 로 `Base.metadata` 등록 | 동일 |
| `urls.py` include 체인 | `<name>_router` → `/api` 자동 마운트 | 중앙 URLconf 없음 |
| `settings.py` | `config.py` (Pydantic Settings) | 환경변수와 `.env` 접근을 한 설정 객체로 일원화 |

---

## 4. 부팅 흐름

`main.py` 는 한 줄이고, 조립은 전부 `create_app()` 안에서 일어난다
(`app/core/bootstrap.py:247`).

```
create_app()
  │
  ├─ registry.discover()        app/features/* 스캔 → 앱 목록 + 각 패키지 import
  │                             (이 시점에 __init__.py 훅이 실행된다)
  ├─ registry.import_models()   Base.metadata 채움
  │
  ├─ FastAPI(...)               문서·lifespan·직렬화 구성
  ├─ setup_user_info_middleware / CORS
  ├─ _register_exception_handlers()
  │
  ├─ registry.install_routers(app)     각 앱의 <name>_router → /api
  ├─ _add_health_and_docs(app)
  └─ ADMIN=true 일 때만 install_admin(admin)
```

**같은 발견 로직을 Alembic 도 쓴다.** `migrations/env.py` 가 `AppRegistry` 를 직접
호출해 모델을 모은다:

```python
_reg = AppRegistry()
_reg.discover()
_reg.import_models()
target_metadata = Base.metadata
```

이것이 §1 에서 말한 "세 곳 중 두 번째" 함정을 구조적으로 없애는 지점이다. 앱을 추가하면
런타임과 마이그레이션이 **같은 목록**을 보게 된다. 손으로 맞출 여지가 없다.

---

## 5. 개발 내역 — 목적을 지키기 위해 고친 것들

자동 등록 구조는 "안 해도 되는 일" 을 없애는 대신 **실패를 조용하게** 만드는 성향이
있다. 아래는 그 성향이 실제로 문제를 일으킨 지점과 대응이다. 이 저장소의 개발 내역은
대부분 여기에 해당한다.

### 5-1. 자동 발견인데 마이그레이션엔 테이블이 없었다

`env.py` 가 `AppRegistry` 를 쓰는데도 Alembic baseline 에는 `user_access_logs` 한 개만
있었다. 나머지 네 테이블(`users` · `blog_posts` · `replies` · `sns_posts`)이 빠져 있었다.
`DEBUG=true` 개발 환경에서는 `create_db_tables()` 가 메타데이터로 테이블을 만들어 주니
아무도 눈치채지 못했고, **운영 배포(`DEBUG=false`, Alembic 단독) 에서만 깨지는** 상태였다.

→ 기존 baseline이 외부 환경에 배포된 이력이 없는 개발용 템플릿임을 전제로 baseline에
네 테이블을 보정했다. 이미 배포된 migration이었다면 기존 revision을 바꾸지 않고 별도의
보정 revision을 추가해야 한다. 더불어 **빈 DB에 `upgrade head`를 실행한 결과와 ORM
메타데이터를 대조하는 회귀 테스트**(`tests/core/test_migration_chain.py`)를 두어, 같은
누락이 다시 생기면 테스트가 잡도록 했다.

### 5-2. 오타 한 줄이 앱을 통째로 사라지게 했다

선택 파일 판정을 `except ModuleNotFoundError` 하나로 하고 있었다. `admin.py` 는 있는데
그 안의 import 가 틀린 경우까지 같은 예외로 잡혀 **"선택 파일 없음"으로 삼켜졌다.**
서버는 에러 없이 뜨고, 그 앱의 관리 화면만 조용히 사라진다.

자동 발견 구조에서 특히 위험한 결함이다. 명시적 등록이라면 import 오류가 즉시
`main.py` 에서 터지지만, 여기서는 "선택 파일이니 없을 수도 있지" 와 구분되지 않는다.

→ `AppModule._import_optional()` 도입. `exc.name` 이 **찾던 바로 그 모듈**(또는 그 상위
패키지)일 때만 부재로 판정하고, 그 외에는 원래 예외를 그대로 올려 기동을 실패시킨다.

```python
except ModuleNotFoundError as exc:
    missing = exc.name
    if missing and (dotted == missing or dotted.startswith(f"{missing}.")):
        return None   # 선택 모듈 자체가 없다 — 정상
    raise             # 모듈 내부의 import 실패 — 숨기지 않는다
```

### 5-3. 생성기가 기존 앱을 덮어썼다

`scripts/new_app.py` 가 이름을 검사 없이 경로에 붙이고 `exist_ok=True` 로 만들었다.
같은 이름으로 다시 실행하면 작성해 둔 코드를 덮어썼고, 되돌릴 방법이 없었다.
`../` 를 주면 `app/features` 바깥에 파일이 생겼고, 하이픈이 든 이름은 **import 불가능한
패키지**를 만들어 자동 발견이 조용히 건너뛰게 했다.

→ stdlib `str.isidentifier()` + `keyword.iskeyword()` 로 이름 검증, `resolve()` 후 부모
경로 재확인, 기존 앱은 `FileExistsError`(`--force` 로만 덮어쓰기).

### 5-4. 그 외 — 자동 등록과 무관한 하드닝

목적과 직접 관련은 없지만 템플릿의 기본값으로서 고쳐 둔 것들이다.

| 항목 | 무엇이 문제였나 |
|---|---|
| DB 오류 누출 | 예외 `detail` 에 드라이버 원문이 담겨 **HTTP 응답으로 나갔다**. SQL·제약명·파라미터 값까지 노출 |
| 접근 로그 | `X-Forwarded-For` 를 무조건 신뢰해 **원격 IP 위조**가 가능했고, 쿼리 문자열을 통째로 저장해 토큰이 평문으로 쌓였다 |
| lifespan | 정리 코드가 `yield` 뒤에 평문으로 있어 **예외 종료 시 건너뛰었다**(로그 유실·커넥션 누수) |
| DB 라우팅 | `SELECT ... FOR UPDATE` 가 읽기 서버로 갈 수 있었다. 잠금이 엉뚱한 곳에 걸린다 |
| 관리자 페이지 | 인증이 없는데 기본값이 `true` 였다 → 기본 폐쇄로 전환 |

---

## 6. 의도적으로 하지 않은 것

템플릿이 무엇을 **제공하지 않는지**가 제공하는 것만큼 중요하다.

| 항목 | 이유 |
|---|---|
| **관리자 인증** | 최종 사양으로 두지 않기로 확정. `/admin`은 인증 없이 열리므로 기본값이 `false`다. 로컬 개발 또는 외부 인증 계층으로 보호된 환경에서만 명시적으로 켠다 |
| **API 인증(JWT)** | 별도 진행 예정. `config.py` 에 설정만 있고 구현은 없다. 접속 로그 미들웨어가 `request.state.user_id` 를 읽는 **연결점만** 미리 열어 두었다 |
| **인프라(Docker·nginx·배포)** | 별도 저장소 소관. 이 저장소는 FastAPI 코드와 설정만 담는다 |
| **중앙 등록 목록 도입** | 자동 발견이 이 저장소의 정체성이다. 명시 등록이 필요하면 자매 저장소 `passive-style` 을 쓴다 |

---

## 7. 이 구조를 쓸 때 알아둘 것

**장점이 그대로 함정이 되는 지점들이다.**

- **폴더를 만들면 즉시 활성화된다.** 실험용 앱을 `app/features/` 에 두면 다음 부팅에
  라우터가 붙는다. 임시 코드는 언더스코어로 시작하는 이름을 쓰면 제외된다(`_scratch`).
- **발견 순서는 알파벳순이다.** 앱 간 로딩 순서에 의존하는 코드를 쓰면 안 된다.
  `__init__.py` 훅은 서로 독립적이어야 한다.
- **`__init__.py` 는 부팅 경로다.** 여기에 무거운 작업이나 DB 접근을 넣으면 기동이
  느려지거나 실패한다. 재호출돼도 결과가 달라지지 않는 가벼운 등록·배선만 둔다.
- **앱 간 직접 import 금지.** 기능이 서로를 부르기 시작하면 자동 발견의 이점(독립적
  추가·제거)이 사라진다. 프레임워크·인프라 계약은 `core`, 도메인과 무관한 순수
  도구는 `utils`에 둔다. 여러 기능이 참여하는 업무 흐름은 무조건 `core`로 옮기지 말고
  명시적인 orchestration, port 또는 event 경계를 설계한다.
- **`ADMIN=true`는 인증을 활성화하지 않는다.** 이 템플릿의 `/admin`을 인터넷에 직접
  노출하는 운영 방식은 지원하지 않는다. 운영에서 필요하면 애플리케이션 또는 외부
  게이트웨이에 별도의 인증·인가 계층을 구현해야 한다.

---

## 8. 품질 게이트

자동 발견 구조는 "조용한 실패" 에 취약하므로 검증을 자동화해 두었다
(`.github/workflows/ci.yml`).

| 검사 | 무엇을 막는가 |
|---|---|
| `ruff check` / `ruff format --check` | 스타일·명백한 오류 |
| `mypy` (콜드 캐시) | 타입 불일치 |
| `bandit` MEDIUM+ | 보안 취약 패턴 |
| `pytest --strict-markers` | 기능 회귀 |
| **조용한 SKIP·xfail 0 판정** | "통과처럼 보이지만 실제로는 검사하지 않은" 테스트 |
| **alembic 단일 head + 빈 DB `upgrade head`** | §5-1 재발 |

검증 스냅샷(2026-08-12, 애플리케이션 기준 커밋 `404777a`): **222 passed** · ruff clean ·
mypy 135 files Success · bandit MEDIUM+ 0 · SKIP/xfail 0 · alembic 단일 head. 이 수치는
설계의 고정 속성이 아니라 당시 검증 결과이며, 최신 상태는 CI 결과를 기준으로 판단한다.

---

## 9. 요약

이 저장소는 **"앱을 추가할 때 중앙 파일을 고치지 않아도 되는 FastAPI 구조"** 를 보여주는
개발용 기본 템플릿이다. Django 의 앱 규약에서 아이디어를 가져왔고, 선언 목록마저 없애
디렉터리 존재를 등록으로 삼았다.

설계의 뼈대는 **발견과 결선의 분리** 하나다. 이 분리가 있어서 자매 저장소가 같은 결선
코드를 공유하면서 목록 출처만 바꿀 수 있고, Alembic 이 런타임과 같은 목록을 보게 되며,
컨벤션을 최소로 유지할 수 있다.

개발 내역의 대부분은 이 구조의 대가를 갚는 일이었다 — **자동이라서 조용해지는 실패를
시끄럽게 만드는 것.** import 오류를 숨기지 않고, 마이그레이션 누락을 테스트로 잡고,
생성기가 덮어쓰지 못하게 하는 작업들이 그것이다.

---

## 참고

- 구조·사용법 기준 문서: [`../../README.md`](../../README.md)
- 자동 발견 상세 흐름·도식: [`../concepts/auto-discovery-registry-2026-06-25.html`](../concepts/auto-discovery-registry-2026-06-25.html)
- 핵심 코드: `app/core/registry.py` · `app/core/bootstrap.py` · `migrations/env.py` · `scripts/new_app.py`
