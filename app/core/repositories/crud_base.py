"""
기본 CRUD 베이스 클래스

모든 Repository의 최하위 기반 클래스입니다.
가장 기본적인 CRUD 작업만 제공합니다.

사용법:
    class BaseRepository(CRUDBase[ModelType]):
        # CRUDBase를 상속받아 확장 기능 구현
        ...
"""

from typing import Any, Generic, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.models.models_base import Base

ModelType = TypeVar("ModelType", bound=Base)

# PK 타입은 모델마다 다르다(문자열 UUID, 정수, 외부 시스템 키…). 기본값을 str 로 두어
# 기존 선언 `BaseRepository[Model]` 을 그대로 두면서, 다른 PK 를 쓰는 모델은
# `BaseRepository[Model, int]` 처럼 명시할 수 있게 한다.
PrimaryKeyType = TypeVar("PrimaryKeyType", default=str)


class CRUDBase(Generic[ModelType, PrimaryKeyType]):
    """
    기본 CRUD 베이스 클래스

    가장 기본적인 데이터베이스 CRUD 작업을 제공합니다.
    BaseRepository가 이 클래스를 상속받아 확장 기능을 구현합니다.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        session: 비동기 데이터베이스 세션

    Type Parameters:
        ModelType: Base를 상속한 SQLAlchemy 모델 타입
        PrimaryKeyType: 이 모델의 기본키 타입 (기본값 str)

    Note:
        공통 Base 는 **단일 컬럼 PK** 만 지원하며 기본 이름은 ``id`` 다. 다른 이름을
        쓰는 모델은 ``pk_attr`` 을 지정하고, 복합 PK 는 기능 Repository 로 분리한다.
    """

    model: type[ModelType]
    #: PK 컬럼 이름. 이름이 ``id`` 가 아닌 모델은 하위 클래스에서 재정의한다.
    pk_attr: str = "id"

    def __init__(self, session: AsyncSession) -> None:
        """
        CRUDBase 초기화

        Args:
            session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        self.session = session

    @property
    def _pk(self) -> InstrumentedAttribute[Any]:
        """PK 컬럼 속성. ``pk_attr`` 이 가리키는 실제 컬럼을 돌려준다."""
        # getattr 은 Any 를 돌려준다 — 매핑된 컬럼임을 아는 것은 이 계약(단일 컬럼 PK)뿐이라
        # 여기서 한 번만 좁히고, 호출부는 좁혀진 타입을 쓴다.
        return cast(InstrumentedAttribute[Any], getattr(self.model, self.pk_attr))

    async def _get(self, id: PrimaryKeyType) -> ModelType | None:
        """
        ID로 엔티티를 조회합니다 (내부용).

        PK 는 **변환하지 않고 그대로** 전달한다. 예전 구현은 ``str(id)`` 로 강제
        변환해서, 정수 PK 나 ``UUID`` 객체 PK 를 쓰는 모델의 조회가 조용히 빗나갔다
        (이 저장소의 모델이 마침 문자열 UUID PK 라 드러나지 않았을 뿐이다).

        Args:
            id: 조회할 엔티티의 PK (모델이 선언한 타입 그대로)

        Returns:
            모델 인스턴스 또는 None
        """
        return await self.session.get(self.model, id)

    async def _add(self, entity: ModelType) -> ModelType:
        """
        엔티티를 추가합니다 (내부용).

        Args:
            entity: 추가할 모델 인스턴스

        Returns:
            추가된 모델 인스턴스
        """
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def _update(self, entity: ModelType) -> ModelType:
        """
        엔티티를 업데이트합니다 (내부용).

        Args:
            entity: 업데이트할 모델 인스턴스

        Returns:
            업데이트된 모델 인스턴스
        """
        return await self._add(entity)

    async def _delete(self, entity: ModelType) -> None:
        """
        엔티티를 삭제합니다 (내부용).

        Args:
            entity: 삭제할 모델 인스턴스
        """
        await self.session.delete(entity)
        await self.session.flush()
