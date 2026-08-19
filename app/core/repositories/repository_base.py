"""
기본 Repository 클래스

모든 Repository의 기반이 되는 Generic 클래스입니다.
CRUD 작업과 N+1 문제 해결을 위한 Eager Loading 메서드를 제공합니다.

사용법:
    class UserRepository(BaseRepository[User]):
        model = User

    # 기본 CRUD
    user = await repo.create({"name": "John"})
    user = await repo.get_by_id("id")
    users = await repo.get_all()

    # N+1 해결 - Eager Loading
    user = await repo.get_by_id_with("id", relations=["posts", "profile"])
    users = await repo.get_all_with(relations=["posts"])
"""

from collections.abc import Sequence
from typing import Any, Generic

from sqlalchemy import exists as sql_exists
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    defer,
    joinedload,
    load_only,
    selectinload,
    subqueryload,
)
from sqlalchemy.sql import Select

from app.core.exception import (
    DatabaseException,
    DuplicateException,
    NotFoundException,
    ValidationException,
)
from app.core.repositories.crud_base import CRUDBase, ModelType, PrimaryKeyType
from app.utils.logs import get_logger

logger = get_logger("repository")


class BaseRepository(CRUDBase[ModelType, PrimaryKeyType], Generic[ModelType, PrimaryKeyType]):
    """
    기본 Repository 클래스

    SQLAlchemy 모델에 대한 CRUD 작업과 N+1 문제 해결을 위한
    Eager Loading 메서드를 제공합니다.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        session: 비동기 데이터베이스 세션

    Type Parameters:
        ModelType: Base를 상속한 SQLAlchemy 모델 타입

    Example:
        class UserRepository(BaseRepository[User]):
            model = User

        repo = UserRepository(session)
        user = await repo.get_by_id("123")  # 타입: User | None
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        """
        BaseRepository 초기화

        Args:
            session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        super().__init__(session)

    # ========================================================================
    # LOADING STRATEGY HELPERS (내부 헬퍼 메서드)
    # ========================================================================

    def _apply_eager_loading(
        self,
        stmt: Select,
        relations: list[str] | None = None,
        strategy: str = "selectin",
    ) -> Select:
        """
        Eager Loading 전략을 쿼리에 적용합니다.

        N+1 문제를 해결하기 위해 관계 데이터를 미리 로드합니다.

        Args:
            stmt: SQLAlchemy Select 문
            relations: 로드할 관계 필드 목록 (예: ["posts", "comments"])
            strategy: 로딩 전략
                - "selectin": SELECT ... WHERE id IN (...) - 1:N 컬렉션에 권장
                - "joined": LEFT JOIN으로 한 번에 조회 - 1:1, N:1에 권장
                - "subquery": 서브쿼리 사용 - selectin과 유사

        Returns:
            Eager Loading이 적용된 Select 문

        Note:
            중첩 관계도 지원합니다: "posts.comments" -> posts와 그 comments 로드
        """
        if not relations:
            return stmt

        loader_map = {
            "selectin": selectinload,
            "joined": joinedload,
            "subquery": subqueryload,
        }
        loader = loader_map.get(strategy, selectinload)

        for relation in relations:
            # 중첩 관계 지원: "posts.comments" -> posts -> comments
            parts = relation.split(".")

            # 첫 파트는 현재 모델의 관계 속성으로 로더를 시작한다.
            attr = getattr(self.model, parts[0])
            load_option = loader(attr)
            # 다음 파트는 "직전 관계가 가리키는 모델"의 속성이어야 한다. SQLAlchemy 2.0
            # 에서는 문자열 기반 관계 로딩이 제거되었으므로, mapper 를 따라가며 실제
            # QueryableAttribute 로 해석한다(문자열 전달 시 런타임 오류).
            related_model = attr.property.mapper.class_
            for part in parts[1:]:
                attr = getattr(related_model, part)
                load_option = load_option.selectinload(attr)
                related_model = attr.property.mapper.class_

            stmt = stmt.options(load_option)

        return stmt

    def _apply_column_loading(
        self,
        stmt: Select,
        only_columns: list[str] | None = None,
        defer_columns: list[str] | None = None,
    ) -> Select:
        """
        컬럼 레벨 로딩을 적용합니다 (부분 로딩).

        대용량 컬럼(TEXT, BLOB 등)을 제외하여 성능을 최적화합니다.

        Args:
            stmt: SQLAlchemy Select 문
            only_columns: 로드할 컬럼만 지정 (나머지는 지연 로딩)
            defer_columns: 지연 로딩할 컬럼 지정

        Returns:
            컬럼 로딩이 적용된 Select 문
        """
        if only_columns:
            columns = [getattr(self.model, col) for col in only_columns]
            stmt = stmt.options(load_only(*columns))

        if defer_columns:
            for col in defer_columns:
                stmt = stmt.options(defer(getattr(self.model, col)))

        return stmt

    # ========================================================================
    # CREATE (생성)
    # ========================================================================

    def _log_db_error(self, operation: str, error: Exception) -> None:
        """DB 오류를 안전한 context 만으로 기록한다.

        예외 원문에는 SQL 조각과 파라미터 값이 그대로 실려 온다. 응답은 물론
        로그에도 남기지 않고 연산·모델·예외 타입만 남긴다 (C-5).
        """
        logger.error(
            "[%s] 데이터베이스 오류 model=%s error_type=%s",
            operation,
            self.model.__name__,
            type(error).__name__,
        )

    async def create(self, data: dict[str, Any]) -> ModelType:
        """
        새로운 레코드를 생성합니다.

        Args:
            data: 생성할 데이터 딕셔너리

        Returns:
            생성된 모델 인스턴스

        Raises:
            DuplicateException: 중복 데이터가 존재하는 경우
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.create({"name": "John", "email": "john@example.com"})
        """
        # 호출자의 dict 를 그대로 쓰지 않는다 — Repository 가 호출자 자료구조를
        # 바꾸면, 같은 dict 를 재사용하는 쪽에서 원인 찾기 어려운 버그가 난다.
        payload = dict(data)

        # PK 생성은 **모델**이 소유한다(UUIDPrimaryKeyMixin 의 default). Base 가
        # id 를 끼워넣으면 정수 PK·시퀀스·외부 시스템 키를 쓰는 모델에서 어긋난다.
        try:
            instance = self.model(**payload)
            return await self._add(instance)  # CRUDBase 메서드 활용
        except IntegrityError as e:
            self._log_db_error("CREATE", e)
            raise DuplicateException(
                message="이미 존재하는 데이터입니다.",
                detail={"model": self.model.__name__},
            ) from e
        except SQLAlchemyError as e:
            self._log_db_error("CREATE", e)
            raise DatabaseException(
                message="데이터 생성 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__},
            ) from e

    # ========================================================================
    # READ - 기본 조회
    # ========================================================================

    async def get_by_id(self, id: PrimaryKeyType) -> ModelType | None:
        """
        ID로 레코드를 조회합니다.

        Args:
            id: 조회할 레코드의 ID

        Returns:
            모델 인스턴스 또는 None

        Example:
            user = await repo.get_by_id("550e8400-e29b-41d4-a716-446655440000")
        """
        return await self._get(id)  # CRUDBase 메서드 활용

    async def get_by_id_or_raise(self, id: PrimaryKeyType) -> ModelType:
        """
        ID로 레코드를 조회하고, 없으면 예외를 발생시킵니다.

        Args:
            id: 조회할 레코드의 ID

        Returns:
            모델 인스턴스

        Raises:
            NotFoundException: 레코드가 존재하지 않는 경우

        Example:
            user = await repo.get_by_id_or_raise("user-123")  # 없으면 예외 발생
        """
        instance = await self.get_by_id(id)
        if instance is None:
            raise NotFoundException(
                message=f"{self.model.__name__}을(를) 찾을 수 없습니다.",
                detail={"model": self.model.__name__, "id": id},
            )
        return instance

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """
        모든 레코드를 조회합니다.

        Args:
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            모델 인스턴스 목록

        Example:
            users = await repo.get_all(skip=0, limit=100)
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """
        레코드 수를 반환합니다.

        Args:
            **filters: 필터 조건 (선택적)

        Returns:
            레코드 수

        Example:
            total = await repo.count()
            active_count = await repo.count(is_active=True)
        """
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: PrimaryKeyType) -> bool:
        """
        ID로 레코드 존재 여부를 확인합니다.

        Args:
            id: 확인할 레코드의 ID

        Returns:
            존재 여부 (True/False)

        Example:
            if await repo.exists("user-123"):
                print("User exists")
        """
        # COUNT(*) 는 조건에 맞는 행을 끝까지 센다. 존재 여부만 알면 되므로
        # EXISTS 로 첫 행에서 멈춘다.
        stmt = select(sql_exists().where(self._pk == id))
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    # ========================================================================
    # UPDATE (수정)
    # ========================================================================

    async def update(self, id: PrimaryKeyType, data: dict[str, Any]) -> ModelType | None:
        """
        ID로 레코드를 업데이트합니다.

        Args:
            id: 업데이트할 레코드의 ID
            data: 업데이트할 데이터 딕셔너리

        Returns:
            업데이트된 모델 인스턴스 또는 None

        Raises:
            DuplicateException: 중복 데이터로 인한 제약 조건 위반
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.update("user-123", {"name": "New Name"})
        """
        payload = dict(data)  # 호출자 dict 불변

        # bulk DML 대신 **먼저 단일 엔티티를 조회**한다. 그래야 없는 행과 변경이
        # 없는 행을 구분할 수 있고, ORM 이벤트와 onupdate 가 정상 경로로 돈다.
        entity = await self._get(id)
        if entity is None:
            return None

        # 빈 PATCH 는 오류가 아니다 — 존재만 확인하고 아무것도 바꾸지 않는다.
        if not payload:
            return entity

        known = set(self.model.__mapper__.column_attrs.keys())
        unknown = sorted(set(payload) - known)
        if unknown:
            raise ValidationException(
                message="알 수 없는 필드는 수정할 수 없습니다.",
                detail={"model": self.model.__name__, "unknown_fields": unknown},
            )
        if self.pk_attr in payload:
            raise ValidationException(
                message="기본키는 수정할 수 없습니다.",
                detail={"model": self.model.__name__, "field": self.pk_attr},
            )

        try:
            for field, value in payload.items():
                setattr(entity, field, value)
            await self._flush()
            return await self._refresh(entity)
        except IntegrityError as e:
            self._log_db_error("UPDATE", e)
            raise DuplicateException(
                message="업데이트할 데이터가 기존 데이터와 충돌합니다.",
                detail={"model": self.model.__name__},
            ) from e
        except SQLAlchemyError as e:
            self._log_db_error("UPDATE", e)
            raise DatabaseException(
                message="데이터 업데이트 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__},
            ) from e

    # ========================================================================
    # DELETE (삭제)
    # ========================================================================

    async def delete(self, id: PrimaryKeyType) -> bool:
        """
        ID로 레코드를 삭제합니다.

        Args:
            id: 삭제할 레코드의 ID

        Returns:
            삭제 성공 여부 (True/False)

        Raises:
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            if await repo.delete("user-123"):
                print("User deleted")
        """
        # update 와 같은 이유로 bulk DML 을 쓰지 않는다 — 먼저 엔티티를 조회한다.
        entity = await self._get(id)
        if entity is None:
            return False

        try:
            await self._delete(entity)
            return True
        except IntegrityError as e:
            self._log_db_error("DELETE", e)
            raise DatabaseException(
                message="다른 데이터에서 참조 중이어서 삭제할 수 없습니다.",
                detail={"model": self.model.__name__},
            ) from e
        except SQLAlchemyError as e:
            self._log_db_error("DELETE", e)
            raise DatabaseException(
                message="데이터 삭제 중 오류가 발생했습니다.",
                detail={"model": self.model.__name__},
            ) from e

    # ========================================================================
    # UPSERT (생성 또는 수정)
    # ========================================================================
