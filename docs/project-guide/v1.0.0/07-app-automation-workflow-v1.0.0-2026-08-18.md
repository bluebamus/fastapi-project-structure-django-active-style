<!-- generated-by: gsd-doc-writer -->
# 앱 자동 발견·생성 워크플로우

| 항목 | 값 |
|---|---|
| 프로젝트 | `fastapi-project-structure-django-active-style` |
| 문서 버전 | `v1.0.0` |
| 작성일 | `2026-08-18` |
| 기준 커밋 | `76aed3c1aea2d3f1754f650ba631c8d853562cec` |
| 상태 | 현재 구현 기준 |

## 개요

기능 앱은 중앙 `INSTALLED_APPS` 목록 없이 디렉터리와 export 이름 규약으로 등록된다. 라우터, 모델과 Admin이 같은 발견 목록을 사용하므로 신규 기능을 추가할 때 `main.py`나 `migrations/env.py`를 수정하지 않는다.

## 발견 규칙

`AppRegistry.discover()`는 기본적으로 `app.features` 바로 아래에서 다음 조건을 만족하는 패키지를 찾는다.

- 디렉터리가 Python package다.
- 이름이 `_`로 시작하지 않는다.
- 직계 하위 패키지다. 중첩 카테고리를 재귀 탐색하지 않는다.
- 결과는 이름 오름차순으로 정렬된다.

각 패키지의 `__init__.py`는 발견 과정에서 import된다. 초기화 훅은 DB나 네트워크 I/O를 하지 않고 빠르고 멱등적이어야 한다.

## 선택 구성요소 계약

| 파일 | export 계약 | 없을 때 | 틀렸을 때 |
|---|---|---|---|
| `api/routers/router.py` | `<name>_router: APIRouter` | 라우터 없는 앱으로 생략 | 기동 실패 |
| `models/` | import 가능한 모델 패키지 | 모델 없는 앱으로 생략 | 내부 import 오류 전파 |
| `admin.py` | `admin_views: list[type[ModelView]]` | Admin 없는 앱으로 생략 | 기동 실패 |

다른 앱과 같은 APIRouter 객체나 ModelView 클래스를 중복 등록해도 `AppContractError`가 발생한다.

## 자동 결선

```mermaid
flowchart TD
    A[app/features 직접 하위 스캔] --> B[이름순 AppModule 목록]
    B --> C[앱 패키지 import / init hook]
    B --> D[models import]
    B --> E[router load]
    E --> F[/api prefix mount]
    B --> G{ADMIN=true?}
    G -->|yes| H[admin_views 검증·등록]
    G -->|no| I[sqladmin app modules 미로드]
    B --> J[Alembic target_metadata]
```

런타임 `main.py`와 Alembic은 각각 `AppRegistry`의 같은 발견 알고리즘을 사용한다. 모델 import 목록을 별도로 유지하지 않는다.

## 신규 앱 생성

프로젝트 루트에서 다음 명령을 사용한다.

```powershell
python -m scripts.new_app orders
python -m scripts.new_app orders --with-admin
```

생성기는 다음 구조를 만든다.

```text
app/features/orders/
├─ __init__.py
├─ api/routers/router.py
├─ api/routers/v1/
├─ models/
├─ schemas/
├─ services/
├─ repositories/
├─ dependencies/
├─ tests/
└─ admin.py                 # --with-admin일 때
```

앱 이름은 Python 식별자여야 하고 예약어일 수 없다. 경로가 `app/features` 밖으로 나가지 않는지 재검사한다. 기존 앱이 있으면 기본적으로 중단하며, `--force`는 기존 파일을 덮어쓸 수 있으므로 명시적 재생성에만 사용한다.

## 기능 완성 순서

1. `api/routers/router.py`의 `<name>_router`에 v1 라우터를 include한다.
2. 모델을 `models/`에 두고 공통 `Base`를 상속한다.
3. 입력·출력 스키마를 분리한다.
4. 저장소와 서비스를 작성하고 세션 기반 의존성을 연결한다.
5. 쓰기 핸들러는 성공 응답 전 명시적으로 커밋한다.
6. Admin이 필요하면 실제 `ModelView`와 `admin_views`를 작성한다.
7. Alembic revision을 생성·검토한다.
8. API, 서비스, 저장소, 앱 계약과 route inventory 테스트를 추가한다.

## Admin 자동 등록

`ADMIN=true`일 때만 `app.features.admin`과 앱별 `admin.py`를 읽는다. `Admin(app, engine)` 생성이 `/admin`을 직접 마운트하며 registry는 view만 추가한다. `ADMIN=false`에서는 sqladmin 관련 앱 모듈을 불필요하게 로드하지 않는다.

Admin에는 인증이 없으므로 신규 view가 민감 필드를 상세·폼·내보내기에 노출하지 않는지 확인해야 한다. 특히 `User.hashed_password` 제외 설정은 제거하지 않는다.

## 앱 제거 또는 이름 변경

- 디렉터리를 제거하면 다음 기동에서 자동 발견 목록, 라우터, 모델, Admin에서 빠진다.
- DB 테이블은 자동 삭제되지 않는다. 데이터 보존·이관과 Alembic downgrade/삭제 revision을 별도로 설계한다.
- 이름 변경은 공개 URL prefix, router export 이름, import 경로, Celery task 이름과 마이그레이션 참조에 영향을 줄 수 있다.
- route inventory 변경은 의도된 API 호환성 변경인지 검토해야 한다.

## 실패 진단

| 증상 | 우선 확인 |
|---|---|
| 앱 전체가 발견되지 않음 | package 여부, 이름, 직계 하위 위치 |
| 라우터만 없음 | `router.py`, `<name>_router` 이름과 타입 |
| migration이 비어 있음 | 모델이 공통 Base 상속·import되는지 |
| Admin view 누락 | `ADMIN`, `admin_views` 리스트와 ModelView 타입 |
| 경로 중복 | 라우터 객체 공유 또는 동일 prefix/path |
| import 중 기동 실패 | 선택 모듈 내부의 잘못된 import |

## 주요 검증 파일

- `tests/test_app_registry.py`
- `tests/test_route_inventory.py`
- `tests/test_admin_wiring.py`
- `tests/scripts/test_new_app.py`
- `tests/core/test_models_registry.py`
