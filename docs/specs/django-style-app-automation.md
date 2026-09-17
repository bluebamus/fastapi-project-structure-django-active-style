# Django 스타일 앱 자동 등록 — 요구사항·설계 근거 (기준선)

| 항목 | 값 |
|---|---|
| 작성 | 2026-08-12 (개념 문서 + 개발 명세), 2026-09-17 한 문서로 통합 |
| 성격 | **고정 기준선** — 자동 등록을 도입할 때 확정한 요구사항과 그 근거 |
| 인용 | 코드·테스트 주석의 `FR-*`·`CR-*`·`NFR-*`·`BC-*`·`SEC-*`·`AC-*` 가 이 문서의 ID 다 |
| 현행 동작 | [ARCHITECTURE §2](../guides/ARCHITECTURE.md) (코드와 다르면 코드가 정답) |

---

## 1. 풀려는 문제

FastAPI 프로젝트가 커지면 기능 하나를 추가할 때마다 **중앙 파일 세 곳**을 함께 고쳐야 한다.

| 고쳐야 하는 곳 | 빠뜨리면 |
|---|---|
| `main.py` 의 `include_router` | 엔드포인트가 통째로 안 뜬다 |
| Alembic `env.py` 의 모델 import | **마이그레이션에서 테이블이 조용히 빠진다** |
| Admin 등록 목록 | 관리 화면에서 그 모델만 사라진다 |

셋 다 **에러 없이 조용히 실패**한다. 특히 두 번째는 운영 배포 뒤에야 드러난다(§5.1).

Django 는 앱 registry 와 로딩 규약으로 모델·관리자 발견을 해결했지만 URL 은 여전히 `urls.py` 에서
`include()` 한다. 이 저장소는 Django 의 앱 registry 와 자동 발견 아이디어를 FastAPI 로 가져오고,
라우터 자동 등록까지 확장하며, **선언 목록(`INSTALLED_APPS`)마저 없앤다.**

> 핵심 명제: `app/features/<name>/` 에 폴더가 존재한다는 사실 자체가 등록이다.

Django 호환 계층이나 Django 기반 구현이 아니다. "Django 와 같은 동작" 은 **개발자가 앱을 추가했을 때
조립 결과가 같다**는 뜻이다.

## 2. 설계 결정

### 2.1 발견(discovery)과 결선(wiring)을 분리한다

```text
discover()  → "어떤 앱이 있는가"
install_*() → "그 앱을 어떻게 엮는가"
```

`discover()` 는 `pkgutil.iter_modules` 로 `app.features` 직계 하위 패키지를 훑어 언더스코어 시작을
빼고 이름순으로 정렬한다. 결선 메서드는 목록의 출처를 모른다. 이 분리 덕분에 런타임·Alembic·
테스트가 같은 규칙을 재사용하고, 목록의 출처가 바뀌어도(예: 명시 목록) 결선 코드는 그대로다.

### 2.2 규약을 최소로 둔다

찾는 것은 라우터(`<name>_router`)·모델 패키지·`admin_views`·초기화 훅뿐이고 전부 선택이다. 규약이
늘수록 "왜 안 붙지" 를 디버깅할 지점도 는다.

### 2.3 core 는 도메인을 모른다

core 미들웨어가 home 의 저장소를 import 하면 `features → core` 방향이 깨진다. 그래서 core 는
`AccessLogSink` Protocol 과 등록 슬롯만 두고, home 이 초기화 훅에서 자신을 등록한다. 슬롯이 비면
미들웨어는 아무것도 하지 않으므로 home 이 없어도 앱은 동작한다.

초기화 훅의 위치는 처음에 앱 `__init__.py` 의 import-time 부수효과였고, 2026-08-25 에 `apps.py` 의
`ready()` 를 `install_hooks()` 가 명시적으로 부르는 방식으로 바꿨다(`discover()` 부작용 0). import
부작용은 무슨 일이 일어나는지 코드에서 읽을 수 없고, 테스트 결과를 실행 순서에 묶기 때문이다.

### 2.4 Django 대응 범위

| Django 개념 | 대응 | 판정 |
|---|---|---|
| 앱 registry | `AppRegistry` 가 목록을 한 번 만들고 모든 결선에 제공 | 적용 |
| `AppConfig.ready()` | 앱 `apps.py` 의 `ready()` (빠르고 멱등, I/O 금지) | 역할 수준 대응 |
| 모델 발견 | 앱 `models` import 로 `Base.metadata` 구성 | 적용 |
| Admin 등록 | 앱 `admin.py` 의 `admin_views` 자동 수집 | 적용 |
| `startapp` | `python -m scripts.new_app <name>` | 적용 |
| URL 연결 | `<name>_router` 를 `/api` 에 자동 마운트 | Django 보다 확장된 규칙 |
| `INSTALLED_APPS` | 디렉터리 존재 자체가 등록 선언 | 의도적인 차이 |

## 3. 범위

**포함** — `app/features/*` 자동 발견, 결정적 정렬과 `_` 제외, 라우터·모델·Admin 의 공통 registry
결선, 가벼운 초기화 훅, 선택 모듈 부재와 내부 import 오류의 구분, 기존 모델 수집 경로의 registry
단일화(`models_registry` 는 위임 facade), 안전한 앱 scaffold, 기존 라우트·모델·Admin 목록 불변 검증,
README·개발 지침 갱신.

**제외** — API 인증·인가 정책, SQLAdmin 인증 정책·`ADMIN` 기본값, DB 라우팅, 접속 로그·CORS·예외
응답·lifespan, 기존 API·스키마·Repository·Service 로직, 의존성 업그레이드, 기존 Alembic revision
재작성, 배포 인프라, `app/features` 경로 변경.

## 4. 요구사항

- ID 는 구현·테스트·PR 에서 같은 이름으로 쓴다. 충족 여부는 구현 존재가 아니라 `AC-*` 의 관찰
  가능한 결과로 판정한다.
- 요구사항을 바꾸거나 빼면 코드만 고치지 않고 이 표의 ID·근거·인수조건을 함께 고친다.

### 4.1 기능 (`FR`)

| ID | 요구사항 | 검증 |
|---|---|---|
| `FR-01` | `app/features/` 직계 하위 Python 패키지를 중앙 선언 없이 앱으로 발견한다. | 가짜 앱·실제 앱 발견 목록 |
| `FR-02` | `api/routers/router.py` 가 있으면 `<name>_router: APIRouter` 를 `/api` 아래 자동 등록한다. | 임시 앱 라우터의 OpenAPI 경로 |
| `FR-03` | DEBUG 테이블 생성과 Alembic 이 같은 registry 경로로 모델을 import 한다. | `Base.metadata`, 빈 DB migration 결과 |
| `FR-04` | `ADMIN=true` 면 각 앱 `admin.py` 의 `admin_views` 를 중앙 목록 수정 없이 SQLAdmin 에 등록한다. | view inventory |
| `FR-05` | 가볍고 멱등적인 초기화 등록 훅을 결정적 순서로 한 번 실행한다. (현행: `install_hooks()` 가 `apps.ready()` 호출) | 재호출 결과·sink 등록 |
| `FR-06` | `python -m scripts.new_app <name>` 이 registry 규약을 만족하는 scaffold 를 만든다. | 임시 경로 생성·자동 발견 통합 |
| `FR-07` | 라우터·모델·Admin 은 선택 구성요소이며, 없다고 앱 전체가 실패하지 않는다. | 선택 조합별 fixture |
| `FR-08` | 앱을 추가·제거할 때 `main.py`, `migrations/env.py`, 중앙 Admin 목록을 편집하지 않는다. | 생성 전후 중앙 파일 diff |

### 4.2 Django 대응 (`CR`)

| ID | 요구사항 |
|---|---|
| `CR-01` | 기능 디렉터리를 라우터·모델·Admin·초기화 코드가 함께 움직이는 독립 앱 단위로 취급한다. |
| `CR-02` | 앱 생성 후 재시작하면 중앙 등록 없이 구성요소가 결선된다. |
| `CR-03` | registry 는 앱 목록을 먼저 확정하고 같은 목록을 라우터·모델·Admin 결선에 재사용한다. |
| `CR-04` | 초기화 훅을 Django `AppConfig.ready()` 와 같은 생명주기로 설명하지 않는다. |
| `CR-05` | Django URLconf 와 달리 `<name>_router` 자동 마운트를 제공한다는 차이를 문서화한다. Django 호환·기반으로 표기하지 않는다. |
| `CR-06` | `INSTALLED_APPS` 를 도입하지 않고 디렉터리 존재를 등록 선언으로 쓴다. |

### 4.3 비기능 (`NFR`)

| ID | 요구사항 | 검증 |
|---|---|---|
| `NFR-01` | 발견·결선 순서는 OS·파일시스템과 무관하게 앱 이름 알파벳순이다. | 비정렬 입력 순서 검사 |
| `NFR-02` | 언더스코어로 시작하는 패키지는 발견하지 않는다. | `_hidden` fixture |
| `NFR-03` | 선택 모듈 자체의 부재와 그 모듈 내부 import 실패를 구분하고, 내부 오류는 원인을 보존해 즉시 실패한다. | 구성요소별 `ModuleNotFoundError` |
| `NFR-04` | 모듈은 있는데 export 이름·타입이 틀리면 부재로 처리하지 않는다. | 잘못된 router·Admin export |
| `NFR-05` | `AppRegistry` 발견 목록을 결선의 단일 출처로 쓰고 두 번째 스캔 로직을 두지 않는다. | 호출 경로·구조 검사 |
| `NFR-06` | 초기화 훅은 빠르고 멱등이며 DB·네트워크 I/O 를 하지 않는다. | 훅 계약·재호출 테스트 |
| `NFR-07` | 구현 중에는 관련 테스트만, 병합 전에는 전체 품질 게이트를 실행한다. | 작업 기록·CI |

### 4.4 기존 동작 보존 (`BC`)

기준은 자동 등록을 도입하기 직전(2026-08-12)의 이 저장소 inventory 다.

| ID | 보존 요구사항 |
|---|---|
| `BC-01` | 기존 여섯 기능(auth·blog·home·reply·sns·user)의 API 경로·HTTP method·응답 계약 |
| `BC-02` | 기존 ORM 테이블과 Alembic migration chain (빈 DB `upgrade head`) |
| `BC-03` | 기존 SQLAdmin view 구성과 자격증명 비노출 계약 |
| `BC-04` | 인증·DB 세션·미들웨어 순서·예외 응답·문서·health 동작 |
| `BC-05` | 설정 키·의존성·`app/features/` 경로 |
| `BC-06` | 모델이 없는 `auth` 와 구성요소 일부가 없는 앱도 정상 부팅 |

### 4.5 보안·안전 (`SEC`)

| ID | 요구사항 | 검증 |
|---|---|---|
| `SEC-01` | `ADMIN=false` 에서는 `sqladmin` 과 기능 `admin.py` 를 로드하지 않는다. | 격리 프로세스의 `sys.modules` |
| `SEC-02` | scaffold 는 식별자가 아니거나 예약어인 이름을 거부한다. | 유효·무효 이름 parametrize |
| `SEC-03` | scaffold 는 resolve 된 경로로 `app/features` 밖 생성을 막는다. | `..`·구분자·경로 이탈 |
| `SEC-04` | scaffold 는 기존 앱 덮어쓰기를 기본 거부하고 `--force` 에서만 허용한다. | 재실행·기존 파일 보존 |
| `SEC-05` | 기준선 코드를 반영할 때 `.git`·로컬 `.env`·가상환경·cache·테스트 산출물을 가져오지 않는다. | tracked snapshot·secret scan |

### 4.6 인수조건 (`AC`)

| ID | 충족 조건 | 연결 |
|---|---|---|
| `AC-01` | 새 임시 앱을 만든 뒤 중앙 파일 수정 없이 재부팅하면 라우터가 OpenAPI 에 나타난다. | FR-01·02·06·08, CR-02 |
| `AC-02` | 모델을 가진 임시 앱의 테이블이 런타임 metadata 와 Alembic metadata 에 한 번씩 나타난다. | FR-03, CR-03, NFR-05 |
| `AC-03` | `ADMIN=true` 에서 임시 앱 view 가 한 번 등록되고, `ADMIN=false` 에서는 Admin 계층이 로드되지 않는다. | FR-04, SEC-01 |
| `AC-04` | 구성요소 없는 앱은 정상 발견되고, 존재하는 모듈의 내부 import 오류와 잘못된 export 는 즉시 실패한다. | FR-07, NFR-03·04 |
| `AC-05` | 같은 앱 집합을 반복 발견해도 순서·결선 결과가 같고 초기화 등록이 중복되지 않는다. | FR-05, NFR-01·02·06 |
| `AC-06` | 잘못된 이름·경로 이탈·기존 앱 재생성이 거부되고 기존 파일이 보존된다. | SEC-02~04 |
| `AC-07` | 도입 전과 비교해 route·table·Admin view·설정·의존성 inventory 에 비의도 차이가 없다. | BC-01~06 |
| `AC-08` | 관련 테스트와 병합 전 전체 게이트가 통과하고 skip·xfail 이 없다. | NFR-07 |
| `AC-09` | 문서가 Django 대응 범위와 차이, 앱 규약, 초기화 훅 제한, scaffold 사용법을 설명한다. | CR-01~06 |
| `AC-10` | 변경 diff 에 자동 앱 관리 범위 밖의 변경과 제외 파일이 없다. | §3, SEC-05 |

## 5. 개발 내역 — 조용한 실패를 시끄럽게

자동 등록은 "안 해도 되는 일" 을 없애는 대신 실패를 조용하게 만든다. 도입 과정의 수정 대부분이 그
대가를 갚는 일이었다.

### 5.1 자동 발견인데 마이그레이션에 테이블이 없었다

`env.py` 가 registry 를 쓰는데도 baseline 에는 `user_access_logs` 만 있었고 `users`·`blog_posts`·
`replies`·`sns_posts` 가 빠져 있었다. `DEBUG=true` 에서는 자동 생성이 가려 주어 운영
(`DEBUG=false`, Alembic 단독)에서만 깨지는 상태였다. 외부 배포 이력이 없는 개발용 baseline 이라
baseline 을 보정했고(배포된 migration 이었다면 보정 revision 을 추가해야 한다), 빈 DB `upgrade head`
결과와 ORM metadata 를 대조하는 `tests/core/test_migration_chain.py` 를 두었다.

### 5.2 오타 한 줄이 앱을 통째로 지웠다

선택 파일 판정을 `except ModuleNotFoundError` 하나로 하던 시절, `admin.py` 안의 잘못된 import 까지
"선택 파일 없음" 으로 삼켜졌다. 명시 등록이라면 즉시 터질 오류가 자동 발견에서는 부재와 구분되지
않는다. `AppModule._import_optional()` 이 `exc.name` 이 찾던 모듈(또는 상위 패키지)일 때만 부재로
보고, 그 밖에는 원래 예외를 다시 올린다. 관용 수집(`getattr(module, "admin_views", [])`)도 같은
이유로 버리고 `AppContractError` 로 바꿨다.

```python
except ModuleNotFoundError as exc:
    missing = exc.name
    if missing and (dotted == missing or dotted.startswith(f"{missing}.")):
        return None   # 선택 모듈 자체가 없다 — 정상
    raise             # 모듈 내부의 import 실패 — 숨기지 않는다
```

### 5.3 생성기가 기존 앱을 덮어썼다

이름을 검사 없이 경로에 붙이고 `exist_ok=True` 로 만들었다. 재실행하면 작성한 코드를 덮어썼고,
`../` 는 `app/features` 밖에 파일을 만들었고, 하이픈 이름은 import 할 수 없는 패키지를 만들어 발견이
조용히 건너뛰었다. `str.isidentifier()` + `keyword.iskeyword()` 검증, `resolve()` 후 부모 경로
재확인, 기존 앱은 `FileExistsError`(`--force` 로만 덮어쓰기)로 고쳤다.

## 6. 의도적으로 하지 않는 것

| 항목 | 이유 |
|---|---|
| 중앙 등록 목록(`INSTALLED_APPS`) | 디렉터리 존재가 등록이라는 것이 이 구조의 정체성이다 |
| SQLAdmin 인증 백엔드 | 영구 비목표로 확정. 대신 staging/production 에서 `ADMIN=true` 기동을 막는다 |
| 인프라(Docker 배포·nginx) | 이 저장소는 FastAPI 코드와 설정만 담는다 |
