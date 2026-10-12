"""
User Service

사용자 비즈니스 로직. 세션을 주입받아 Repository 를 구성하고, 협력 객체(해시기·refresh
저장소·소유권 판정)는 생성자로 받는다(service-hardening C-1).
commit 은 여기서 하지 않는다. 요청에서는 쓰기 핸들러 본문이 응답 DTO 검증 뒤 한 번,
요청 밖에서는 background_db_session() 을 연 호출자가 한다. 예외 시 rollback 은 세션
Dependency(또는 컨텍스트)가 맡는다.

권한 규칙(ADR-016): 목록·생성·삭제는 라우트가 슈퍼유저로 막고, 단건 조회·수정은 본인
또는 슈퍼유저(`OwnershipPolicy` — 사용자 자신이 "소유자"다), ``is_active``·``is_superuser``
변경은 슈퍼유저만 한다. 비활성화·강등·삭제는 그 사용자의 refresh family 를 모두 폐기한다.
"""

import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.password_hasher import PasswordHasher
from app.core.security.refresh_store import RefreshTokenStore
from app.core.services.services_base import BaseService
from app.features.user.exceptions import (
    PrivilegedFieldException,
    UsernameDuplicateException,
    UserNotFoundException,
)
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.schemas.user_schema import UserCreate, UserUpdate

# 슈퍼유저만 바꿀 수 있는 필드.
_PRIVILEGED_FIELDS = frozenset({"is_active", "is_superuser"})


class UserService(BaseService):
    """사용자 비즈니스 로직 (세션 기반)."""

    def __init__(
        self,
        session: AsyncSession,
        hasher: PasswordHasher,
        refresh_store: RefreshTokenStore,
        policy: OwnershipPolicy,
    ) -> None:
        super().__init__(session)
        self.repository = UserRepository(session)
        self.hasher = hasher
        self.refresh_store = refresh_store
        self.policy = policy

    async def create_user(self, data: UserCreate) -> User:
        """사용자를 생성한다. 사용자명 중복 시 UsernameDuplicateException."""
        self.log.debug("사용자 생성: username=%s", data.username)
        if await self.repository.get_by_username(data.username) is not None:
            raise UsernameDuplicateException(detail={"username": data.username})
        # 해시는 CPU 집약적이라 이벤트 루프를 막지 않도록 스레드로 격리한다(auth 가입과 같다).
        hashed = await asyncio.to_thread(self.hasher.hash, data.password)
        return await self.repository.create(
            {**data.model_dump(exclude={"password"}), "hashed_password": hashed}
        )

    async def get_user(self, user_id: str, principal: Principal) -> User:
        """사용자를 조회한다. 본인·슈퍼유저가 아니면 403, 없으면 404."""
        self.log.debug("사용자 조회: id=%s", user_id)
        # 존재 확인보다 권한 판정이 먼저다 — 남의 id 로 존재 여부(404/403)를 떠보지 못한다.
        self.policy.ensure_can_modify(user_id, principal)
        return await self._get(user_id)

    async def _get(self, user_id: str) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException(detail={"id": user_id})
        return user

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """사용자 목록과 전체 개수를 조회한다."""
        self.log.debug("사용자 목록 조회: skip=%s limit=%s", skip, limit)
        users = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return users, total

    async def update_user(self, user_id: str, data: UserUpdate, principal: Principal) -> User:
        """사용자를 부분 수정한다.

        Raises:
            ForbiddenException: 본인·슈퍼유저가 아님(403).
            PrivilegedFieldException: 슈퍼유저가 아닌데 ``is_active``·``is_superuser`` 를 보냄(403).
            UserNotFoundException: 없음(404).
        """
        self.log.debug("사용자 수정: id=%s", user_id)
        self.policy.ensure_can_modify(user_id, principal)
        changes = data.model_dump(exclude_unset=True)
        if not principal.is_superuser and _PRIVILEGED_FIELDS & changes.keys():
            raise PrivilegedFieldException()
        existing = await self._get(user_id)  # 존재 보장(없으면 404)
        if changes.get("is_active") is False or changes.get("is_superuser") is False:
            # 비활성화·강등이면 기존 로그인 세션을 끊는다 — 이미 발급된 access 토큰은
            # 만료(기본 15분)까지 남는다(R-201).
            await self.refresh_store.revoke_user(user_id)
        updated = await self.repository.update(user_id, changes)
        # updated 가 None 이면 변경행 0(동일 값 no-op, MySQL changed-rows 의미). 존재는 이미
        # 보장됐으므로 404 가 아니라 현재 엔티티를 반환한다.
        return updated if updated is not None else existing

    async def delete_user(self, user_id: str) -> None:
        """사용자를 삭제하고 그 사용자의 refresh family 를 모두 폐기한다. 없으면 404."""
        self.log.debug("사용자 삭제: id=%s", user_id)
        if not await self.repository.delete(user_id):
            raise UserNotFoundException(detail={"id": user_id})
        await self.refresh_store.revoke_user(user_id)
