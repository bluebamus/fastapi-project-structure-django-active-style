"""Pagination utility.

여러 프로젝트에서 공통으로 쓰이는 페이지네이션 유틸. `app/utils` 하위의 독립
모듈로, 재사용 가능한 응답 컨테이너(`PaginatedResponse`)와 범용 조회 헬퍼
(`get_paginated`)를 제공한다.

`PaginatedResponse` 는 **표준 라이브러리 `@dataclass`** 로 정의된 데이터 컨테이너다.
- 모든 필드는 기본값을 가진다(초기값 고정).
- `create()` 팩토리가 `return cls(...)` 로 최종 반환 데이터 타입을 고정한다.

설계 결정(트레이드오프, 감사 승인):
    stdlib dataclass 는 런타임 검증이 없고, FastAPI `response_model` 로 직접 쓸 때
    제네릭 OpenAPI 스키마 표현이 제한적이다. 응답 검증/스키마 충실도가 필요하면
    라우트에서 Pydantic 모델로 변환·감싸서 반환한다. 순수 데이터 컨테이너로서의
    사용을 전제로 한 선택이다.

적용 현황(의도된 상태):
    이 모듈은 소비자가 가져다 쓰는 **독립 재사용 유틸**이다. 이 저장소의 도메인
    엔드포인트는 각자 `<Name>ListResponse`(skip/limit) 스키마를 사용하며 이 유틸을
    배선하지 않는다. 즉 "제공하되 앱에는 미배선"이 의도된 상태다(소유자 결정).
    소비 프로젝트가 page/page_size 방식이 필요할 때 `get_paginated`/`PaginatedResponse`
    를 사용하면 된다.

사용 예시:
    from app.utils.pagination import PaginatedResponse, get_paginated

    result = await get_paginated(
        session=session,
        model=Item,
        item_schema=ItemOut,
        page=1,
        page_size=20,
    )
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class _HasId(Protocol):
    """페이지네이션 대상 모델의 최소 계약: `id` 속성 보유.

    utils 는 상위 계층(core)에 의존하지 않으므로, ORM Base 를 직접 import 하지
    않고 구조적 타입(Protocol)으로 `id` 요구만 표현한다.
    """

    id: Any


T = TypeVar("T", bound=BaseModel)
ModelT = TypeVar("ModelT", bound=_HasId)


@dataclass
class PaginatedResponse(Generic[T]):
    """페이지네이션 응답 컨테이너 (재사용 가능, stdlib dataclass).

    `return cls()` 로 반환 타입을 고정하기 위해, 필드는 기본값과 함께 정의된다.
    컨테이너 데이터 이외의 클래스 변수/상태는 두지 않는다.

    Fields:
        items: 현재 페이지 데이터 목록
        total: 전체 데이터 수
        page: 현재 페이지(1부터)
        page_size: 페이지당 데이터 수
        total_pages: 전체 페이지 수
        has_next: 다음 페이지 존재 여부
        has_prev: 이전 페이지 존재 여부
    """

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """페이지 메타데이터를 계산해 페이지네이션 응답을 생성한다.

        Args:
            items: 현재 페이지의 데이터 목록
            total: 전체 데이터 수
            page: 현재 페이지 번호
            page_size: 페이지당 데이터 수

        Returns:
            PaginatedResponse[T]: 완성된 페이지네이션 응답
        """
        total_pages = math.ceil(total / page_size) if total > 0 else 1
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


async def get_paginated(
    session: AsyncSession,
    model: type[ModelT],
    item_schema: type[T],
    page: int = 1,
    page_size: int = 20,
    max_page_size: int = 100,
    filters: dict[str, Any] | None = None,
    order_by: str | None = "created_at",
    order_desc: bool = True,
    transform_fn: Callable[[ModelT], T] | None = None,
) -> "PaginatedResponse[T]":
    """범용 페이지네이션 조회 함수.

    Args:
        session: SQLAlchemy AsyncSession
        model: SQLAlchemy 모델 클래스
        item_schema: 항목 변환용 Pydantic 스키마 클래스
        page: 페이지 번호(1부터, 기본 1)
        page_size: 페이지당 데이터 수(기본 20)
        max_page_size: 최대 페이지 크기(기본 100)
        filters: 필터 조건 딕셔너리
        order_by: 정렬 기준 컬럼명(기본 "created_at")
        order_desc: 내림차순 여부(기본 True)
        transform_fn: 모델→스키마 변환 함수(None 이면 필드명 매칭 자동 변환)

    Returns:
        PaginatedResponse[T]: 페이지네이션된 응답
    """
    page_size = min(page_size, max_page_size)
    offset = (page - 1) * page_size

    query = select(model)
    count_query = select(func.count(model.id))

    # 필터 적용
    if filters:
        for field_name, value in filters.items():
            if value is not None and hasattr(model, field_name):
                column = getattr(model, field_name)
                query = query.where(column == value)
                count_query = count_query.where(column == value)

    # 전체 개수
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # 정렬
    if order_by and hasattr(model, order_by):
        order_column = getattr(model, order_by)
        query = query.order_by(order_column.desc() if order_desc else order_column.asc())

    # 페이지네이션 적용
    query = query.offset(offset).limit(page_size)
    result = await session.execute(query)
    records = result.scalars().all()

    # 스키마 변환
    if transform_fn:
        items = [transform_fn(record) for record in records]
    else:
        items = []
        for record in records:
            item_data = {}
            for field_name in item_schema.model_fields.keys():
                if hasattr(record, field_name):
                    item_data[field_name] = getattr(record, field_name)
            items.append(item_schema(**item_data))

    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
