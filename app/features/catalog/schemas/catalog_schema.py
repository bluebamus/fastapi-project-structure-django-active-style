"""Catalog API 스키마.

DB 제약은 ORM 컬럼이, API 계약은 여기가 소유한다. 둘을 한쪽으로 몰지 않는 이유는
"저장 가능한 값" 과 "받아도 되는 값" 이 같지 않기 때문이다 — 가격은 컬럼상 음수도
담기지만 API 는 받지 않는다.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    """상품 생성 입력."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"name": "Mechanical Keyboard", "price": "129.00"}]}
    )

    name: str = Field(min_length=1, max_length=200, description="상품명")
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="판매가")


class ProductUpdate(BaseModel):
    """상품 부분 수정 입력.

    모든 필드가 선택이다. 아무것도 넘기지 않은 PATCH 는 오류가 아니라 존재 확인 후
    no-op 이다(계획서 §4).
    """

    model_config = ConfigDict(json_schema_extra={"examples": [{"price": "99.00"}]})

    name: str | None = Field(None, min_length=1, max_length=200, description="상품명")
    price: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2, description="판매가")
    is_active: bool | None = Field(None, description="판매 활성 여부")


class ProductResponse(BaseModel):
    """상품 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="상품 UUID")
    name: str = Field(description="상품명")
    price: Decimal = Field(description="판매가")
    is_active: bool = Field(description="판매 활성 여부")


class ProductListResponse(BaseModel):
    """상품 목록 응답."""

    items: list[ProductResponse] = Field(description="상품 목록")
    total: int = Field(ge=0, description="전체 상품 수")
    skip: int = Field(ge=0, description="건너뛴 수")
    limit: int = Field(ge=1, description="조회 제한 수")
