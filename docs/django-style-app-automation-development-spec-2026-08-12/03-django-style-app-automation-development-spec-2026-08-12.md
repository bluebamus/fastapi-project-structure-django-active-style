# Django 스타일 앱 자동화 통합 계획

- 작성일: 2026-08-12
- 대상 저장소: `fastapi-project-structure-django-active-style`
- 기반 저장소: `fastapi-default-project-structure`
- 기반 코드 기준: `a980b71` (`fastapi-default-project-structure/main`)
- 자동화 참조 기준: `47384a9` (`fastapi-project-structure-django-active-style/main`)
- 설계 기준 문서: `docs/django-style-app-automation-development-spec-2026-08-12/02-django-style-app-discovery-concept-2026-08-12.md`
- 문서 성격: 분석·기획·설계·개발·브랜치 이관 계획

## 1. 목표

`fastapi-default-project-structure`의 현재 기능과 동작을 새 기준선으로 사용하고, 다음 Django 스타일 앱 자동화 기능만 추가한다.

1. `app/features/<name>/` 직계 하위 패키지를 앱으로 자동 발견한다.
2. 앱의 라우터를 중앙 `main.py` 수정 없이 자동 등록한다.
3. 앱의 모델을 런타임 테이블 생성과 Alembic에서 같은 규칙으로 자동 import한다.
4. 앱의 SQLAdmin 뷰를 중앙 목록 수정 없이 자동 등록한다.
5. 앱 패키지 초기화 훅을 결정적인 순서로 실행한다.
6. Django `startapp`에 대응하는 안전한 앱 scaffold 명령을 제공한다.
7. 선택 구성요소가 없는 정상 상태와 구성요소 내부 import 오류를 구분하여, 잘못된 앱을 조용히 누락시키지 않는다.

이 작업은 전체 프로젝트를 현재 `django-active-style` 코드로 교체하는 작업이 아니다. 기반 저장소의 인증, rate limit, 응답 직렬화, DB 세션, 미들웨어, API, 설정 및 운영 정책은 유지하고 앱 등록 자동화에 필요한 부분만 이식한다.

## 2. “Django와 동일한 동작”의 적용 범위

FastAPI와 Django는 공식 생명주기와 URL 조립 방식이 다르므로 프레임워크 내부 동작까지 동일하게 만들 수는 없다. 이 계획에서 동일 동작은 개발자가 앱을 추가하고 애플리케이션이 이를 조립하는 결과의 동등성을 뜻한다.

| Django 개념 | 이 프로젝트의 대응 동작 | 판정 |
|---|---|---|
| 앱 registry | `AppRegistry`가 앱 목록을 한 번 만들고 공통 결선에 제공 | 적용 |
| `AppConfig.ready()` | 앱 패키지 `__init__.py`의 빠르고 멱등적인 등록 훅 | 역할 수준 대응 |
| 모델 발견 | 앱 `models` import로 `Base.metadata` 구성 | 적용 |
| Admin 등록 | 앱 `admin.py`의 `admin_views` 자동 수집 | 적용 |
| `startapp` | `python -m scripts.new_app <name>` | 적용 |
| URL 연결 | `<name>_router`를 `/api`에 자동 마운트 | Django보다 확장된 프로젝트 규칙 |
| `INSTALLED_APPS` | 디렉터리 존재 자체가 등록 선언 | 의도적인 차이 |

따라서 이 결과물을 Django 호환 계층이나 Django 기반 구현이라고 설명하지 않는다. 목표는 Django의 앱 단위 응집도와 registry 개념을 FastAPI 조립 과정에 맞게 구현하는 것이다.

## 3. 현행 분석

### 3.1 기반 저장소 상태

`fastapi-default-project-structure/main`의 `a980b71` 기준으로 다음 상태를 확인했다.

| 영역 | 현재 방식 | 자동화 적용 후 |
|---|---|---|
| 라우터 | `main.py`가 `auth`, `blog`, `home`, `reply`, `sns`, `user`를 직접 import하고 `include_router` 호출 | registry가 기능별 `<name>_router`를 자동 마운트 |
| 모델 | `app/core/db/models_registry.py`가 `models/models.py`를 별도 스캔 | 앱 registry 목록을 모델 import의 단일 출처로 사용 |
| Alembic | `models_registry.import_all_models()` 호출 | `AppRegistry.discover()`와 `import_models()` 호출 |
| Admin | `app/features/admin.py`의 명시 import와 `ADMIN_VIEWS` 중앙 목록 | `ADMIN=true`일 때만 각 앱의 `admin.py`를 자동 수집 |
| 앱 생성기 | 없음 | 안전한 `scripts/new_app.py` 추가 |
| 기능 루트 | `app/features/` | 그대로 유지 |

기반 저장소는 모델 수집만 부분 자동화되어 있다. 라우터와 Admin은 새 앱을 추가할 때 중앙 파일을 수정해야 하므로 프로젝트 목적을 완전히 충족하지 않는다.

### 3.2 참조 저장소 상태

`fastapi-project-structure-django-active-style/main`의 `47384a9`에는 자동 발견 registry, 런타임·Alembic 모델 연결, 라우터·Admin 자동 등록 및 scaffold가 존재한다. 다만 해당 main은 `app/domains/`를 사용하고, 현재 검수 문서는 `app/features/`와 더 엄격한 import 오류 처리 및 scaffold 안전성을 기준으로 한다.

적용 우선순위는 다음과 같다.

1. 검수 완료된 개념 문서의 계약
2. 대상 저장소 main의 자동화 구조와 조립 방식
3. 현재 작업 브랜치에서 자동화 자체에 직접 해당하는 결함 수정
4. 기반 저장소의 기존 기능과 공개 동작

대상 저장소의 DB routing, access log, lifespan, 오류 응답, CI 강화 등은 자동 앱 등록과 독립적인 변경이므로 이 작업에 함께 가져오지 않는다.

## 4. 범위

### 4.1 포함

- `app/features/*` 자동 발견
- 결정적인 앱 정렬과 언더스코어 시작 패키지 제외
- 라우터, 모델, Admin의 공통 registry 결선
- 앱 패키지 import를 통한 가벼운 초기화 훅
- 선택 모듈 부재와 내부 import 오류의 엄격한 구분
- 기존 `models_registry` 사용처의 registry 기반 단일화
- 안전한 앱 scaffold와 관련 테스트
- 기존 라우트·모델·Admin 목록 불변 검증
- README와 개발 지침의 앱 추가 절차 갱신

### 4.2 제외

- API 인증·인가 정책 변경
- SQLAdmin 인증 정책 또는 `ADMIN` 기본값 변경
- DB read/write routing 변경
- access log, CORS, 예외 응답, lifespan 변경
- 기존 API, schema, repository, service 로직 변경
- 패키지 의존성 업그레이드
- Alembic 기존 revision 내용 재작성
- 배포 인프라 변경
- `app/features`를 `app/domains`로 재명명

## 5. 요구사항 정의

### 5.1 요구사항 관리 원칙

- 요구사항 ID는 구현·테스트·PR에서 동일하게 사용한다.
- `필수` 요구사항은 main 병합 전에 모두 충족해야 한다.
- 요구사항을 변경하거나 제외할 때는 코드만 바꾸지 않고 이 문서의 ID, 근거, 인수조건을 함께 갱신한다.
- “Django와 동일한 동작”은 아래 `CR-*`에서 정한 사용자 관점의 결과 동등성을 의미한다.
- 요구사항 충족 여부는 구현 존재가 아니라 `AC-*`의 관찰 가능한 결과로 판정한다.

요구사항 분류는 다음과 같다.

| 접두사 | 분류 | 의미 |
|---|---|---|
| `FR-*` | 기능 | 앱 자동 발견·결선·생성 기능 |
| `CR-*` | Django 대응 | Django 앱 관리 방식과의 대응 범위 및 의도적 차이 |
| `NFR-*` | 비기능 | 결정성, 오류 가시성, 단일 출처, 실행 특성 |
| `BC-*` | 기존 동작 보존 | 기반 저장소에서 바뀌면 안 되는 계약 |
| `SEC-*` | 보안·안전 | Admin 지연 로딩, 경로 이탈 및 덮어쓰기 방지 |
| `AC-*` | 인수조건 | 요구사항 완료를 판정하는 검증 가능한 결과 |

### 5.2 기능 요구사항

| ID | 우선순위 | 요구사항 | 검증 개요 |
|---|---|---|---|
| `FR-01` | 필수 | 시스템은 `app/features/` 직계 하위의 Python 패키지를 별도 중앙 선언 없이 앱으로 발견해야 한다. | fake app 및 실제 앱 발견 목록 비교 |
| `FR-02` | 필수 | 발견된 앱에 `api/routers/router.py`가 있으면 `<name>_router: APIRouter`를 `/api` 아래 자동 등록해야 한다. | 임시 앱 라우터의 OpenAPI 경로 확인 |
| `FR-03` | 필수 | 발견된 앱의 모델을 DEBUG 테이블 생성과 Alembic이 동일한 registry 경로로 import해야 한다. | `Base.metadata`, 빈 DB migration 결과 비교 |
| `FR-04` | 필수 | `ADMIN=true`이면 각 앱 `admin.py`의 `admin_views`를 중앙 목록 수정 없이 SQLAdmin에 등록해야 한다. | 등록 view inventory 및 신규 앱 view 확인 |
| `FR-05` | 필수 | 발견 과정은 앱 패키지를 import하여 가볍고 멱등적인 초기화 등록 훅을 실행해야 한다. | import 횟수·재호출 결과 및 sink 등록 검사 |
| `FR-06` | 필수 | `python -m scripts.new_app <name>`은 registry 규약을 만족하는 `app/features/<name>/` scaffold를 생성해야 한다. | 임시 경로 생성 결과와 자동 발견 통합 검사 |
| `FR-07` | 필수 | 라우터·모델·Admin은 선택 구성요소여야 하며 없는 구성요소 때문에 앱 전체가 실패해서는 안 된다. | 선택 구성요소 조합별 fixture 검사 |
| `FR-08` | 필수 | 앱을 추가하거나 제거할 때 `main.py`, `migrations/env.py`, 중앙 Admin 목록을 편집하지 않아야 한다. | 생성 전후 중앙 파일 diff 및 통합 검사 |

### 5.3 Django 대응 요구사항

| ID | 우선순위 | 요구사항 | 경계 |
|---|---|---|---|
| `CR-01` | 필수 | 기능 디렉터리를 라우터·모델·Admin·초기화 코드가 함께 이동하는 독립적인 앱 단위로 취급해야 한다. | Django 앱 단위 응집도에 대응 |
| `CR-02` | 필수 | 앱 생성 후 서버를 다시 시작하면 별도 중앙 등록 없이 사용 가능한 구성요소가 자동 결선되어야 한다. | 개발자 관점의 `startapp` 후 등록 결과 동등성 |
| `CR-03` | 필수 | registry는 앱 목록을 먼저 확정하고, 동일 목록을 라우터·모델·Admin 결선에 재사용해야 한다. | Django app registry 역할에 대응 |
| `CR-04` | 필수 | Python import 훅을 Django 공식 `AppConfig.ready()`와 동일한 생명주기로 설명해서는 안 된다. | 역할만 유사하며 실행 보장은 다름 |
| `CR-05` | 필수 | Django URLconf와 달리 이 프로젝트는 `<name>_router` 자동 마운트를 제공한다는 차이를 문서화해야 한다. | Django 호환 또는 Django 기반으로 표기 금지 |
| `CR-06` | 필수 | `INSTALLED_APPS`를 도입하지 않고 디렉터리 존재를 앱 등록 선언으로 사용해야 한다. | active-style의 핵심 의도 |

### 5.4 비기능 요구사항

| ID | 우선순위 | 요구사항 | 검증 개요 |
|---|---|---|---|
| `NFR-01` | 필수 | 앱 발견과 결선 순서는 운영체제·파일시스템 순서와 무관하게 앱 이름의 알파벳순이어야 한다. | 비정렬 입력에 대한 순서 검사 |
| `NFR-02` | 필수 | 언더스코어로 시작하는 패키지는 발견 대상에서 제외해야 한다. | `_scratch` fixture 제외 검사 |
| `NFR-03` | 필수 | 선택 모듈 자체의 부재와 그 모듈 내부 import 실패를 구분하고, 내부 오류는 원인을 보존하여 즉시 실패해야 한다. | 세 구성요소별 `ModuleNotFoundError` 검사 |
| `NFR-04` | 필수 | 모듈이 존재하지만 필수 export의 이름·타입이 잘못된 경우 선택 기능 부재로 처리하지 않아야 한다. | 잘못된 router·Admin export 실패 검사 |
| `NFR-05` | 필수 | `AppRegistry`의 발견 목록을 앱 결선의 단일 출처로 사용하고 독립적인 두 번째 스캔 로직을 두지 않아야 한다. | 호출 경로 및 코드 구조 검사 |
| `NFR-06` | 필수 | 앱 초기화 훅은 빠르고 멱등적이어야 하며 DB·네트워크 I/O를 수행하지 않아야 한다. | 훅 문서 계약과 재호출 테스트 |
| `NFR-07` | 필수 | 구현 중에는 관련 테스트만 우선 실행하고, 전체 품질 게이트는 기능 완성 및 main 병합 전에 실행해야 한다. | 작업 기록과 CI 결과 확인 |

### 5.5 기존 동작 보존 요구사항

| ID | 우선순위 | 보존 요구사항 | 비교 기준 |
|---|---|---|---|
| `BC-01` | 필수 | 기존 여섯 기능의 API 경로, HTTP method 및 응답 계약을 유지해야 한다. | 기반 commit `a980b71` OpenAPI inventory |
| `BC-02` | 필수 | 기존 ORM table과 Alembic migration chain을 유지해야 한다. | table inventory 및 빈 DB `upgrade head` |
| `BC-03` | 필수 | 기존 SQLAdmin model view의 구성과 자격증명 비노출 계약을 유지해야 한다. | Admin view inventory와 보안 테스트 |
| `BC-04` | 필수 | 인증, rate limit, DB 세션, 미들웨어 순서, 예외 응답, 문서 및 health endpoint 동작을 변경하지 않아야 한다. | 기존 회귀 테스트와 설정 비교 |
| `BC-05` | 필수 | 기반 저장소의 설정 키, 의존성 및 `app/features/` 경로를 유지해야 한다. | `pyproject.toml`, 설정 계약 및 경로 diff |
| `BC-06` | 필수 | 모델이 없는 `auth`와 구성요소 일부가 없는 앱도 정상 부팅되어야 한다. | 실제 `auth` 및 fake app 검사 |

### 5.6 보안·안전 요구사항

| ID | 우선순위 | 요구사항 | 검증 개요 |
|---|---|---|---|
| `SEC-01` | 필수 | `ADMIN=false`에서는 `sqladmin`과 기능별 `admin.py`를 로드하지 않아야 한다. | 격리 프로세스의 `sys.modules` 검사 |
| `SEC-02` | 필수 | scaffold는 Python 식별자가 아니거나 예약어인 앱 이름을 거부해야 한다. | 유효·무효 이름 parameterized test |
| `SEC-03` | 필수 | scaffold가 `app/features` 밖에 파일을 만들 수 없도록 resolve된 경로를 검증해야 한다. | `..`, 구분자 및 경로 이탈 검사 |
| `SEC-04` | 필수 | scaffold는 기존 앱 덮어쓰기를 기본 거부하고 명시적인 `--force`에서만 허용해야 한다. | 재실행 및 기존 파일 보존 검사 |
| `SEC-05` | 필수 | 기반 코드 이관 시 `.git`, 로컬 `.env`, 가상환경, cache 및 테스트 산출물을 복사하지 않아야 한다. | tracked snapshot manifest 및 secret scan |

### 5.7 인수조건

| ID | 충족 조건 | 연결 요구사항 |
|---|---|---|
| `AC-01` | 새 임시 앱을 생성한 뒤 중앙 파일을 수정하지 않아도 재부팅 시 라우터가 OpenAPI에 나타난다. | `FR-01`, `FR-02`, `FR-06`, `FR-08`, `CR-02` |
| `AC-02` | 모델을 가진 임시 앱의 table이 런타임 `Base.metadata`와 Alembic metadata 양쪽에 한 번씩 나타난다. | `FR-03`, `CR-03`, `NFR-05` |
| `AC-03` | `ADMIN=true`에서는 임시 앱 view가 한 번 등록되고 `ADMIN=false`에서는 Admin 계층이 로드되지 않는다. | `FR-04`, `SEC-01` |
| `AC-04` | 라우터·모델·Admin이 없는 앱은 정상 발견되며, 존재하는 모듈 내부 import 오류와 잘못된 export는 즉시 실패한다. | `FR-07`, `NFR-03`, `NFR-04` |
| `AC-05` | 동일 앱 집합을 반복 발견했을 때 순서와 결선 결과가 같고 초기화 등록이 중복되지 않는다. | `FR-05`, `NFR-01`, `NFR-02`, `NFR-06` |
| `AC-06` | 잘못된 이름·경로 이탈·기존 앱 재생성은 거부되고 기존 파일 내용이 보존된다. | `SEC-02`, `SEC-03`, `SEC-04` |
| `AC-07` | 기반 commit과 비교해 기존 route, table, Admin view, 설정·의존성 inventory에 비의도 차이가 없다. | `BC-01`~`BC-06` |
| `AC-08` | 관련 테스트와 main 병합 전 전체 품질 게이트가 모두 통과하며 skip·xfail이 없다. | `NFR-07` 및 전체 필수 요구사항 |
| `AC-09` | 문서가 Django 대응 범위와 차이, 앱 규약, 초기화 훅 제한 및 scaffold 사용법을 설명한다. | `CR-01`~`CR-06` |
| `AC-10` | 기능 브랜치 diff에 자동 앱 관리 범위 밖의 변경과 제외 파일이 포함되지 않는다. | 범위 절, `SEC-05` |

## 6. 설계

### 6.1 구성요소

```text
app/features/*
       |
       v
AppRegistry.discover()
       |
       +-- import_models() ----> Base.metadata ----> DEBUG create_all / Alembic
       +-- install_routers() --> FastAPI.include_router(..., prefix="/api")
       +-- install_admin() ----> SQLAdmin.add_view(...), ADMIN=true일 때만
       `-- package import -----> 가볍고 멱등적인 앱 초기화 훅
```

`AppRegistry`는 앱 목록의 단일 출처이고 `AppModule`은 앱 하나의 구성요소 로딩 규칙을 담당한다. 발견과 결선을 분리하여 런타임, Alembic, 테스트가 같은 규칙을 재사용하게 한다.

### 6.2 앱 규약

| 경로 | 계약 | 부재 시 동작 |
|---|---|---|
| `app/features/<name>/__init__.py` | 앱 패키지 및 선택적 초기화 훅 | 앱 패키지가 아니므로 발견하지 않음 |
| `api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱으로 정상 처리 |
| `models/__init__.py` | import 시 ORM 모델이 `Base.metadata`에 등록 | 모델 없는 앱으로 정상 처리 |
| `admin.py` | `admin_views: list[type]` | Admin 없는 앱으로 정상 처리 |

앱 이름은 Python 식별자이며 예약어가 아니어야 한다. 발견 순서는 앱 이름의 알파벳순으로 고정한다. `_scratch`처럼 언더스코어로 시작하는 패키지는 발견 대상에서 제외한다.

### 6.3 오류 정책

- 선택 모듈 자체가 없으면 정상적으로 건너뛴다.
- 선택 모듈 내부에서 다른 모듈 import가 실패하면 원래 `ModuleNotFoundError`를 다시 발생시킨다.
- 라우터 모듈은 있으나 `<name>_router`가 없거나 타입이 `APIRouter`가 아니면 기동 오류로 처리한다.
- `admin_views`가 존재하지만 list가 아니거나 항목이 SQLAdmin view 계약을 만족하지 않으면 등록 단계에서 실패시킨다.
- 동일 라우터 또는 Admin view의 중복 등록을 검사한다.
- 초기화 훅에는 DB I/O, 네트워크 I/O 및 무거운 작업을 두지 않는다.

현재 참조 구현의 관대한 `getattr(..., None)` 동작은 잘못된 export도 선택 기능 부재처럼 보이게 할 수 있다. 구현 단계에서는 “파일 부재는 선택, 잘못된 계약은 오류” 원칙을 테스트로 고정한다.

### 6.4 기반 저장소 보존 설계

- `main.py` 전체를 대상 저장소의 `bootstrap.py`로 교체하지 않는다.
- 기존 FastAPI 인스턴스, rate limiter, 예외 핸들러, 미들웨어 순서, 문서 및 health endpoint는 그대로 둔다.
- 명시적인 기능 import와 여섯 개 `include_router` 호출만 registry 호출로 교체한다.
- `app/features/admin.py`는 Admin 인터페이스 생성 책임을 유지하되 중앙 `ADMIN_VIEWS` 취합 책임만 registry로 넘긴다.
- `ADMIN=false`에서는 `sqladmin`과 기능별 `admin.py`가 로드되지 않는 기존 계약을 유지한다.
- `app/core/db/models_registry.py`는 즉시 삭제하지 않고, 초기 통합에서는 `AppRegistry`에 위임하는 호환 facade로 남긴다. 독립적인 두 번째 스캔 로직은 제거한다.
- `app/core/db/session.py`와 `migrations/env.py`는 같은 registry 모델 import 경로를 사용한다.
- 모델이 없는 `auth` 앱과 Admin이 없는 앱은 정상적으로 발견되고 필요한 구성요소만 연결된다.

## 7. 예상 변경 파일

| 구분 | 경로 | 작업 |
|---|---|---|
| 추가 | `app/core/registry.py` | `AppModule`, `AppRegistry`, 엄격한 선택 import 구현 |
| 수정 | `main.py` | 자동 발견, 모델 선등록, 라우터·Admin 자동 결선 |
| 수정 | `app/core/db/models_registry.py` | 독립 스캔 제거, registry 위임 호환 API 제공 |
| 수정 | `app/core/db/session.py` | 테이블 생성 전 registry 기반 모델 import |
| 수정 | `migrations/env.py` | Alembic metadata를 registry로 구성 |
| 수정 | `app/features/admin.py` | Admin 생성 책임 유지, 중앙 view 목록 제거 |
| 추가 | `scripts/__init__.py` | scaffold 모듈 패키지화 |
| 추가 | `scripts/new_app.py` | Django `startapp` 대응 생성기 |
| 추가 | `tests/core/_fakeapps/` | 라우터·모델·Admin 선택 조합 fixture |
| 추가 | `tests/core/test_registry_*.py` | 발견·결선·오류·중복 계약 검증 |
| 추가 | `tests/scripts/test_new_app*.py` | 생성 결과, 이름 검증, 경로 이탈·덮어쓰기 방지 |
| 수정 | `tests/test_router_registration.py` | 수동 등록 누락 검사를 자동 등록 계약 검사로 전환 |
| 수정 | `tests/test_admin_wiring.py` | 중앙 목록 계약을 registry 완전성 계약으로 전환 |
| 수정 | `tests/core/test_alembic_metadata.py` | registry와 metadata 일치 검증 |
| 수정 | `tests/core/test_migration_chain.py` | 호환 facade 또는 registry 경로 반영 |
| 수정 | `README.md` | 앱 생성·자동 등록 규약 및 제한 설명 |

실제 구현 중 파일 목록이 달라지면, 자동화 기능에 필요한 이유를 PR 설명에 기록한다. 예상 목록 밖의 비관련 파일 변경은 원칙적으로 되돌린다.

## 8. 개발 단계

### 단계 A. 기준선 동결과 차이 목록 작성

1. 두 저장소의 원격 상태를 갱신하고 기준 commit을 다시 확인한다.
2. 기반 저장소 `a980b71`의 tracked file 목록과 대상 저장소 main `47384a9`의 자동화 관련 파일 목록을 기록한다.
3. 대상 저장소의 현재 미커밋 문서 변경을 코드와 분리된 docs commit으로 보존한다.
4. main에 대한 복구 tag를 만든다.
5. 다음 불변 목록을 추출한다: OpenAPI 경로, SQLAlchemy table, SQLAdmin model view, 설정 키, 의존성 목록.

산출물은 source commit manifest와 before 스냅샷이다.

### 단계 B. 기반 코드 이관

1. 대상 저장소의 최신 main에서 `feature/default-base-django-app-automation` 브랜치를 만든다.
2. 별도 임시 디렉터리에 `fastapi-default-project-structure`의 `a980b71` tracked snapshot을 추출한다.
3. `.git`, cache, 가상환경, 로컬 `.env`, 테스트 산출물은 복사하지 않는다.
4. 대상 저장소의 검수 문서와 이 계획서는 보존한다.
5. 추출 snapshot과 대상 작업 트리를 manifest 기준으로 대조한 뒤 기반 코드를 반영한다.
6. 자동화 적용 전 기준선 commit을 만든다.

권장 commit:

```text
chore(base): sync fastapi-default-project-structure at a980b71
```

복사는 탐색기 전체 복사나 `.git` 중첩 방식으로 하지 않는다. tracked snapshot을 사용해야 원본 저장소의 cache와 로컬 비밀값이 섞이지 않고, 출처 commit을 재현할 수 있다.

### 단계 C. registry 핵심 구현

1. 대상 main의 `app/core/registry.py`를 참조하여 `app.features` 기준으로 이식한다.
2. 발견 순서, 언더스코어 제외, 앱 package import를 구현한다.
3. 선택 모듈 부재와 내부 import 오류를 구분한다.
4. 라우터 export와 Admin view 계약을 엄격하게 검증한다.
5. 발견·로딩·등록 단위 테스트를 먼저 통과시킨다.

권장 commit:

```text
feat(registry): add deterministic feature app discovery
```

### 단계 D. 애플리케이션 결선

1. `main.py`의 직접 기능 import와 `include_router` 목록을 registry로 교체한다.
2. 앱 생성 전에 모델 metadata를 채운다.
3. `ADMIN=true`일 때만 Admin 인터페이스를 만들고 registry가 view를 등록하게 한다.
4. `models_registry.py`, `session.py`, `migrations/env.py`가 같은 발견 규칙을 사용하게 한다.
5. 기존 인증·rate limit·미들웨어·예외·문서 동작이 변하지 않았는지 before 스냅샷과 비교한다.

권장 commit:

```text
refactor(wiring): register routers models and admin from app registry
```

### 단계 E. 앱 생성 자동화

1. `scripts/new_app.py`를 `app/features/<name>` 기준으로 이식한다.
2. Python 식별자·예약어·경로 이탈을 검증한다.
3. 기존 앱은 기본적으로 덮어쓰지 않고 명시적인 `--force`에서만 허용한다.
4. 생성되는 router export가 `<name>_router` 계약을 만족하게 한다.
5. `--with-admin`과 모델 없는 앱 조합을 검증한다.
6. 생성한 임시 앱이 중앙 파일 수정 없이 발견·마운트되는 통합 테스트를 추가한다.

권장 commit:

```text
feat(scaffold): add safe django-style app generator
```

### 단계 F. 문서와 회귀 계약 정리

1. README의 수동 `include_router`, 중앙 Admin 목록 수정 절차를 제거한다.
2. 앱 규약, 선택 구성요소, 초기화 훅 제한, scaffold 사용법을 기록한다.
3. Django와의 대응 및 차이를 명시해 “Django 호환”으로 오해하지 않게 한다.
4. 계획서의 예상 파일 목록과 실제 변경 목록을 대조한다.

권장 commit:

```text
docs(apps): document django-style automatic app wiring
```

## 9. 검증 계획

### 9.1 구현 중 빠른 검증

변경 직후에는 관련 테스트만 실행한다.

```text
tests/core/test_registry_*.py
tests/scripts/test_new_app*.py
tests/test_router_registration.py
tests/test_admin_wiring.py
tests/core/test_alembic_metadata.py
tests/core/test_migration_chain.py
tests/test_route_inventory.py
```

단순 폴더명 변경과 달리 이 작업은 부팅, 라우팅, metadata, Alembic 및 Admin 조립을 바꾸므로 관련 테스트가 필요하다. 다만 각 작은 편집마다 전체 `uv` 검사를 반복하지 않는다.

### 9.2 main 병합 전 전체 게이트

- ruff lint 및 format check
- mypy
- 전체 pytest, skip·xfail 0
- Alembic single head
- 빈 DB `upgrade head`
- OpenAPI route inventory 전후 비교
- ORM table inventory 전후 비교
- `ADMIN=true`의 view inventory 전후 비교
- `ADMIN=false`에서 sqladmin 미로드 확인
- 신규 임시 앱의 자동 발견·라우터 마운트·모델 metadata·Admin 등록 통합 검증

### 9.3 완료 기준

- 새 앱을 추가할 때 `main.py`, Alembic, 중앙 Admin 목록을 수정하지 않는다.
- 기존 여섯 기능의 API 경로와 HTTP 동작이 유지된다.
- 기존 ORM table과 Admin view가 누락되거나 중복되지 않는다.
- 모델·라우터·Admin이 없는 앱은 정상 동작한다.
- 구성요소 내부 import 오류는 기동 또는 테스트에서 즉시 드러난다.
- 앱 발견 순서는 운영체제와 파일시스템 순서에 관계없이 동일하다.
- 기존 기반 저장소의 인증, rate limit, 설정 및 의존성 동작에 비의도 변경이 없다.
- 변경 목록이 자동 앱 관리 범위를 벗어나지 않는다.

### 9.4 요구사항 추적표

| 요구사항 묶음 | 설계·구현 위치 | 개발 단계 | 주 검증 |
|---|---|---|---|
| `FR-01`, `FR-05`, `FR-07`, `CR-03`, `NFR-01`~`NFR-04` | `AppRegistry.discover()`, `AppModule` | 단계 C | registry discovery·optional import 테스트 |
| `FR-02`, `FR-08`, `CR-02`, `CR-05` | `AppRegistry.install_routers()`, `main.py` | 단계 D | route inventory, 임시 앱 OpenAPI 검사 |
| `FR-03`, `NFR-05`, `BC-02` | registry model import, `models_registry` facade, `session.py`, `migrations/env.py` | 단계 D | metadata, migration chain, 빈 DB upgrade |
| `FR-04`, `SEC-01`, `BC-03` | `app/features/admin.py`, `AppRegistry.install_admin()` | 단계 D | Admin inventory, disabled 미로드 검사 |
| `FR-06`, `SEC-02`~`SEC-04` | `scripts/new_app.py` | 단계 E | scaffold 단위·통합 테스트 |
| `CR-01`~`CR-06`, `AC-09` | README, 개념 문서, 이 계획서 | 단계 F | 문서 대조 검수 |
| `BC-01`, `BC-04`~`BC-06` | 기반 코드 보존 및 최소 결선 diff | 단계 A·B·D | before/after inventory와 기존 회귀 테스트 |
| `NFR-06`, `NFR-07`, `SEC-05` | 초기화 훅 계약, 검증 순서, tracked snapshot 이관 | 전 단계 | 멱등성, CI, manifest·secret scan |

PR 설명에는 각 행의 요구사항 ID와 실제 테스트 결과를 연결한다. 구현이 완료됐지만 해당 ID의 검증 증거가 없으면 요구사항은 완료로 판정하지 않는다.

## 10. 브랜치·commit·push 계획

### 10.1 브랜치 전략

```text
fastapi-project-structure-django-active-style/main
  `-- feature/default-base-django-app-automation
        1. default 기반 snapshot commit
        2. registry commit
        3. wiring commit
        4. scaffold commit
        5. tests/docs commit
        `-- 검증 후 main으로 --no-ff merge
```

기반 저장소의 main에는 변경하거나 push하지 않는다. 모든 구현과 이력은 대상 저장소의 기능 브랜치에서 관리한다.

### 10.2 작업 순서

1. 대상 저장소의 문서 변경을 별도 commit으로 보존한다.
2. target main을 최신 `origin/main`과 동기화한다.
3. 복구 tag를 생성한다.
4. `feature/default-base-django-app-automation`을 target main에서 생성한다.
5. 기반 snapshot과 자동화 기능을 단계별로 commit한다.
6. 기능 브랜치를 origin에 push하고 PR 또는 동등한 review 단계를 연다.
7. 전체 게이트가 통과한 뒤 최신 main 변경을 기능 브랜치에 반영해 재검증한다.
8. main에 `--no-ff` merge한다.
9. force push 없이 main을 origin에 push한다.
10. push 후 원격 CI와 main commit을 확인한다.

권장 merge commit:

```text
feat(apps): add django-style automatic app management to default structure
```

### 10.3 중단 조건

- target 또는 기반 저장소 작업 트리가 예상하지 못한 변경을 포함한다.
- 기준 commit이 원격에서 달라졌는데 차이 검토가 끝나지 않았다.
- 기존 route, table, Admin view inventory가 이유 없이 달라진다.
- 자동화 범위 밖의 설정·보안·API 변경이 함께 들어온다.
- 전체 게이트가 실패하거나 skip·xfail이 생긴다.
- main이 전진하여 병합 충돌의 의미 검토가 필요하다.

이 조건에서는 push나 main 병합을 진행하지 않고 원인을 기록한 뒤 기능 브랜치에서 수정한다.

## 11. 위험과 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 전체 대상 코드 cherry-pick | 기반 저장소 기능과 무관한 변경 유입 | 자동화 관련 파일·hunk만 수동 이식 |
| 앱 import 부수효과 | 부팅 지연, 순서 의존, 외부 I/O | 빠르고 멱등적인 등록만 허용, 정렬·재호출 테스트 |
| 관대한 optional import | 라우터·모델·Admin의 조용한 누락 | 내부 import 오류 재발생, 잘못된 export 계약 실패 |
| 모델 발견 경로 이중화 | 런타임과 Alembic metadata 불일치 | `AppRegistry`를 SSOT로 하고 기존 registry는 facade화 |
| Admin 조기 import | `ADMIN=false`에서도 sqladmin 로드 | Admin 분기 내부에서만 `admin.py` 탐색 |
| 기반 snapshot 대량 반영 | main 이력 검토 난이도 증가 | source commit 고정, snapshot commit과 기능 commit 분리 |
| 무심코 `.git`·`.env` 복사 | 저장소 손상 또는 비밀값 유출 | tracked archive만 사용하고 secret scan 수행 |
| main 직접 push | 복구와 review 곤란 | 기능 브랜치 push, CI/review, no-ff merge, 비강제 push |

## 12. 최종 산출물

- `fastapi-default-project-structure@a980b71` 기반 코드가 반영된 기능 브랜치
- Django 스타일 `AppRegistry`
- 라우터·모델·Admin 자동 결선
- 안전한 앱 scaffold
- 자동화 및 회귀 테스트
- 갱신된 README와 개념 문서
- source commit과 검증 결과가 포함된 PR 또는 merge 기록
- 검증 완료 후 대상 저장소 main commit 및 origin push 결과

이 계획의 핵심 원칙은 **기반 저장소의 동작을 유지하면서 중앙 등록 작업만 제거하는 것**이다. 구현 diff가 이 원칙을 벗어나면 기능을 더 가져오는 것이 아니라 범위를 다시 줄여야 한다.
