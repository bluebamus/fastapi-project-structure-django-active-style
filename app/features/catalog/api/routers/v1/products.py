"""Catalog v1 API 엔드포인트 — 상품 CRUD.

view 는 HTTP 역할만 한다: 파라미터 수신 → Service 호출 → 응답 변환 → (쓰기면) commit.

쓰기 경로는 **응답 DTO 검증을 commit 앞에** 둔다. commit 뒤에 검증하면 만료된 속성을
다시 읽으려다 lazy I/O 가 발생하고, 그 I/O 가 실패하면 이미 커밋된 트랜잭션 위에서
500 이 난다 — 클라이언트는 실패로 보지만 데이터는 저장된 상태가 된다.

조회는 read-only Dependency, 변경은 writer Dependency 를 쓴다(계획서 §7).
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse, NotFoundException
from app.features.catalog.dependencies.catalog_dependencies import (
    get_catalog_service,
    get_catalog_service_readonly,
)
from app.features.catalog.schemas.catalog_schema import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.features.catalog.services.catalog_service import CatalogService

router = APIRouter()

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "상품을 찾을 수 없음"}
}


def _require(product: object | None, product_id: str) -> Any:
    """없으면 404 로 끊는다 — 각 핸들러가 같은 분기를 복사하지 않도록."""
    if product is None:
        raise NotFoundException(
            message="상품을 찾을 수 없습니다.",
            detail={"product_id": product_id},
        )
    return product


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


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses=_NOT_FOUND,
    summary="상품 단건 조회",
    description="상품 하나를 조회합니다.",
    operation_id="getCatalogProduct",
)
async def get_product(
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductResponse:
    product = _require(await service.get_product(product_id), product_id)
    return ProductResponse.model_validate(product)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses=_NOT_FOUND,
    summary="상품 수정",
    description="상품을 부분 수정합니다(전달한 필드만). 빈 요청은 변경 없이 현재 상태를 돌려줍니다.",
    operation_id="updateCatalogProduct",
)
async def update_product(
    payload: ProductUpdate,
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = _require(await service.update_product(product_id, payload), product_id)
    response = ProductResponse.model_validate(product)
    await service.commit()
    return response


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="상품 삭제",
    description="상품을 삭제합니다.",
    operation_id="deleteCatalogProduct",
)
async def delete_product(
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    if not await service.delete_product(product_id):
        raise NotFoundException(
            message="상품을 찾을 수 없습니다.",
            detail={"product_id": product_id},
        )
    await service.commit()
