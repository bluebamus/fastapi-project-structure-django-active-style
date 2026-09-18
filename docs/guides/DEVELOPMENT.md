# 기능 개발 가이드 — ORM / Raw 워크플로

새 API·테이블을 이 구조로 만드는 개발자를 위한 문서입니다. 무엇을 먼저 정하고, 어떤 파일을 어떤
순서로 만들고, 세션·트랜잭션·테스트를 어떻게 다루는지 설명합니다. 이 저장소의 새 기능은
**ORM 과 Raw SQL 중 무엇으로 데이터에 접근할지**를 정하는 데서 출발하므로 그 선택이 이 문서의
중심입니다.

- 실행 중의 조립·설정·세션 구조는 [ARCHITECTURE](./ARCHITECTURE.md), 설치와 API 목록은
  [README](../../README.md)를 봅니다.
- 두 방식은 **각각 완결된 예제**로 들어 있습니다. 설명보다 코드를 함께 여는 편이 빠릅니다.

| | ORM 예제 | Raw 예제 |
|---|---|---|
| 기능 | `app/features/catalog/` (상품 CRUD) | `app/features/reports/` (일별 매출 집계) |
| 공개 API | `GET·POST /api/v1/catalog/products`, `GET·PATCH·DELETE /api/v1/catalog/products/{product_id}` | `GET /api/v1/reports/sales/daily?start_date=&end_date=` |
| 핵심 파일 | `app/features/catalog/repositories/product_repository.py` | `app/features/reports/repositories/sales_report_repository.py` |

---

## 1. 먼저 정할 것

1. **새 앱이 필요한가.** 기존 기능에 엔드포인트 하나를 더하면 되는 일이면 그 기능 안에서 합니다.
2. **HTTP 계약** — method·경로·입력·공개할 응답 필드·오류 응답.
3. **데이터 소유** — 새 테이블인가, 기존 테이블의 계산 결과인가(§4 의 선택 기준).
4. **읽기/쓰기 의도** — 조회만인가, 조회 후 쓰기인가, 잠금이 필요한가(§7).
5. **권한** — 현재 CRUD 예제에는 인가가 없습니다([ARCHITECTURE §10.3](./ARCHITECTURE.md)). 새
   엔드포인트는 인증·소유권 검사를 명시적으로 정합니다. 인증 성공과 수정 권한은 별개입니다.
6. **동시성·멱등성** — 재고 차감·상태 전환은 "조회 후 UPDATE" 만으로 안전하지 않습니다. 조건부
   UPDATE·잠금·DB 제약 중 무엇을 쓸지 정합니다.

---

## 2. 공통 계층 규칙 (ORM·Raw 둘 다)

두 방식은 **데이터 접근 방법만** 다르고 계층 규칙은 같습니다.

```text
View(Router)  →  Dependency  →  Service  →  Repository  →  AsyncSession → DB
  HTTP 만        조립만        업무 규칙     데이터 접근
```

| 계층 | 위치 | 한다 | 하지 않는다 |
|---|---|---|---|
| **View** (MVC 의 Controller) | `api/routers/v1/*.py` | 파라미터·본문 수신(Pydantic), Service 호출, 응답 DTO 변환, **쓰기면 commit 1회** | SQL, 업무 분기 |
| **Dependency** (조립 지점) | `dependencies/<name>_dependencies.py` | 세션 선택, `Service(session)` 를 **반환**(`yield` 아님) | commit, Service 메서드 실행 |
| **Service** | `services/` (`BaseService` 상속) | 업무 규칙, 같은 세션으로 Repository 조립, Raw 결과의 DTO 변환 | HTTP 객체 인지, commit 시점 결정 |
| **Repository** | `repositories/` (`BaseRepository` 또는 `RawRepositoryBase`) | 데이터 접근, SQL 소유 | commit, HTTP 응답 생성 |
| **Model** | `models/models.py` | 테이블·컬럼·PK·제약 | 응답 계약 대신하기 |
| **Schema** | `schemas/` | 입력 검증, 공개 응답 필드, OpenAPI 설명 | 테이블 생성 |

- **commit 은 쓰기 View 가 응답 직전에 한 번만** 합니다. 커밋 주체가 둘이면 실패했을 때 어디까지
  남았는지 알 수 없고, 중간 commit 뒤의 실패는 앞 변경을 되돌리지 못합니다.
- Service 는 FastAPI 를 모르므로 요청 밖(background·Celery·테스트)에서도 `Service(session)` 로
  그대로 씁니다. Service 를 전역 싱글턴으로 두지 않습니다(보관한 세션이 요청을 넘나듭니다).
- 기능끼리 import 하지 않습니다(예외: `auth → user`). 공통 기반은 `app/core`, 순수 도구는
  `app/utils` 에 있습니다.
- UnitOfWork·Factory 같은 추가 추상화는 요구가 생기기 전에는 만들지 않습니다. 트랜잭션 상태는
  `AsyncSession` 이 갖고, 경계는 쓰기 핸들러 본문입니다.
- SQLAdmin `ModelView`, SQL 의 VIEW, 이 문서의 "View(API 핸들러)" 는 서로 다른 것입니다.

---

## 3. 앱 만들기 — 생성기와 표준 레이아웃

```bash
uv run python -m scripts.new_app <name>                 # 뼈대
uv run python -m scripts.new_app <name> --with-admin    # admin.py(빈 admin_views) 포함
uv run python -m scripts.new_app <name> --force         # 이미 있는 앱을 의도적으로 다시 만들 때만
```

- 이름은 파이썬 식별자(snake_case)여야 하고 예약어·`app/features` 밖 경로는 거부됩니다. 대상 앱이
  이미 있으면 기본적으로 중단합니다. `--category` 는 동작에 영향 없는 호환용 옵션입니다.
- 생성물: `api/routers/v1/`·`models/`·`schemas/`·`services/`·`repositories/`·`dependencies/`·`tests/`
  패키지, 빈 `<name>_router` 가 있는 `api/routers/router.py`, 예시 주석만 있는
  `dependencies/<name>_dependencies.py`, (`--with-admin`) `admin_views: list[type] = []` 인 `admin.py`.
- **만들지 않는 것**: `models/models.py`, `apps.py`, v1 엔드포인트 파일, 스키마·Repository·Service
  본문, 테스트, migration. 아래를 직접 작성합니다.
- 손으로 만들어도 되지만 라우터 변수명은 반드시 `<name>_router` 입니다. 그 밖의 등록 규약은
  [ARCHITECTURE §2](./ARCHITECTURE.md)가 정합니다. `main.py`·`migrations/env.py`·
  `app/features/admin.py` 는 **열지 않습니다**.

```text
app/features/<name>/
├── __init__.py                 # 패키지 선언만 (부수효과·재노출 금지)
├── apps.py                     # ready() — 부팅 초기화 훅이 필요할 때만
├── api/routers/
│   ├── router.py               # <name>_router — v1 서브라우터를 include
│   └── v1/<name>.py            # 엔드포인트
├── models/
│   ├── __init__.py             # 모델 재노출
│   └── models.py               # ORM 모델
├── schemas/                    # 요청·응답 DTO
├── repositories/               # BaseRepository / RawRepositoryBase 상속
├── services/                   # BaseService 상속
├── dependencies/<name>_dependencies.py   # get_<name>_service / get_<name>_service_readonly
├── exceptions.py               # 기능 예외 (선택)
├── admin.py                    # ModelView + admin_views (모델이 있으면 사실상 필수)
└── tests/                      # 이 기능의 테스트
```

| 용도 | 쓰는 이름 | 쓰지 말 것 |
|---|---|---|
| 기능 예외 | `exceptions.py` | `<name>_exception.py` |
| 기능 의존성 | `dependencies/` 패키지 (단일 `dependencies.py` 도 허용) | `dependency.py` |
| SQLAdmin 뷰 | `admin.py` | `api/<name>_admin.py` |
| Celery 태스크 | 중앙 `app/celery/tasks.py` | 기능별 `worker/` |
| 초기화 | `apps.py` 의 `ready()` | `__init__.py` 의 import 부수효과 |

**최종 URL 은 prefix 의 합**입니다. 디렉터리 이름으로 계산되지 않습니다.

```text
registry 의 "/api"  +  router.py 의 include prefix "/v1/catalog"  +  v1 엔드포인트 "/products"
= /api/v1/catalog/products
```

```python
# app/features/catalog/api/routers/router.py
catalog_router = APIRouter()
catalog_router.include_router(products_v1.router, prefix="/v1/catalog", tags=["Catalog"])
```

`API_VERSION` 설정은 prefix 에 쓰이지 않습니다. `tests/test_openapi_contract.py` 가 모든 operation 의
summary·description·유일한 `operation_id`·tag, 파라미터·스키마 필드의 `description`, 그리고
`app/core/tags_metadata.py` 와 실제 tag 의 양방향 일치를 강제합니다. 새 경로를 추가하면
`tests/test_route_inventory.py` 의 목록과 README 의 API 표를 함께 갱신합니다.

---

## 4. ORM 이냐 Raw 냐

**기본값은 ORM 입니다.** Raw SQL 은 ORM 을 우회하는 일반 수단이 아니라, 아래 상황에서 **선택하는**
도구입니다. 일반 단일 테이블 CRUD 는 예외 없이 ORM 입니다.

| Raw 를 고르는 상황 | 이유 |
|---|---|
| 복잡한 집계·윈도 함수·CTE | ORM 표현이 SQL 보다 길어지고 의도가 흐려진다 |
| SQL 계약이 더 명확한 리포트 | 결과가 엔티티가 아니라 "행" 이다 |
| 실행 계획으로 관리해야 하는 성능 민감 조회 | 생성되는 SQL 을 통제해야 한다 |
| 저장 프로시저·DB 전용 기능 연계 | ORM 이 표현하지 못한다 |

판단이 애매하면 **돌려주는 것이 엔티티인가 계산 결과인가**를 봅니다. `Product` 한 건은 식별자와
수명주기가 있는 엔티티라 ORM, `GROUP BY` 로 나온 일자별 합계는 계산 결과라 Raw 입니다. reports 가
집계 전용 ORM 모델을 만들지 **않은** 이유입니다 — 원본 `SalesOrder` 모델은 테이블 소유권과 Admin
조회를 위해 있고, 집계는 Raw SQL 이 합니다. Raw 는 "항상 빠르다" 도 "Schema·Service 가 필요 없다"
도 아닙니다.

---

## 5. ORM 워크플로 — catalog 따라 읽기

| # | 파일 | catalog 에서 볼 것 |
|---|---|---|
| 1 | 생성기 실행 | `uv run python -m scripts.new_app <name> --with-admin` |
| 2 | `models/models.py` | `UUIDPrimaryKeyMixin`+`CreatedAtMixin`+`UpdatedAtMixin`+`Base` 조합, 금액은 `Numeric(12, 2)` |
| 3 | `models/__init__.py` | 모델 재노출 |
| 4 | `migrations/versions/*.py` | `alembic revision --autogenerate` 후 검토, **downgrade 도 구현** (§10) |
| 5 | `admin.py` | `admin_views` 목록 — 중앙 등록 불필요 |
| 6 | `schemas/*.py` | 입력/출력 모델 분리, 모든 필드에 `description`, `from_attributes=True` |
| 7 | `repositories/*.py` | `BaseRepository[Model, PK타입]` 상속, `model = Product` |
| 8 | `services/*.py` | 업무 규칙. 지금은 얇지만 규칙이 생기면 여기 쌓인다 |
| 9 | `dependencies/*.py` | 조회용·변경용 **둘 다** |
| 10 | `api/routers/v1/*.py` | `operation_id` 명시, 쓰기는 DTO 검증 → commit 1회 |
| 11 | `api/routers/router.py` | `<name>_router` — 이 이름이어야 자동 발견된다 |

### 5.1 모델과 스키마

- Mixin 의 UUID·시각 기본값은 **행 INSERT 시** 호출되는 Python 함수입니다. `UpdatedAtMixin` 의
  `onupdate` 는 ORM/Core UPDATE 에만 적용되고 Raw SQL 은 호출하지 않습니다.
- DB 제약(nullable·unique·index)과 Pydantic 검증(`min_length`, `gt=0` 등)은 목적이 다릅니다. 입력은
  스키마로 막고, 동시성 상황의 최종 무결성은 DB 제약으로 지킵니다.
- 응답 필드는 스키마로 정합니다. `Base.to_dict()` 를 그대로 공개하면 해시·내부 컬럼이 샙니다.
  catalog `ProductResponse` 는 `id/name/price/is_active` 만 공개합니다.
- PATCH 의 "보내지 않음" 과 "`null` 을 보냄" 은 다릅니다. `exclude_unset=True` 는 앞의 것만 뺍니다.
  non-nullable 컬럼에 `null` 을 허용할지 스키마에서 정하고 테스트합니다.
- 선언되지 않은 FK·relationship 을 추정해 만들지 않습니다. 기능 사이 참조는 값으로 둡니다.

### 5.2 생성 요청 한 건의 흐름

```text
POST /api/v1/catalog/products
 → get_catalog_service(session=Depends(get_writer_db_session)) → CatalogService(session)
 → service.create_product(payload) → ProductRepository.create(payload.model_dump())
 → CRUDBase._add: session.add → await flush → await refresh      (INSERT 전송, 아직 commit 아님)
 → View: ProductResponse.model_validate(product) → await service.commit() → 201
```

```python
@router.post("/products", response_model=ProductResponse, status_code=201,
             summary="상품 생성", operation_id="createCatalogProduct")
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.create_product(payload)
    response = ProductResponse.model_validate(product)   # 1. DTO 검증 먼저
    await service.commit()                               # 2. 그다음 commit
    return response
```

**응답 DTO 검증은 commit 앞에서** 합니다. 세션은 `expire_on_commit=False` 라 commit 자체로 속성이
만료되지는 않지만, DTO 검증이나 적재되지 않은 관계 접근이 commit 뒤에 실패하면 **이미 저장된
데이터에 대해 500** 이 나갑니다. catalog·blog·reply·sns·user 의 생성·수정 핸들러가 모두 이 순서이고,
`tests/test_dto_before_commit.py` 가 DTO 검증을 강제로 실패시켜 commit 0회·DB 불변을 확인합니다.

### 5.3 `BaseRepository` 공개 계약

| 메서드 | 동작 |
|---|---|
| `create(data)` | flush·refresh 까지, commit 없음. 제약 위반은 `DuplicateException`, 그 밖의 DB 오류는 `DatabaseException` |
| `get_by_id(pk)` | 없으면 `None` |
| `get_by_id_or_raise(pk)` | 없으면 `NotFoundException` |
| `get_all(skip=0, limit=100)` | 단순 페이지 조회 — **정렬 없음** |
| `count(**filters)` / `exists(pk)` | 총 개수(`filter_by`) / 존재 여부 |
| `update(pk, data)` | 없으면 `None`. **빈 dict 는 no-op** 으로 현재 객체 반환. 모델에 없는 필드·PK 변경은 `ValidationException`, 제약 위반은 `DuplicateException`. flush·refresh 까지 |
| `delete(pk)` | 삭제 여부(`bool`), commit 없음 |

- 목록에 순서가 필요하면 기능 Repository 에 `order_by`(동률은 PK)를 명시한 메서드를 추가하고,
  같은 필터로 `count` 를 계산합니다.
- 도메인 조회는 문자열 컬럼명을 받는 범용 필터 대신 모델 속성을 쓰는 명시적 메서드로 추가합니다
  (예: `ProductRepository.list_active()`).
- **공개 eager-loading 메서드는 없습니다.** 응답이 관계를 읽는다면 기능 Repository 쿼리에
  `selectinload`(1:N)·`joinedload`(N:1, 1:1)를 명시해 DTO 검증 중 암묵 I/O 가 나지 않게 합니다
  (`_apply_eager_loading()` 은 호출부가 없는 내부 헬퍼입니다).
- Service 가 `None` 을 돌려주면 View 가 404 로 바꿉니다(catalog 의 `_require()`).

---

## 6. Raw 워크플로 — reports 따라 읽기

계층은 같고 Repository 만 다릅니다.

```python
# app/features/reports/repositories/sales_report_repository.py
_DAILY_SALES = text("""
    SELECT DATE(o.created_at) AS sales_date, COUNT(*) AS order_count, ...
    WHERE o.created_at >= :start_date
      AND o.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)
""")

class SalesReportRawRepository(RawRepositoryBase):
    async def daily_sales(self, *, start_date, end_date):
        rows = await self.fetch_all(
            _DAILY_SALES,
            {"start_date": start_date, "end_date": end_date},
            query_name="sales_report.daily_sales",
        )
        return list(rows)
```

흐름: View(`get_daily_sales_report`, read-only 세션) → `ReportService.get_daily_sales()`(시작일이
종료일보다 뒤면 `InvalidDateRangeException`) → `SalesReportRawRepository.daily_sales()` →
`RawRepositoryBase.fetch_all()` → `RowMapping` → `DailySalesItem` DTO. 집계 기준은 `created_at` 이고
종료일 당일 전체를 포함합니다. 조회 기간의 상한은 없습니다.

### 6.1 지켜야 하는 5가지

**① SQL 은 모듈/클래스 상수입니다.** 요청 값으로 SQL 을 조립하지 않습니다.

```python
text(f"SELECT * FROM t WHERE id = {user_id}")   # 금지 — 정적 검사가 막는다
text("SELECT * FROM t WHERE id = :id")          # 허용
```

`tests/core/test_raw_sql_static_guard.py` 가 `app/`·`main.py`·`scripts/`·`migrations/` 를 AST 로 훑어
조립된 SQL 을 거부합니다. primitive 도 `text()` 로 감싼 `TextClause` 만 받고 multi-statement 를
거부합니다(`RawSQLContractError`).

**② 모든 외부 값은 named bind 입니다.** `IN` 목록은 `bindparam(name, expanding=True)` 를 씁니다.

**③ 식별자는 allowlist 로.** 정렬 컬럼처럼 bind 할 수 없는 값은 코드가 소유한 목록을
`ensure_identifier(value, allowed)` 로 통과한 것만 씁니다. 이스케이프로 막으려 하지 않습니다.

**④ 결과는 `RowMapping` 이고 DTO 변환은 Service 가 합니다.** View 가 `RowMapping` 을 그대로
돌려주면 SQL 컬럼 변경이 곧 공개 API 변경이 됩니다.

```python
return [DailySalesItem.model_validate(dict(row)) for row in rows]
```

DTO 필드와 SQL alias 가 어긋나면 **그 자리에서 실패**합니다. 의도된 안전망입니다. `Decimal`·날짜
타입도 DTO 에서 확인합니다.

**⑤ `query_name` 은 필수입니다.** Base 는 질의 이름·소요 시간·성공 여부(실패 시 예외 타입)만
기록하고 **SQL 본문과 파라미터는 남기지 않습니다** — 파라미터에는 사용자 식별자·검색어가 들어
있습니다. 이름은 `sales_report.daily_sales` 처럼 안정적인 코드 식별자로 짓습니다.

### 6.2 결과 API 의 의미 (임의로 바꾸지 마세요)

| 메서드 | 0행 | 1행 | 복수 행 |
|---|---|---|---|
| `fetch_one` | `None` | `RowMapping` | **오류** (`MultipleResultsFound`) |
| `fetch_all` | `[]` | 1개 목록 | 목록 |
| `fetch_scalar` | `None` | 값 (SQL `NULL` 도 `None`) | **오류** (`MultipleResultsFound`) |
| `execute` | DML 전용. 영향 행 수(`int`), 드라이버 미제공 시 `None`. commit 없음 | | |

`fetch_scalar` 는 "0행" 과 "값이 NULL" 을 구분하지 못합니다. 구분이 필요하면 `fetch_one` 을 씁니다.

### 6.3 DB 방언은 실제 DB 에서 검증합니다

reports 의 SQL 은 MySQL 문법(`DATE_ADD(..., INTERVAL 1 DAY)`)입니다. **SQLite 통과는 MySQL 승인
근거가 아닙니다.** 기능 테스트는 MySQL 에 의존하는 한 지점만 대체하고, 실제 SQL 은
`tests/integration/test_sales_report_mysql.py` 가 MySQL 8.4 에 대고 확인합니다. 운영 SQL 을 테스트
편의로 문자열 치환하지 않습니다.

```bash
docker compose -f compose.test.yaml up -d --wait
uv run python -m pytest -m mysql
docker compose -f compose.test.yaml down -v
```

### 6.4 Raw 로 쓰기(DML)를 해야 한다면

현재 reports 에는 Raw 쓰기 엔드포인트가 없습니다. 추가한다면 writer Dependency → Service → Raw
Repository(`execute()` 로 rowcount 반환) 순서를 지키고 **View 가 응답 전 commit 1회** 합니다.

- Raw INSERT/UPDATE 는 ORM Mixin 의 PK·시각 기본값과 `onupdate` 를 거치지 않습니다. 필요한 컬럼을
  bind 로 넣거나 DB `server_default` 를 씁니다.
- read-only 세션에서 Raw DML 을 시도하면 `DB_ROUTER_ENABLED` 와 **무관하게**
  `ReadOnlyRoutingError` 입니다. Raw 쓰기는 항상 writer 세션을 씁니다.
- `tests/integration/test_sales_report_mysql.py` 의 `_SalesOrderWriteService` 는 테스트용 helper 라
  endpoint 대신 commit/rollback 을 직접 부릅니다. 운영 Service 규약과 혼동하지 않습니다.

---

## 7. 세션 선택과 주입

```python
# app/features/catalog/dependencies/catalog_dependencies.py
async def get_catalog_service(
    session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(session)


async def get_catalog_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    return CatalogService(session)
```

| 유스케이스 | Dependency | 규칙 |
|---|---|---|
| 조회 (복제 지연 허용) | `get_read_only_db_session` | 쓰기를 시도하면 `ReadOnlyRoutingError`. commit 없음. 라우터가 켜져 있으면 replica |
| 쓰기, 조회 후 쓰기, 잠금 | `get_writer_db_session` | 첫 쿼리부터 writer. 응답 전 commit 1회 |
| 복제 지연을 허용할 수 없는 조회 | `get_writer_db_session` | writer 고정 조회, commit 없음 |

- GET/POST 라는 이름이 아니라 **유스케이스**로 고릅니다.
- 기능의 세션 Dependency 는 이 둘뿐입니다. 쓰기는 전부 `get_writer_db_session`, 조회는 전부
  `get_read_only_db_session` 입니다. 동적 라우팅은 기능 코드에서 쓰지 않습니다
  (`tests/core/test_session_dependency_names.py` 가 강제합니다).
- 조회에 쓰기 세션을 재사용하지 않습니다. writer 가 자동 commit 하지는 않지만 read-only 보호와
  replica 선택을 잃습니다. **Raw 라는 이유로 쓰기 세션을 쓰지 않습니다** — Raw 는 접근 방식이지
  권한이 아닙니다.
- 여러 Service 가 한 원자적 쓰기에 참여하면 같은 writer 세션을 주입하고 commit 주체는 하나로
  둡니다. 한 요청 안에서 같은 Dependency 는 재사용되지만 writer·read-only getter 는 서로 다른
  세션입니다.
- 인증 Dependency(`get_current_user`)가 read-only 세션으로 읽은 객체를 쓰기 세션에서 수정하지 말고,
  쓰기 세션으로 다시 조회합니다.

세션 종류·라우팅 규칙 전체는 [ARCHITECTURE §8](./ARCHITECTURE.md)에 있습니다.

---

## 8. 트랜잭션 경계와 오류

- `flush` 는 현재 트랜잭션 안에서 SQL 을 보내고, `refresh` 는 DB 값을 다시 읽고, `commit` 이 전체를
  확정합니다. Repository 는 flush 까지만 합니다.
- **왜 Dependency 가 아니라 핸들러가 commit 하는가.** 기본 request scope 의 yield Dependency 종료
  코드는 **응답을 보낸 뒤** 실행되므로, 거기서 commit 이 실패해도 클라이언트는 이미 `201` 을 받을
  수 있습니다([FastAPI 설명](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#early-exit-and-scope)).
  핸들러에서 commit 하면 실패가 응답 코드에 반영됩니다. 구조 증거: `tests/test_read_path_no_commit.py`,
  `app/features/blog/tests/test_transaction_boundary.py`.
- 예외로 빠져나가면 세션 Dependency 가 `rollback()` 후 재전파하고, 글로벌 핸들러가 `ErrorResponse` 를
  만듭니다. 이미 commit 한 뒤의 실패는 rollback 이 되돌리지 못합니다.
- `BaseService.commit()` 은 `session.commit()` 을 그대로 await 합니다. Repository 의 예외 변환은
  commit 단계 오류까지 포함하지 않으므로, 새 오류 계약은 commit 실패도 테스트합니다. 응답에는 SQL·
  bind 값·DSN·secret 을 넣지 않습니다.
- DB commit 과 HTTP 전송은 하나의 원자적 동작이 아닙니다. commit 성공 뒤 연결이 끊길 수 있으므로,
  중요한 생성 업무는 idempotency 키·중복 처리 정책을 요구사항으로 정합니다.
- 취소(`CancelledError`)는 `except Exception` 에 잡히지 않습니다. 취소·timeout 경로도 테스트합니다.

---

## 9. 요청 밖 작업 — background·Celery

```python
async with background_db_session() as session:     # 별도 풀, 예외 시 rollback, 끝나면 close
    service = SomeService(session)
    await service.do_write()
    await session.commit()                          # 요청 밖에서는 호출자가 commit
```

- `Depends` 는 요청 밖에서 자동 해석되지 않습니다. 위처럼 컨텍스트를 열고 Service 를 직접 조립합니다.
- 요청의 세션·Service·`Request` 를 background 나 Celery payload 로 넘기지 않습니다. JSON 직렬화
  가능한 id·값만 넘기고, 작업이 자기 세션을 엽니다.
- Celery 태스크는 `app/celery/tasks.py` 에 두고 코루틴은 `run_async()` 로 실행합니다
  ([ARCHITECTURE §11](./ARCHITECTURE.md)). 재시도·중복·"commit 과 enqueue 사이 실패" 를 테스트합니다.
- 접속 로그용 `access_log_tasks` 러너는 넘치면 버리는 비핵심 경로입니다. 결제·발송 같은 중요한
  작업을 넣지 않습니다.
- `async def` 안에서 `time.sleep`·동기 HTTP·큰 파일 처리·무거운 CPU 루프를 돌리면 이벤트 루프가
  멈춥니다. blocking I/O 는 `asyncio.to_thread`, 무겁거나 내구성이 필요한 작업은 Celery 로 보냅니다.
- 같은 `AsyncSession` 으로 `asyncio.gather` 를 돌리지 않습니다. 한 트랜잭션의 SQL 은 순차 await,
  독립 병렬 작업은 작업마다 세션을 엽니다.
- 공유 Redis 가 필요하면 `app.state.redis` 를 읽는 작은 Dependency 를 만들되, Redis 장애 시의 오류
  계약을 함께 정합니다(공통 Redis Dependency 는 아직 없습니다).

---

## 10. 스키마 변경 — migration 절차

```bash
uv run alembic revision --autogenerate -m "add <name> table"
# 생성된 파일의 upgrade/downgrade·drop·nullable·인덱스·FK·default·데이터 이동을 사람이 검토
uv run alembic upgrade head
uv run alembic current
uv run alembic heads          # head 는 하나여야 한다
```

1. 모델·제약·소유권을 정하고 `models/` 에 둡니다(등록은 registry 가 합니다).
2. autogenerate 결과는 후보일 뿐입니다. 이름 변경(rename)은 자동 감지되지 않고 drop+add 로 나올 수
   있습니다([Alembic 문서](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)).
3. 빈 DB·기존 DB·MySQL 방언에서 확인합니다. `tests/core/test_migration_chain.py` 가 빈 DB
   `upgrade head` 결과와 ORM metadata 를 대조합니다.
4. 운영은 앱 배포 전에 writer 에 `upgrade head` 를 적용합니다. 컬럼 제거처럼 호환이 깨지는 변경은
   "확장 → 코드 전환 → 구 컬럼 제거" 로 나눕니다.

- 실데이터가 있는 DB 에서 drop/recreate 나 검증 없는 `alembic stamp head` 를 하지 않습니다. stamp 는
  테이블을 만들지 않고 이력만 맞춰 스키마 차이를 숨깁니다.
- 개발 초기의 `DEBUG=true` 자동 생성과 Alembic 사이의 전환은 README 의 "스키마 관리" 절을 따릅니다.
- DB 의 SQL VIEW 가 실제로 필요하면 방언에 맞는 `CREATE VIEW`/`DROP VIEW` 를 migration 에 직접 쓰고,
  Repository 는 읽기 SQL 과 DTO 계약만 소유합니다. Alembic 은 VIEW 정의 변경을 자동 추적하지
  않습니다. (현재 reports 는 VIEW 를 만들지 않는 SELECT 집계입니다.)

---

## 11. 테스트

| 범위 | 확인할 시나리오 |
|---|---|
| Schema | 필수값·길이·금액·음수·`null` 과 미전달의 차이·공개 응답 필드 |
| Service | 업무 분기·부재·범위·상태 전환 |
| Repository | flush 까지·commit 없음, bind·필터·정렬·count·오류 변환 |
| Endpoint | 201/200/204, 404/409/422/500, `operation_id`, 권한, 응답 DTO |
| 트랜잭션 | commit 실패 시 2xx 없음, 중간 실패 rollback, DTO 검증 실패, 멱등성 |
| 등록 | 라우터·모델·Admin 결선, 잘못된 export, 경로 인벤토리 |
| 비동기·수명 | 요청 세션을 background 에 넘기지 않음, 취소·timeout |
| 실제 DB | MySQL 의 Decimal·날짜·제약·잠금·Raw 방언·migration (`mysql` 마커) |

- 기능 테스트는 `app/features/<name>/tests/`, 횡단 테스트는 `tests/` 에 `test_*.py` 로 둡니다.
- 엔드포인트 단위 테스트는 `app.dependency_overrides` 로 세션·Service 를 바꾸고, 테스트가 끝나면
  복원합니다. 기존 `conftest.py` 패턴(예: `app/features/blog/tests/conftest.py`)을 따릅니다.
- lifespan 을 검증할 때는 `TestClient` 컨텍스트나 `app.router.lifespan_context` 로 실제로 진입합니다.
  `ASGITransport` 요청만으로 startup 이 실행됐다고 보지 않습니다.
- 모델을 정의하는 테스트는 공유 `Base.metadata` 를 오염시키지 않도록 테스트 전용 `DeclarativeBase`
  를 씁니다(`tests/core/test_pk_generic.py`).
- skip 된 MySQL 테스트는 성공이 아닙니다. CI MySQL job 과 `tests` 게이트는 skip 0 을 요구합니다.

```bash
uv run python -m pytest app/features/<name>/tests
uv run python -m pytest -m "not mysql" -q
uv run python -m scripts.review_gate --group static structure docs
```

---

## 12. 완료 체크리스트

- [ ] `uv run python -m scripts.new_app <name>` (또는 규약대로 수동 생성)
- [ ] `models/models.py` + `models/__init__.py` 재노출, Alembic revision 생성·검토 (`env.py` 는 그대로)
- [ ] `schemas/` — 입력/출력 분리, `description`, 공개 필드 확정
- [ ] `repositories/` — ORM 이면 `BaseRepository`, Raw 면 `RawRepositoryBase` (+ `query_name`, named bind)
- [ ] `services/` — 업무 규칙, Raw 결과는 여기서 DTO 로
- [ ] `dependencies/` — 쓰기용·조회용 getter 둘 다
- [ ] `api/routers/v1/` — `operation_id`, DTO 검증 → commit 1회 / `router.py` 의 `<name>_router`
- [ ] 필요하면 `admin.py` 의 `admin_views` (민감 필드 제외 확인), `apps.py` 의 `ready()`
- [ ] 태그 설명(`app/core/tags_metadata.py`), `tests/test_route_inventory.py`, README API 표 갱신
- [ ] 테스트 작성, `mysql` 마커 대상 SQL 확인, 게이트 실행
- [ ] Celery 태스크가 필요하면 `app/celery/tasks.py` 에 추가

| 바꾼 것 | 함께 확인할 곳 |
|---|---|
| 공개 경로·메서드 | 라우터, `operation_id`, `tests/test_route_inventory.py`, README API 표 |
| 모델 필드 | 스키마 3종(create/update/response), Repository, `admin.py` 노출, Alembic revision |
| 트랜잭션 | 핸들러의 commit 위치, 기능별 트랜잭션 경계 테스트(예: `app/features/auth/tests/test_transaction_boundary.py`) |
| 인증 정책 | 보호할 라우터, 오류 응답, 보안 테스트 |
| 접속 로그 필드 | 미들웨어, sink, 모델·스키마, 개인정보 보존 정책 |
| 설정 추가 | `config.py`, `.env.example`(테스트가 양방향 일치 강제), 필요하면 배포 게이트 |
| 함수명·세션 이름·경로 | 이 문서, ARCHITECTURE, README (게이트 `docs` 그룹이 경로를 검사) |

---

## 13. 더 깊이

| 문서 | 내용 |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 조립·설정·세션·라우팅·보안 경계 |
| [`feature-development-guide.html`](./feature-development-guide.html) | 이 문서의 흐름을 catalog·reports 요청 도식으로 따라가는 안내서 |
| [`server-lifecycle-guide.html`](./server-lifecycle-guide.html) | 설정 → 기동 → 요청 → 종료 추적 안내서 |
| [`../specs/orm-raw-repository/`](../specs/orm-raw-repository/) | ORM/Raw 요구명세·개발계획·지침 원본 (착수 기준선, 코드 주석의 `workflow-guide §N` 출처) |
| [`../crp/groups/orm-raw-repository/design-baseline.md`](../crp/groups/orm-raw-repository/design-baseline.md) | 설계 결정과 선택 근거 |
| [`../specs/django-style-app-automation.md`](../specs/django-style-app-automation.md) | 앱 자동 등록 요구사항·설계 근거 |

규칙이 실제로 지켜지는지는 테스트와 게이트가 강제합니다. 문서를 읽지 않아도 틀린 코드는 통과하지
못하게 되어 있고, 이 문서는 "왜 그런 규칙인가" 를 설명합니다.
