<!-- generated-by: gsd-doc-writer -->
# ORM/Raw 공통 워크플로우 개발 지침서

## 1. 적용 원칙

ORM과 Raw SQL은 Repository 구현에서만 갈라진다.

```text
View -> Dependency -> Service -> Repository -> AsyncSession
```

| 계층 | 해야 하는 일 | 하지 않는 일 |
|---|---|---|
| View | HTTP 계약, Service 호출, 응답 변환, 쓰기 commit | SQL, 도메인 규칙 |
| Dependency | session 선택, 객체 조립 | 비즈니스 실행, commit |
| Service | 유스케이스와 비즈니스 규칙 | HTTP 객체, SQL 문자열 |
| Repository | ORM/Raw 데이터 접근 | commit, HTTP 응답 생성 |
| Schema | 입력 검증과 출력 계약 | DB 세션 접근 |

## 2. 공통 디렉터리 구조

```text
app/
├── core/
│   ├── db/
│   ├── middlewares/
│   ├── models/models_base.py
│   ├── repositories/
│   │   ├── crud_base.py
│   │   ├── repository_base.py
│   │   ├── raw_crud_base.py
│   │   └── raw_repository_base.py
│   ├── services/services_base.py
│   └── tags_metadata.py
└── features/<feature>/
    ├── api/routers/
    │   ├── router.py
    │   └── v1/<view>.py
    ├── dependencies/<feature>_dependencies.py
    ├── models/models.py                  # ORM 조회 또는 스키마 소유권이 있는 기능
    ├── admin.py                          # 모델이 있는 기능은 필수
    ├── repositories/<name>_repository.py
    ├── schemas/<feature>_schema.py
    ├── services/<feature>_service.py
    └── tests/
```

Raw 조회 전용 기능은 결과용 ORM 모델을 만들지 않는다. DB 테이블의 생명주기를 이
프로젝트가 관리한다면 테이블 ORM 모델과 Alembic migration은 별개로 필요할 수 있다.
모델을 추가한 기능은 프로젝트 정책상 `admin.py`와 `admin_views: list[type]`도 함께
제공한다. `AppRegistry`는 `admin.py` 자체가 없는 기능을 기술적으로는 선택 구성으로
처리하지만, 이 지침에서 신규 영속 모델의 Admin 누락은 허용하지 않는다.

### 2.1 DB Session 명명 규칙

애플리케이션 계층에서는 SQLAlchemy 세션임을 이름으로 명확히 표현한다.

| 용도 | 정식 Dependency | 사용 기준 |
|---|---|---|
| 순수 조회 | `get_read_only_db_session` | GET/HEAD 및 변경 없는 조회 |
| 쓰기·조회 후 쓰기 | `get_writer_db_session` | 첫 쿼리부터 primary writer 고정 |
| 동적 라우팅 | `get_routed_db_session` | 명시적으로 승인된 특수 경로만 사용 |
| Background DI | `get_background_db_session` | background 전용 pool 사용 |
| 요청 밖 context | `background_db_session` | Celery 및 fire-and-forget 작업 |

Dependency 인자와 Service/Repository 생성자 및 속성은 `db_session`과
`self.db_session`을 사용한다. 정식 이름과 호환 별칭은 다음처럼 1:1로 유지한다.

| 정식 API | deprecated alias |
|---|---|
| `get_read_only_db_session` | `get_read_session` |
| `get_writer_db_session` | `get_write_session` |
| `get_routed_db_session` | `get_session` |
| `get_background_db_session` | `get_background_session` |
| `background_db_session` | `background_session` |

현재 active-style 소스의 `app/core/db/session.py`는 아직 오른쪽 이름을 정의한다. 구현 시
왼쪽 이름을 실제 함수로 두고 오른쪽은 단순 별칭으로 제공한 뒤, 모든 기능 Dependency,
Dependency override 테스트와 문서를 정식 이름으로 전환한다. 신규 코드는 deprecated alias를
사용하지 않는다.

JWT access/refresh 발급·검증·refresh 재발급은 이미 구현된 기준선이며 이 작업에서는 변경하지
않는다. 영속적 rotation/reuse detection, revoke/logout, 권한·보안 저장 정책은 별도 후속
명세로 관리한다.

## 3. ORM 시나리오: 상품 CRUD

아래 코드는 확정된 목표 Base 시그니처를 기준으로 한 예시다.

### 3.1 ORM 모델

```python
# app/features/catalog/models/models.py
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.models_base import UUIDTimestampModel


class Product(UUIDTimestampModel):
    __tablename__ = "catalog_products"

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="상품명")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, comment="판매가")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

모델 원칙:

- 공통 PK와 시간 필드는 프로젝트 믹스인을 사용한다.
- 변경 가능한 모델은 UUID/created/updated 조합 Base를 사용하고 불변 로그는 updated를 제외한다.
- DB 제약은 ORM 컬럼에 선언한다.
- API 설명은 Pydantic Schema에도 별도로 선언한다.
- `__tablename__`, nullability, index, unique, FK를 명시한다.

Alembic migration은 예제 구현과 함께 실제 revision으로 추가한다.

```text
migrations/versions/<revision>_add_catalog_products.py
migrations/versions/<revision>_add_sales_orders.py
```

`catalog_products`는 `Product` ORM 모델과 metadata가 일치해야 한다. `sales_orders`도
migration/metadata 드리프트 검사와 Admin 스키마 소유권을 위한 `SalesOrder` 모델을 둔다.
단, 리포트 결과 전용 ORM 모델은 만들지 않고 집계 조회는 Raw SQL을 사용한다. 두 revision은
upgrade와 downgrade를 모두 구현한다. 기존 revision은 재작성하지 않으며 각 신규 revision을
즉시 `down_revision`까지 downgrade한 뒤 head로 재-upgrade하는 절차를 ephemeral MySQL에서
검증한다. 운영 장애 복구는 데이터 보존을 우선해 기본적으로 forward-fix한다.

### 3.2 SQLAdmin 자동 결선

```python
# app/features/catalog/admin.py
from sqladmin import ModelView

from app.features.catalog.models.models import Product


class ProductAdmin(ModelView, model=Product):
    name = "Product"
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True


admin_views: list[type] = [ProductAdmin]
```

`reports/admin.py`도 같은 방식으로 `SalesOrderAdmin`을 정확히 한 번 공개한다. Registry는
`admin.py` 부재를 선택 기능으로 취급하므로, 신규 모델의 Admin 누락은
`tests/test_admin_wiring.py`와 `tests/core/test_admin_views.py`에서 명시적으로 실패시킨다.
`SalesOrderAdmin`은 create/edit/delete를 `False`, details/export를 `True`로 설정한다.
Product에는 현재 비밀 필드가 없지만 향후 secret은 모든 표면에서 제외하고, SalesOrder의 향후
payment/customer 식별자는 list/export에서 제외한다.

### 3.3 Pydantic Schema

```python
# app/features/catalog/schemas/catalog_schema.py
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Mechanical Keyboard", "price": "129.00"}]
        }
    )

    name: str = Field(min_length=1, max_length=200, description="상품명")
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="판매가")


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200, description="상품명")
    price: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2, description="판매가")
    is_active: bool | None = Field(None, description="판매 활성 여부")


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="상품 UUID")
    name: str = Field(description="상품명")
    price: Decimal = Field(description="판매가")
    is_active: bool = Field(description="판매 활성 여부")


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int = Field(ge=0, description="전체 상품 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
```

### 3.4 ORM Repository

```python
# app/features/catalog/repositories/product_repository.py
from app.core.repositories.repository_base import BaseRepository
from app.features.catalog.models.models import Product


class ProductRepository(BaseRepository[Product, str]):
    model = Product
```

공통 CRUD로 표현할 수 없는 조회만 명시적인 도메인 메서드로 추가한다.

```python
async def list_active(self, *, skip: int, limit: int):
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return (await self.db_session.execute(stmt)).scalars().all()
```

### 3.5 Service

```python
# app/features/catalog/services/catalog_service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate


class CatalogService(BaseService):
    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = ProductRepository(db_session)

    async def create_product(self, payload: ProductCreate):
        return await self.repository.create(payload.model_dump())

    async def list_products(self, *, skip: int, limit: int):
        items = await self.repository.list(skip=skip, limit=limit)
        total = await self.repository.count()
        return items, total
```

가격 정책, 상태 전환, 중복 판정 등은 이 계층에 둔다.
Service는 `get_product`, `update_product`, `delete_product`도 Repository 최소 CRUD에 위임한다.
update는 PK/unknown field 변경을 거부하고 제공된 필드만 반영하며, 빈 PATCH는 존재 확인 후
no-op이다. delete는 조회한 entity를 삭제한다. commit/rollback은 Repository가 수행하지 않는다.

### 3.6 Dependency

```python
# app/features/catalog/dependencies/catalog_dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.catalog.services.catalog_service import CatalogService


async def get_catalog_service(
    db_session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    return CatalogService(db_session)


async def get_catalog_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    return CatalogService(db_session)
```

Dependency는 조립만 한다. `yield` 이후 commit하거나 Service 메서드를 미리 실행하지 않는다.

### 3.7 Versioned View

```python
# app/features/catalog/api/routers/v1/products.py
from fastapi import APIRouter, Depends, Query, status

from app.features.catalog.dependencies.catalog_dependencies import (
    get_catalog_service,
    get_catalog_service_readonly,
)
from app.features.catalog.schemas.catalog_schema import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
)
from app.features.catalog.services.catalog_service import CatalogService

router = APIRouter()


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="상품 생성",
    description="판매할 상품을 생성합니다.",
    operation_id="createCatalogProduct",
)
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.create_product(payload)
    response = ProductResponse.model_validate(product)
    await service.commit()
    return response


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="상품 목록 조회",
    description="상품을 페이지 단위로 조회합니다.",
    operation_id="listCatalogProducts",
)
async def list_products(
    skip: int = Query(0, ge=0, description="건너뛸 상품 수"),
    limit: int = Query(50, ge=1, le=100, description="조회할 상품 수"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductListResponse:
    items, total = await service.list_products(skip=skip, limit=limit)
    return ProductListResponse(
        items=[ProductResponse.model_validate(item) for item in items],
        total=total,
        skip=skip,
        limit=limit,
    )
```

예시는 축약했지만 공개 CRUD 계약은 아래 다섯 operation 전부다. 구현·route inventory·OpenAPI
테스트가 모두 같은 path/method/operation ID/status를 고정해야 한다.

| method/path | operation ID | 성공 | 주요 오류 |
|---|---|---:|---|
| `GET /api/v1/catalog/products` | `listCatalogProducts` | 200 | 422 |
| `POST /api/v1/catalog/products` | `createCatalogProduct` | 201 | 409, 422, 500 |
| `GET /api/v1/catalog/products/{product_id}` | `getCatalogProduct` | 200 | 404, 422 |
| `PATCH /api/v1/catalog/products/{product_id}` | `updateCatalogProduct` | 200 | 404, 409, 422, 500 |
| `DELETE /api/v1/catalog/products/{product_id}` | `deleteCatalogProduct` | 204, body 없음 | 404, 422, 500 |

get은 read-only Dependency, update/delete는 writer Dependency를 쓴다. 쓰기 operation은 응답
DTO 검증과 관계 preload를 commit 전에 끝내며 commit/rollback 실패의 SQL·DSN·driver 원문을
응답에 노출하지 않는다.
catalog 그룹 router는 prefix `/v1/catalog`, tag `Catalog`를 사용한다. reports는 기존 예시대로
prefix `/v1/reports`, tag `Reports`를 사용한다.

## 4. Raw 시나리오: 일별 매출 리포트

### 4.1 Raw Base 사용 계약

```python
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause


# app/core/repositories/raw_crud_base.py의 목표 인터페이스
class RawCRUDBase:
    def __init__(self, db_session: AsyncSession) -> None: ...

    async def _fetch_all(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Sequence[RowMapping]: ...

    async def _fetch_one(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> RowMapping | None: ...

    async def _fetch_scalar(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> Any | None: ...

    async def _execute(
        self, statement: TextClause, params: Mapping[str, Any] | None = None
    ) -> int | None: ...


class RawRepositoryBase(RawCRUDBase):
    async def fetch_all(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> Sequence[RowMapping]: ...
```

결과 계약을 임의로 바꾸지 않는다.

- `fetch_one`은 `mappings().one_or_none()`으로 0행 `None`, 1행 `RowMapping`을 반환하며 복수
  행은 cardinality 오류다.
- `fetch_all`은 `mappings().all()`이고 빈 결과는 빈 sequence다.
- `fetch_scalar`는 `scalar_one_or_none()`이다. 0행과 SQL NULL은 모두 `None`이며 복수 행은
  오류다. 0행/NULL 구분이 필요하면 `fetch_one`을 사용한다.
- `execute`는 INSERT/UPDATE/DELETE에만 사용하고 유효한 rowcount는 `int`, driver가 제공하지
  않으면 `None`을 반환한다. 음수 값을 성공 건수로 공개하지 않는다.
- 모든 외부 값은 `:start_date`처럼 named placeholder로 SQL에 선언하고
  `Mapping[str, Any]`로 바인딩한다. SQL 문자열 보간, positional parameter와 f-string 값
  삽입은 금지한다.
- Base는 commit/rollback을 수행하지 않으며 public 메서드는 keyword-only `query_name`을 받아
  이름과 소요 시간만 로그로 남긴다. SQL 본문과 `params`는 로그에 남기지 않는다.

### 4.2 Raw 결과 Schema

```python
# app/features/reports/schemas/report_schema.py
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date
    end_date: date
    items: list[DailySalesItem]
```

Raw 결과는 ORM 객체가 아니므로 `from_attributes=True`에 의존하지 않는다. `dict(row)`를
Pydantic으로 검증한다.

### 4.3 Raw Repository

```python
# app/features/reports/repositories/sales_report_repository.py
from datetime import date

from sqlalchemy import text

from app.core.repositories.raw_repository_base import RawRepositoryBase


class SalesReportRawRepository(RawRepositoryBase):
    async def daily_sales(self, *, start_date: date, end_date: date):
        statement = text(
            """
            SELECT
                DATE(o.created_at) AS sales_date,
                COUNT(*) AS order_count,
                COALESCE(SUM(o.total_amount), 0) AS gross_amount
            FROM sales_orders AS o
            WHERE o.created_at >= :start_date
              AND o.created_at < DATE_ADD(:end_date, INTERVAL 1 DAY)
            GROUP BY DATE(o.created_at)
            ORDER BY sales_date ASC
            """
        )
        return await self.fetch_all(
            statement,
            {"start_date": start_date, "end_date": end_date},
            query_name="sales_report.daily_sales",
        )
```

주의: 위 SQL은 MySQL 방언 예시다. SQLite에서는 Base 계약만 빠르게 검증하고 실제 SQL과
Alembic migration은 로컬 및 CI가 공유하는 `compose.test.yaml` MySQL service에서 검증한다.
운영 SQL을 테스트 편의 때문에 문자열 치환하지 않는다.

### 4.4 Raw Service

```python
# app/features/reports/services/report_service.py
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import DailySalesItem


class ReportService(BaseService):
    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = SalesReportRawRepository(db_session)

    async def get_daily_sales(self, *, start_date: date, end_date: date):
        if end_date < start_date:
            raise ValueError("end_date must not precede start_date")

        rows = await self.repository.daily_sales(
            start_date=start_date,
            end_date=end_date,
        )
        return [DailySalesItem.model_validate(dict(row)) for row in rows]
```

날짜 범위 규칙은 비즈니스 규칙이므로 Service에 둔다. SQL과 컬럼 alias는 Repository가
소유한다.

### 4.5 Raw Dependency

```python
# app/features/reports/dependencies/report_dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    db_session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    return ReportService(db_session)
```

### 4.6 Raw View

```python
# app/features/reports/api/routers/v1/sales_reports.py
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.features.reports.dependencies.report_dependencies import (
    get_report_service_readonly,
)
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/sales/daily",
    response_model=DailySalesReportResponse,
    summary="일별 매출 리포트",
    description="지정한 기간의 주문 수와 총 매출을 일별로 집계합니다.",
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(description="조회 시작일", examples=["2026-08-01"]),
    end_date: date = Query(description="조회 종료일", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(
        start_date=start_date,
        end_date=end_date,
    )
    return DailySalesReportResponse(
        start_date=start_date,
        end_date=end_date,
        items=items,
    )
```

조회이므로 commit하지 않는다. Raw SQL이라는 이유로 쓰기 세션을 사용하지 않는다.

## 5. 라우터 취합

버전 View를 기능 그룹 라우터에 등록한다.

```python
# app/features/reports/api/routers/router.py
from fastapi import APIRouter

from app.features.reports.api.routers.v1 import sales_reports

reports_router = APIRouter()
reports_router.include_router(
    sales_reports.router,
    prefix="/v1/reports",
    tags=["Reports"],
)
```

정식 자동 배선 계약은 `router.py`의 `<feature>_router`다. 기능 패키지
`__init__.py`는 경량 상태로 유지하고 모델·라우터·sink/engine을 import하거나 재노출하지 않는다.
현재 일부 기능 패키지의 재노출/import-time 초기화는 Runtime gate에서 먼저 제거하고, 필요한
초기화는 명시적 멱등 hook으로 옮긴다. `discover()`만 실행했을 때 metadata와 장기 자원 수가
변하지 않는 테스트를 둔다.

`main.py`는 이미 `discover()`한 registry에 최종 취합을 위임한다.

```python
registry = AppRegistry()
registry.discover()
registry.import_models()

app = FastAPI(...)
registry.install_routers(app)  # reports_router를 /api에 마운트
```

즉 실제 흐름은 `reports_router` → `AppRegistry.install_routers()` → `main.py`다.
`AppRegistry.load_router()`는 `app.features.reports.api.routers.router` 모듈을 열어
`reports_router: APIRouter`를 검증한다. 모듈이 있는데 이름이 틀리거나 타입이
아니면 기동을 실패시킨다. `tests/test_app_autowiring.py`,
`tests/test_router_registration.py`, `tests/test_route_inventory.py`로 누락과 공개 API 변경을 검출한다.

## 6. Raw SQL 보안 규칙

### 허용

```python
statement = text("SELECT * FROM sales_orders WHERE user_id = :user_id")
await self.fetch_all(statement, {"user_id": user_id})
```

### 금지

```python
text(f"SELECT * FROM sales_orders WHERE user_id = '{user_id}'")
text("SELECT * FROM " + table_name)
```

정렬 컬럼처럼 식별자 선택이 필요하면 allowlist를 사용한다.

```python
SORT_COLUMNS = {
    "date": "o.created_at",
    "amount": "o.total_amount",
}
column = SORT_COLUMNS[requested_sort]
statement = text(f"SELECT ... ORDER BY {column} DESC")
```

이 경우 f-string 값은 외부 입력이 아니라 코드가 소유한 상수에서만 나온다.
SQL 본문도 Repository 소유 상수로 고정하며 multi-statement와 요청 기반 동적 SQL은 금지한다.
`IN` 목록은 `bindparam(expanding=True)`를 사용한다. AST/정적 테스트로 f-string/문자열 연결과
비허용 `text()` 생성을 검출한다.

### `TextClause` 문장 분류

첫 토큰만 보고 읽기/쓰기를 나누는 정규식은 완전한 SQL parser가 아니다. 특히
`WITH ... DELETE/UPDATE/INSERT`는 선두 키워드가 `WITH`라서 단순 분류기를 우회할 수 있다.
Repository가 소유한 SQL 상수만 허용하더라도 read-only 경계는 다음처럼 fail-closed로 동작한다.

| 문장 | 분류/처리 |
|---|---|
| 일반 `SELECT` | read |
| `SELECT ... FOR UPDATE` | writer; read-only에서 거부 |
| `INSERT`/`UPDATE`/`DELETE` 및 DDL | writer; read-only에서 거부 |
| `CALL`/저장 프로시저 | writer; read-only에서 거부 |
| `WITH`로 시작하거나 판별 불가 | writer 또는 unknown; read-only에서 기본 거부 |
| 빈 문장/multi-statement | 거부 |

CTE를 지원 범위에 넣으려면 문자열 확장이 아니라 dialect-aware parser 또는 SQLAlchemy expression
구조로 분류기를 교체하고, 그 전까지 CTE 기반 DML은 명시적인 잔여 위험으로 관리한다.

## 7. 트랜잭션 지침

### 조회

```text
GET View
  -> get_<feature>_service_readonly
  -> get_read_only_db_session
  -> Repository 조회
  -> commit 없음
```

### 쓰기

```text
POST/PATCH/DELETE View
  -> get_<feature>_service
  -> get_writer_db_session
  -> Repository flush/execute
  -> View에서 await service.commit()
  -> 응답 반환
```

금지 항목:

- Dependency teardown에서 commit
- Repository에서 commit
- 응답 반환 후 background task로 핵심 DB commit
- 조회 View에서 쓰기 Dependency 재사용
- Raw DML을 `get_read_only_db_session`으로 실행

### `DB_ROUTER_ENABLED=false`에서도 read-only DML 차단

read-only는 replica 라우팅 옵션이 아니라 Dependency 계약이다. 현재 active-style의
`get_read_session()`은 `DB_ROUTER_ENABLED=false`일 때 일반 `AsyncSessionLocal`을 사용하므로
`mark_read_only()`만으로는 쓰기를 차단하지 못한다. 정식
`get_read_only_db_session`은 설정값과 무관하게 다음 두 경계를 모두 적용해야 한다.

1. read-only 전용 Session 클래스와 중앙 `is_read_only()`/`assert_writable()`가 ORM flush와 SQLAlchemy Core DML
   (`Insert`/`Update`/`Delete`)을 `ReadOnlyRoutingError`로 차단한다. 라우터가 꺼져 있으면
   이 Session은 reader 선택 없이 writer engine에 바인딩하되 쓰기 검증은 유지한다.
2. 모든 session 실행 경계가 TextClause를 검사한다. `_execute()`뿐 아니라 fetch API로 전달한
   DML, 직접 `session.execute()`, `SELECT ... FOR UPDATE`, 저장 프로시저와 multi-statement를
   거부한다. `WITH`와 판별 불가 문장은 writer/unknown으로 취급해 read-only에서 기본 거부한다.
   Raw Repository 쓰기는 전용 primitive를 통과한다.
3. `session.info`는 보안 경계가 아니므로 운영 배포는 read-only DB credential 또는 transaction
   read-only 설정을 최종 방어선으로 사용한다.

검증은 `DB_ROUTER_ENABLED` true/false를 parameterize하여 각각 ORM `add()` + `flush()`,
Core `insert/update/delete`, Raw `execute(text(...))`가 예외를 내고 DB row count가 변하지
않음을 MySQL 통합 테스트로 확인한다. 같은 Session의 SELECT와 writer Dependency의
DML 성공 테스트를 대조군으로 둔다.

## 8. Scalar 문서 체크리스트

### View

- [ ] `summary`, `description`, 고유 `operation_id`
- [ ] 성공 `response_model`과 상태 코드
- [ ] 알려진 오류를 `responses`로 문서화
- [ ] Path/Query 제약과 설명 및 대표 예시
- [ ] 적절한 그룹 tag

### Pydantic

- [ ] 입력과 출력을 별도 모델로 구분
- [ ] 모든 외부 노출 필드에 의미 있는 `description`
- [ ] 길이, 범위, pattern 등 실제 검증 제약
- [ ] 민감 필드는 응답 모델에서 제외
- [ ] 대표 요청/응답은 `json_schema_extra.examples`로 제공
- [ ] ORM 응답만 `from_attributes=True`; Raw mapping은 명시적으로 검증

### ORM 모델

- [ ] DB nullability, unique, index, FK와 Python 타입 일치
- [ ] 공통 믹스인 정책 준수
- [ ] DB `comment`는 필요 시 제공하되 API 문서의 유일한 출처로 사용하지 않음

### 태그

- [ ] `tags_metadata.py`의 이름과 Router tag 일치
- [ ] 구현 완료 기능을 “예정”으로 설명하지 않음
- [ ] 태그 표시 순서가 의도와 일치
- [ ] `Health`를 유지하고 `Auth`/`Catalog`/`Reports`를 metadata에 추가했는가
- [ ] 미사용 `Analytics`를 제거하고 User/Blog/Reply/SNS의 “미구현/예정” 설명을 현재화했는가

## 9. 테스트 지침

### ORM Repository

- create/get/list/count/exists/update/delete
- 입력 dict가 변경되지 않는지 검증
- duplicate/FK/DB 오류 변환
- eager loading이 필요한 기능 쿼리의 N+1 검증
- PK 타입이 `BaseRepository[ModelT, PrimaryKeyT]` 계약으로 검사되는지 검증

### Raw Repository

- named parameter가 실제로 바인딩되는지 검증
- one/all/scalar/rowcount 결과 형태
- 빈 결과 처리
- DB 오류가 공통 예외로 변환되는지 검증
- 사용자 값이 SQL 문자열에 직접 삽입되지 않는지 검토
- MySQL 전용 SQL은 MySQL 통합 테스트로 검증
- CTE-wrapped DML, 주석 선행 문장, multi-statement, `FOR UPDATE`, `CALL`, DDL의 분류/차단 검증
- 모든 public 실행에 안정적인 `query_name`을 전달하고 SQL 본문과 params를 로그에 남기지 않음
- 공개 Raw DML endpoint는 만들지 않는다. 테스트 전용 Service/UoW가 writer session의
  commit/rollback을 소유하고 Repository는 commit하지 않는다. 실패는 HTTP 응답이 아니라
  예외 전파, rollback과 DB 상태 불변으로 검증한다.

### MySQL 통합 환경

- 프로젝트 루트의 `compose.test.yaml`에 MySQL test service를 정의한다.
- 로컬과 CI가 같은 compose 파일, healthcheck, migration 명령과 pytest marker를 사용한다.
- 테스트 시작 시 Alembic head까지 upgrade하고 Raw SQL/migration 테스트를 실행한다.
- migration chain은 현재 head → 신규 revision 순차 upgrade, downgrade, 재-upgrade를 검증한다.
- SQLite는 Base와 Service의 빠른 단위 테스트에만 사용하며 MySQL 방언 승인의 근거로 삼지 않는다.
- CI run마다 고유 database/schema와 명시적 Alembic target을 사용한다. 동일 DB 병렬 실행은
  금지하며 xdist가 필요하면 worker별 DB를 만든다.
- 성공/실패 모두 compose logs를 수집하고 `docker compose down -v`를 항상 실행한다.
- MySQL 전용 strict marker는 `mysql`, CI selector는 `pytest -m mysql`로 통일한다. 일반
  `integration` marker와 섞어 MySQL 검증이 SQLite/단위 통합 테스트에 가려지지 않게 한다.
- marker 실행에서 MySQL test의 selected/executed 수가 1개 이상이고 선택된 테스트의 skip/xfail이
  0인지 확인한다. `pytest -m mysql`이 비-MySQL 테스트를 deselect하는 것은 정상이라서 전체
  `deselected` 수를 실패 조건으로 사용하지 않는다. full suite의 skip/xfail/deselected 0 검증은
  이와 별도 gate다.
- MySQL 8.4의 기본 `caching_sha2_password` 인증을 사용하는 driver라면 `cryptography`를 test/runtime
  dependency에 포함하고 실제 handshake로 검증한다.
- migration fixture는 table만 지우지 말고 `alembic_version`, view, trigger까지 포함한 진짜 빈 schema에서
  시작한다.
- Compose host port는 `127.0.0.1`에만 publish하고 승인된 MySQL image digest를 사용한다. staging과
  production은 인증서 검증 TLS 및 migration/writer/reader 최소권한 계정을 사용하며 test 고정
  자격증명을 재사용하지 않는다.

### Service

- Repository mock/fake로 비즈니스 분기 검증
- Raw row가 Pydantic DTO로 변환되는지 검증
- 잘못된 기간과 상태 전환 검증

### API

- 성공 상태와 응답 schema
- validation 422 및 알려진 오류
- 조회 commit 0회
- 쓰기 성공 commit 1회
- 예외/commit 실패가 성공 응답으로 반환되지 않음
- read-only/writer DB session Dependency 선택

### OpenAPI

- operation ID 중복 없음
- 실제 Router tag와 metadata 일치
- ORM/Raw 응답 schema 모두 존재
- 문서에서 내부 ORM 객체나 `RowMapping`이 직접 노출되지 않음
- 규칙 기반 contract 검사를 기본으로 하고 상품·매출 핵심 schema만 snapshot
- component schema 이름이 전역에서 고유하고 module-qualified 이름(`__`)이 생성되지 않음

## 10. 코드 리뷰 체크리스트

- [ ] View에 SQL 또는 복잡한 도메인 분기가 없는가
- [ ] Dependency가 조립 외 작업을 하지 않는가
- [ ] Service가 HTTP 객체를 알지 않는가
- [ ] Repository가 commit하지 않는가
- [ ] ORM Repository는 ORM Base를 상속하는가
- [ ] Raw Repository는 Raw Base를 상속하는가
- [ ] Raw SQL은 named binding과 식별자 allowlist를 사용하는가
- [ ] read-only/writer DB session이 올바르게 분리됐는가
- [ ] Pydantic이 모든 외부 응답을 검증하는가
- [ ] 라우터가 버전 View → 기능 `<feature>_router` → `AppRegistry.install_routers()` 순서로 자동 결선되는가
- [ ] 신규 ORM 모델마다 기능 소유 `admin.py`와 유효한 `admin_views`가 있는가
- [ ] 기능 추가를 위해 `main.py`, `migrations/env.py`, 중앙 Admin 목록을 수정하지 않았는가
- [ ] Scalar 메타데이터와 실제 구현이 일치하는가
- [ ] 단위, 통합, 트랜잭션, OpenAPI 테스트가 추가됐는가
- [ ] 예외 객체, SQL, bind params, DSN이 application/SQLAlchemy/driver 로그와 오류 응답에 노출되지 않는가
- [ ] HTTP/App/validation/catch-all handler가 raw detail, validation input, body/header와 traceback을
      allowlist 없이 로그·응답에 남기지 않는가
- [ ] Admin 공개 시 인증 backend 또는 동등한 proxy/network 보호가 있고 운영 기본값이 fail-closed인가
- [ ] 신뢰 proxy가 아닌 요청의 `X-Forwarded-For`/`X-Real-IP`를 실제 IP로 사용하지 않는가
- [ ] `/ready`가 public ingress에서 제외되고 catalog/reports 예제의 인증·권한/격리 정책이 명시됐는가
- [ ] Celery serializer/accept-content가 JSON-only이며 pickle/yaml을 거부하는가
- [ ] DB TLS·최소권한, dependency/secret scan, Action SHA와 container digest gate가 있는가
- [ ] 문서에 적힌 경로, symbol, 환경 변수가 실제 코드/config에 존재하는가

## 11. Lifespan 자원 관리 지침

### 기본 구조

`main.py`에는 자원별 startup/shutdown 코드를 나열하지 않는다.

```python
from contextlib import asynccontextmanager

from app.core.resources import manage_application_resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with manage_application_resources(app, registry):
        yield
```

`app/core/resources.py`에서 순서를 명시적으로 관리한다.

```python
@dataclass(slots=True)
class ApplicationResources:
    log_listener: QueueListener | None = None


@asynccontextmanager
async def manage_application_resources(app: FastAPI, registry: AppRegistry):
    resources = ApplicationResources()
    app.state.resources = resources
    try:
        async with AsyncExitStack() as cleanup:
            # 각 manager가 start 중간 실패까지 자체 cleanup한다.
            resources.log_listener = await cleanup.enter_async_context(
                manage_log_listener()
            )

            # 현재 engine은 import 시 생성된다. 1차 단계에서는 생성자가 아니라 종료 소유자다.
            cleanup.push_async_callback(dispose_all_engines_independently)

            # main.py가 이미 discover()와 import_models()를 완료한 동일 객체다.
            # 여기서 새 AppRegistry를 만들거나 모델을 다시 탐색하지 않는다.
            assert registry.enabled_apps
            if app_settings.DEBUG and Base.metadata.tables:
                await create_registered_tables()

            cleanup.push_async_callback(access_log_tasks.close_admission_and_drain)
            yield resources
    finally:
        app.state.resources = None
```

`registry`는 `main.py`에서 `discover()`와 `import_models()`를 완료한 바로 그 인스턴스다.
현재 `create_db_tables()`는 내부에서 `import_all_models()`를 호출하므로 그대로 재사용하지
않고, 모델 준비와 DDL 실행을 `prepare_models(registry)` / `create_registered_tables()`처럼
분리한다. Resource Manager나 DDL 함수가 별도의 `AppRegistry()`를 생성해서는 안 된다.

`manage_log_listener()`처럼 각 자원 context manager가 fallible start와 부분 생성 cleanup을
함께 소유한다. 단순 callback을 쓸 때는 start 전에 안전한 멱등 cleanup을 등록한다.
`AsyncExitStack`은 역순으로 종료하므로 실제 순서는 background admission close/drain → 모든
DB engine 독립 dispose → listener flush/stop이다. dispose 하나가 실패해도 나머지를 시도하고
오류를 집계한다. 전체 20초는 단계 timeout의 단순 합이 아니라 단일 monotonic deadline에서
남은 예산을 전달하며 cleanup/로깅용 reserve를 둔다.

### 모델과 테이블 생성

- `main.py`가 기존 registry로 모델 모듈을 한 번만 import한다.
- `Base.metadata.tables`가 비었으면 DB 접속과 `create_all()`을 생략한다.
- 개발 자동 생성 정책이 활성화된 경우에만 `create_all()`을 실행한다.
- 개발 자동 생성은 단일 worker에서만 허용한다. 다중 worker startup DDL은 거부하고 Alembic
  또는 별도 init job을 사용한다.
- 운영은 Alembic migration을 사용한다.
- 모델 파일이 있다는 사실이 아니라 실제 metadata table 수로 판정한다.

### 장기 자원과 요청 자원

| 종류 | 관리 위치 |
|---|---|
| DB engine/pool | Resource Manager |
| logging queue/listener | Resource Manager에서 마지막 flush/stop |
| access log background tasks | Resource Manager에서 shutdown drain |
| 요청별 AsyncSession | `get_writer_db_session`/`get_read_only_db_session` Dependency |
| Celery broker/backend | Celery worker process |

DB engine/sessionmaker는 기존 DI와 SQLAdmin을 위해 `db/session.py`에 정의해도 된다. 다만
engine pool을 종료하는 주체는 Resource Manager 하나만 둔다. 그러므로 이 단계에서
`ApplicationResources`가 engine을 생성했다고 표현하지 않으며, factory 전환 시에만 생성
소유권도 옮긴다. 반복 app 생성/lifespan 재진입 테스트로 global handle 누수를 검증한다.

### 종료 순서

```text
1. FastAPI가 신규 요청 수신 중단
2. in-flight background task drain
3. DB writer/read/background engine dispose
4. logging queue flush 및 listener stop
```

자원을 해제한다는 이유로 DB table을 drop하지 않는다.

### 자원 Dependency

장기 수명 자원이 필요하면 module global을 새로 만들지 않고 `app.state.resources`에서
Dependency로 제공한다.

```python
def get_application_resources(request: Request) -> ApplicationResources:
    resources = request.app.state.resources
    if resources is None:
        raise RuntimeError("Application resources are not available")
    return resources
```

### 추가 체크리스트

- [ ] startup 중간 실패에도 cleanup이 실행되는가
- [ ] 모델이 없으면 DB 연결을 시도하지 않는가
- [ ] 사용하지 않는 선택 자원을 생성하지 않는가
- [ ] background task가 사용하는 client보다 task를 먼저 종료하는가
- [ ] cleanup 실패가 다음 cleanup을 막지 않는가
- [ ] 단일 monotonic 20초 deadline 안에서 task 최대 5초, DB 최대 10초, logging 최대 5초와
      cleanup reserve가 적용됐는가
- [ ] Celery worker cleanup에 별도 10초 제한이 적용됐는가
- [ ] multi-worker별 DB pool 연결 수가 DB 한도를 넘지 않는가
- [ ] `/health`와 `/ready`의 목적이 분리되어 있는가
- [ ] `/ready`가 writer DB `SELECT 1`을 2초 내 실행하고 실패 시 503을 반환하는가
- [ ] `/ready`가 `Health` tag, `getReadiness`, `HealthResponse` 200/표준 오류 503 계약이며
      Phase 1 inventory 19 paths/31 operations와 최종 inventory 22 paths/37 operations에
      포함되는가
- [ ] startup/shutdown 로그에 secret이 포함되지 않는가
- [ ] shutdown 후 `app.state.resources`에 닫힌 자원 참조가 남지 않는가

## 12. 비동기 구현 지침

### 비동기 적용 판단

`async def`는 비동기 I/O를 await할 때 의미가 있다. 모든 동기 함수를 무조건 async 또는
thread 작업으로 바꾸지 않는다.

| 유형 | 구현 기준 |
|---|---|
| DB/HTTP I/O | async client와 `await` 사용 |
| 파일 logging | QueueHandler로 event loop 밖 listener thread에 위임 |
| bcrypt 등 고비용 CPU | `asyncio.to_thread()` 또는 worker 사용 |
| 짧은 JWT/Pydantic/User-Agent 연산 | event loop에서 동기 실행 허용 |
| Celery task entrypoint | sync 유지, 내부 coroutine bridge 사용 |
| SQLAlchemy metadata DDL | `AsyncConnection.run_sync()` 사용 허용 |

`AsyncSession.execute()`는 await하지만 buffered `Result`의 `mappings()/scalars()/all()` 소비는
동기 API다. 대용량 처리는 별도 stream API와 lifecycle을 설계한다. 하나의 `AsyncSession`은
동시 task가 공유하지 않으며 task마다 독립 session/transaction을 사용한다.

### Queue 기반 logging

운영 파일 handler를 root logger에 직접 연결하지 않는다.

```text
root logger
  -> bounded QueueHandler
  -> QueueListener thread
       -> stdout/stderr
       -> container/runtime log collector
```

production/staging 애플리케이션 파일 handler는 사용하지 않는다. Docker, Kubernetes 또는
운영 agent가 파일 저장과 rotation을 담당하며 각 worker는 독립 queue/listener를 가진다.

Resource Manager는 listener의 lifecycle을 관리한다.

```python
listener = await cleanup.enter_async_context(manage_log_listener())
resources.log_listener = listener
```

`stop_log_listener_async()`는 동기 `listener.stop()`과 flush/join을
`await asyncio.to_thread(...)`로 격리한다.

logging bootstrap은 `python main.py` 경로에만 두지 않는다. `uvicorn main:app` import에서도
설정이 정확히 한 번 수행되고 uvicorn access/error logger가 같은 queue로 handoff되어 중복
출력이 없어야 한다. 표준 `QueueHandler`에 의존해 severity 정책을 암묵 처리하지 말고 bounded
`put_nowait`, drop counter, ERROR/CRITICAL 최소 stderr fallback을 가진 전용 handler를 둔다.
queue가 가득 차도 listener stop sentinel이 삽입되어 종료가 교착되지 않아야 한다.

`engine.echo=False`만으로 SQL과 bind 값의 비노출을 보장할 수 없다. `sqlalchemy.engine`,
`sqlalchemy.pool`, `aiomysql`, `pymysql`, `aiosqlite` 등 SQL/driver logger에 전용 noise filter를
적용하고 SQL echo는 기본 false, 로컬의 명시적 opt-in만 허용한다. application Repository와
commit 경계도 예외 객체 자체를 `%s`, f-string, `exc_info`로 남기지 않고 안정적인 error code,
model/query/operation만 기록한다. Alembic은 `fileConfig(..., disable_existing_loggers=False)`로
기존 보안 filter와 application logger를 제거하지 않아야 한다.

구현 체크리스트:

- [ ] worker별 queue 최대 크기가 10,000건인가
- [ ] 적재가 blocking `put()`이 아닌 `put_nowait()`인가
- [ ] DEBUG/INFO/WARNING drop counter와 rate-limited 관측 신호가 있는가
- [ ] ERROR/CRITICAL에 재귀 없는 최소 stderr fallback이 있는가
- [ ] 정상 shutdown에서 ERROR/CRITICAL 로그를 flush하는가
- [ ] production/staging에 애플리케이션 file handler가 없는가
- [ ] 외부 collector가 저장과 rotation을 담당하는가
- [ ] API request thread에 동기 output handler가 연결되지 않는가
- [ ] uvicorn logger의 중복 출력과 propagate 설정을 검증했는가
- [ ] sentinel secret을 bind/exception/DSN에 넣은 end-to-end 테스트에서 최종 로그와 오류 응답이 깨끗한가
- [ ] SQL noise filter가 INFO SQL은 제거하면서 WARNING/ERROR 관측 신호는 유지하는가

### Background task timeout

```python
runner.close_admission()
snapshot = set(tasks)
done, pending = await asyncio.wait(snapshot, timeout=timeout)
for task in pending:
    task.cancel()
await asyncio.gather(*done, *pending, return_exceptions=True)
```

done callback은 추적 집합에서 제거하기 전에 `task.exception()`을 안전하게 소비하고 보고한다.
drain 시작 뒤 late spawn은 거부한다. 취소 task를 await해야 `finally`, session rollback/close와
cleanup callback이 실행된다. 취소를 삼키는 task에는 남은 global deadline으로 escalation을
적용하고 종료 후 `runner.active == 0`을 검증한다.

### Celery worker 종료

Celery entrypoint는 동기 함수로 유지한다.

```python
@celery_app.task
def task_entrypoint():
    return run_async(async_use_case())
```

worker shutdown signal에서는 event loop가 살아 있는 동안 DB pool을 먼저 dispose한다.
지원 worker pool은 prefork로 제한한다. `worker_process_init`에서 child 전용 loop/engine을 만들고
`worker_process_shutdown`에서 독립·멱등 cleanup한다. 다른 pool을 지원하려면 별도 동시성
설계와 테스트를 먼저 추가한다.
현재 import-time `background_engine`/sessionmaker를 그대로 상속하지 않는다. worker 전용
factory를 도입해 init signal에서 inherited pool을 폐기하고 child handle로 재바인딩한 뒤,
shutdown signal이 그 child handle만 닫는지 검증한다.

```text
worker_process_shutdown
  -> run_async(dispose worker DB resources)
  -> loop.shutdown_asyncgens()
  -> loop.close()
  -> loop reference = None
```

FastAPI Resource Manager를 Celery에서 직접 실행하지 않는다. 공통 DB cleanup primitive만
재사용한다.

Celery message 역직렬화는 worker의 코드 실행 경계이므로 다음 설정을 회귀 보호한다.

```python
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
```

pickle/yaml serializer를 편의상 추가하지 않는다. broker/backend URL은 password를 URL-safe하게
조립하고 로그에는 masking하며, production에서는 TLS와 broker 접근 제어를 별도 배포 계약으로 둔다.

### 금지 패턴

```python
async def handler():
    requests.get(url)           # 동기 HTTP
    time.sleep(1)               # event loop 정지
    open(path).write(data)      # 동기 파일 I/O
    subprocess.run(command)     # 동기 프로세스 대기
```

동기 라이브러리만 사용할 수 있다면 `asyncio.to_thread()`로 격리하거나 Celery 같은 외부
worker로 이동한다. 단, 마이크로초 수준의 짧은 CPU 연산은 thread 전환 비용을 측정한 뒤
결정한다.

## 13. 운영 보안 설정

개발 편의 기능은 운영에서 경고만 남기고 계속 기동하지 않는다. 설정 검증은 startup 초기에
실행하며 staging/production에서는 다음 조건을 위반하면 즉시 실패한다.

| 설정 | local/test | staging/production |
|---|---|---|
| `DEBUG`, API docs | 명시적 opt-in 허용 | 기본 비활성, 활성화 시 기동 실패 또는 승인된 별도 정책 필요 |
| JWT/session secret | test 전용 값 허용 | placeholder, 약한 값, access/refresh 동일 값 거부 |
| Admin | 인증된 개발 환경에서 허용 | 인증 backend 또는 동등한 proxy/network 보호 없으면 기동 거부 |
| CORS | 명시적 origin 사용 | credentials와 wildcard origin 조합 거부 |
| SQL echo | 로컬 명시적 opt-in | 항상 false |
| DB transport/account | local test DB 허용 | 인증서 검증 TLS, migration/writer/reader 최소권한 분리 |
| Proxy headers | 직접 연결값 우선 | 신뢰 proxy allowlist를 통과한 전달 헤더만 사용 |
| 예제 API·`/ready` | 개발 예제/로컬 probe | 인증·권한 또는 network isolation, public ingress 제외 |
| Celery content | JSON | JSON-only, pickle/yaml 거부 |

`ADMIN=false`이면 SQLAdmin과 기능별 `admin.py`를 lazy import하여 `/admin`이 404이고 관련 의존성의
import side effect도 없어야 한다. `ADMIN=true` 자체는 인증이 아니다. 공개할 때는 인증 backend를
등록하거나, 신뢰 가능한 reverse proxy 인증과 network allowlist를 배포 계약 및 테스트로 고정한다.

DB URL은 사용자 입력 문자열 연결 대신 `sqlalchemy.engine.URL.create()` 같은 구조화 API로 만들고,
로그/진단 출력에는 password를 마스킹한다. 오류 응답은 공통 코드와 안전한 메시지만 제공하며 driver의
원문 오류, SQL, params 또는 DSN을 반환하지 않는다.

글로벌 예외 handler도 같은 규칙을 따른다. `HTTPException.detail`, Pydantic validation input,
`str(exc)`, 요청 body/header와 traceback은 기본적으로 민감하다고 보고 일반 응답·로그에 넣지 않는다.
안정적인 error code, 예외 타입, method와 route template만 allowlist로 기록한다. sentinel token을
HTTP/App/validation/catch-all 경로 각각에 주입해 queue log, stderr fallback과 응답을 검사한다.

접속 기록의 `X-Forwarded-For`/`X-Real-IP`는 신뢰 proxy가 덮어쓴 경우에만 사용한다. 인터넷
클라이언트가 직접 보낸 헤더를 실제 IP로 저장하면 감사 기록과 IP 기반 제어가 위조된다. IP/User-Agent
수집에는 길이 제한, 보존 기간과 접근 통제도 둔다.

공개 Raw 집계에는 DB/service timeout을 두고 취소 뒤 session rollback/close가 끝나는지 검증한다.
`/ready`는 DB를 매 호출 probe하므로 일반 ingress에 공개하지 않는다. catalog/reports 예제를 실제
서비스에 활성화할 때는 JWT 인증과 권한 정책 또는 동등한 network isolation을 먼저 적용한다.

## 14. 검수 게이트와 잔여 위험

완료 판정은 명령이 한 번 성공했다는 사실뿐 아니라 같은 결함이 되돌아오지 않게 하는 규칙을 포함한다.
저장소의 deterministic review gate는 pytest, Ruff, cold mypy, Bandit, Alembic single head,
AppRegistry/Admin/Raw SQL 불변식과 OpenAPI contract를 묶고, 각 하위 명령의 비정상 종료를 그대로
실패로 전파한다. subprocess 출력은 UTF-8로 정규화하고 Windows 기본 encoding이 달라도 실패 보고가
다시 예외를 내지 않는지 실패 경로 자체를 테스트한다.
Bandit은 dependency CVE나 CI 공급망을 검사하지 않으므로 lockfile 기반 취약점 검사, secret scan,
GitHub Action commit SHA와 test container image digest 검사를 별도 gate로 실행한다.

문서와 검수 기록은 다음을 함께 관리한다.

- 발견 사항 ledger의 Open Fix가 0인지 확인한다.
- 수정마다 AST/실행 기반 fail-on-revert test 또는 명시적 수동 증거를 연결한다.
- test 전용 ORM model은 별도 `DeclarativeBase`를 사용해 공유 metadata와 migration을 오염시키지 않는다.
- 문서의 파일 경로, symbol, 환경 변수, marker를 코드에서 기계적으로 재검증한다.
- OpenAPI component 이름 충돌, `__`가 포함된 module-qualified schema, operation ID/tag 불일치를 거부한다.
- MySQL marker가 수집만 된 것이 아니라 selected=executed로 실제 실행됐고 선택 대상의 skip/xfail이
  0인지 기록한다. selector가 제외한 비-MySQL 테스트의 deselected 수는 예상값으로 별도 기록한다.
- active-style Phase 0의 cold-cache mypy 8개 파일/29건 오류를 ledger에 등록하고 0건이 되기 전에는
  green 기준선이나 다음 phase 승인으로 표현하지 않는다.

완료 후에도 parser 없는 CTE DML 분류, Admin/예제 endpoint의 인증 범위, 실복제 환경,
성능·pool·logging 처리량, 실제 Celery worker, 브라우저 Scalar 렌더링처럼 검증하지 않은 항목은
통과로 쓰지 않고 owner, 영향, 완화책, 재검토 조건이 있는 residual-risk 목록으로 남긴다.
Auth hardening이 별도 범위라면 login/refresh rate limit·account lockout, bcrypt 72-byte 초과 입력,
JWT algorithm allowlist·reserved claim 덮어쓰기와 refresh replay 방지도 같은 목록에 명시한다.
