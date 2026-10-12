"""ORM 기능 경로를 실제 MySQL 8.4 에 대고 한 번씩 돌린다 (service-hardening F-015).

기능 테스트는 in-memory SQLite 로 View→Service→Repository 를 빠르게 검증하지만, 다음은
**MySQL 에서만** 드러난다. 여기서 실제 서비스·리포지토리 경로로 고정한다.

1. 대표 ORM 기능(catalog) CRUD 가 MySQL 방언에서 그대로 성립한다.
2. `get_all` 의 보조 정렬 키(PK) — created_at 이 같은 행들의 순서가 결정적이고 offset 페이지가
   겹치지 않는다. SQLite 는 삽입 순서로 우연히 맞아 보일 수 있다.
3. username 중복은 collation 을 따른다 — `utf8mb4_unicode_ci` 에서 "Kim" 과 "kim" 은 같은 값이다.
   서비스의 사전 조회도, DB UNIQUE(1062 → `DuplicateException`)도 둘을 같은 것으로 본다.
4. 스키마를 우회해 NOT NULL 컬럼에 None 을 넣으면 strict 모드가 1048 을 내고, 변환기가
   422(`ValidationException`)로 바꾼다 — 500 으로 새지 않는다.
5. 컬럼보다 긴 접속 로그 값은 잘려서 **저장된다**(strict 모드는 자르지 않고 INSERT 를 거부한다).
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.core.exception import DuplicateException, ValidationException
from app.core.security.authorization import OwnershipPolicy
from app.core.security.password_hasher import PasswordHasher
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.catalog_schema import ProductCreate, ProductUpdate
from app.features.catalog.services.catalog_service import CatalogService
from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import UserAccessLogService
from app.features.user.exceptions import UsernameDuplicateException
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.schemas.user_schema import UserCreate
from app.features.user.services.user_service import UserService

pytestmark = pytest.mark.mysql


def _user_service(session):
    # 생성 경로는 refresh 저장소를 쓰지 않는다(비활성화·삭제만 쓴다) — Redis 없이 조립한다.
    return UserService(session, PasswordHasher(), None, OwnershipPolicy())


async def test_catalog_crud_through_service(mysql_session_maker):
    async with mysql_session_maker() as session:
        service = CatalogService(session)
        created = await service.create_product(
            ProductCreate(name="키보드", price=Decimal("129.00"))
        )
        await service.commit()
        product_id = created.id

    async with mysql_session_maker() as session:
        service = CatalogService(session)
        fetched = await service.get_product(product_id)
        assert fetched is not None
        assert (fetched.name, fetched.price, fetched.is_active) == (
            "키보드",
            Decimal("129.00"),
            True,
        )

        updated = await service.update_product(product_id, ProductUpdate(price=Decimal("99.50")))
        await service.commit()
        assert updated is not None and updated.price == Decimal("99.50")

    async with mysql_session_maker() as session:
        service = CatalogService(session)
        items, total = await service.list_products(skip=0, limit=10)
        assert total == 1 and [item.id for item in items] == [product_id]

        assert await service.delete_product(product_id) is True
        await service.commit()

    async with mysql_session_maker() as session:
        assert await CatalogService(session).get_product(product_id) is None


async def test_same_created_at_rows_page_deterministically(mysql_session_maker):
    # UTCDateTime 는 naive 값을 거부한다(ADR-007).
    same_moment = datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
    async with mysql_session_maker() as session:
        repository = ProductRepository(session)
        for index in range(5):
            await repository.create(
                {"name": f"p{index}", "price": Decimal("1.00"), "created_at": same_moment}
            )
        await session.commit()

    async with mysql_session_maker() as session:
        repository = ProductRepository(session)
        first = [p.id for p in await repository.get_all(skip=0, limit=10)]
        second = [p.id for p in await repository.get_all(skip=0, limit=10)]
        pages = [[p.id for p in await repository.get_all(skip=skip, limit=2)] for skip in (0, 2, 4)]

    assert len(first) == 5
    assert first == second, "created_at 이 같아도 순서가 매번 같아야 한다"
    assert [pid for page in pages for pid in page] == first, "offset 페이지가 겹치거나 빠졌다"


async def test_username_duplicate_is_case_insensitive(mysql_session_maker):
    async with mysql_session_maker() as session:
        collation = await session.scalar(
            text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
                "AND COLUMN_NAME = 'username'"
            )
        )
        # 아래 단언의 전제 — compose.test.yaml 의 --collation-server 가 바뀌면 여기서 먼저 깨진다.
        assert collation == "utf8mb4_unicode_ci"

        service = _user_service(session)
        await service.create_user(
            UserCreate(username="Kim", email="kim@example.com", password="password123")
        )
        await service.commit()

    async with mysql_session_maker() as session:
        # 서비스의 사전 조회가 collation 을 따라 "kim" 을 "Kim" 과 같은 것으로 찾는다.
        with pytest.raises(UsernameDuplicateException) as service_error:
            await _user_service(session).create_user(
                UserCreate(username="kim", email="kim2@example.com", password="password123")
            )
        assert service_error.value.status_code == 409

    async with mysql_session_maker() as session:
        # 사전 조회를 건너뛰어도 UNIQUE 인덱스가 같은 판정을 내린다(1062 → 409).
        with pytest.raises(DuplicateException) as db_error:
            await UserRepository(session).create({"username": "kim", "email": "kim3@example.com"})
        assert db_error.value.status_code == 409
        assert "kim3@example.com" not in str(db_error.value.detail)


async def test_explicit_null_on_not_null_column_maps_to_422(mysql_session_maker):
    async with mysql_session_maker() as session:
        product = await ProductRepository(session).create(
            {"name": "이름 있음", "price": Decimal("10.00")}
        )
        await session.commit()
        product_id = product.id

    async with mysql_session_maker() as session:
        # 스키마(PatchSchema)를 우회해 DB 까지 보낸다 — strict 모드 1048 이 변환기를 거친다.
        with pytest.raises(ValidationException) as error:
            await ProductRepository(session).update(product_id, {"name": None})
        await session.rollback()

    assert error.value.status_code == 422
    assert error.value.detail == {"model": "Product"}

    async with mysql_session_maker() as session:
        stored = await session.get(Product, product_id)
        assert stored is not None and stored.name == "이름 있음"


async def test_long_access_log_values_are_truncated_and_stored(mysql_session_maker):
    long_path = "/p" + "x" * 3000
    long_language = "ko-KR," * 100
    long_agent = "Agent/" + "a" * 5000  # Text 컬럼 — 자르지 않는다

    async with mysql_session_maker() as session:
        await UserAccessLogService(session).create_access_log(
            {
                "ip_address": "203.0.113.7",
                "request_path": long_path,
                "request_method": "GET",
                "accept_language": long_language,
                "user_agent": long_agent,
            }
        )
        await session.commit()

    async with mysql_session_maker() as session:
        stored = (await session.execute(select(UserAccessLog))).scalars().one()

    assert stored.request_path == long_path[:2048]
    assert stored.accept_language == long_language[:255]
    assert stored.user_agent == long_agent
