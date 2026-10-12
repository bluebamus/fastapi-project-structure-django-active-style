"""Auth 서비스 — 회원가입/인증/토큰 발급·회전·로그아웃.

user 도메인의 `User` 모델·`UserRepository` 에 대해 인증한다(자격증명은 users.hashed_password).
auth 는 횡단 관심사라 user 식별 모델에 의존하는 것을 허용한다.

협력 객체(해시·토큰·refresh 저장소)는 생성자로 받는다. 조립은
``dependencies/auth_dependencies.py`` 의 provider 가 한다(service-hardening C-1).
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import InvalidTokenException
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import REFRESH, TokenService
from app.core.services.services_base import BaseService
from app.features.auth.exceptions import (
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from app.features.auth.schemas.auth_schema import RegisterRequest, TokenResponse
from app.features.auth.services.password_hasher import PasswordHasher
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository


class AuthService(BaseService):
    """인증 비즈니스 로직. 커밋은 핸들러가 한다."""

    def __init__(
        self,
        session: AsyncSession,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        refresh_store: RefreshTokenStore,
    ) -> None:
        super().__init__(session)
        self.users = UserRepository(session)
        self.hasher = password_hasher
        self.tokens = token_service
        self.refresh_store = refresh_store

    async def register(self, data: RegisterRequest) -> User:
        """사용자를 생성한다(사용자명 중복 시 409)."""
        if await self.users.get_by_username(data.username) is not None:
            raise UsernameAlreadyExistsException()
        # 해시는 CPU 집약적(수십~수백 ms)이라 이벤트 루프를 막지 않도록 스레드로 격리한다.
        hashed = await asyncio.to_thread(self.hasher.hash, data.password)
        return await self.users.create(
            {
                "username": data.username,
                "email": data.email,
                "hashed_password": hashed,
            }
        )

    async def authenticate(self, username: str, password: str) -> User:
        """사용자명/비밀번호를 검증하고 사용자를 반환한다(실패 시 401).

        저장된 해시가 옛 형식(bcrypt)이면 새 해시로 바꿔 둔다 — 호출자가 커밋한다.
        """
        user = await self.users.get_by_username(username)
        # 사용자 부재/비밀번호 미설정이어도 더미 해시로 항상 같은 검증을 치른다
        # (응답 시간차로 사용자명을 열거하는 타이밍 공격 방지).
        stored = user.hashed_password if user and user.hashed_password else self.hasher.dummy_hash
        ok, new_hash = await asyncio.to_thread(self.hasher.verify_and_update, password, stored)
        if user is None or not user.hashed_password or not user.is_active or not ok:
            raise InvalidCredentialsException()
        if new_hash is not None:
            await self.users.update(user.id, {"hashed_password": new_hash})
        return user

    async def _issue(self, user: User, family: str) -> TokenResponse:
        refresh, jti = self.tokens.issue_refresh(user.id, family)
        await self.refresh_store.register(jti, user.id, family)
        return TokenResponse(
            access_token=self.tokens.issue_access(user.id, user.username),
            refresh_token=refresh,
            expires_in=int(self.tokens.access_ttl.total_seconds()),
        )

    async def issue_tokens(self, user: User) -> TokenResponse:
        """로그인 — 새 family 로 access/refresh 를 발급한다."""
        return await self._issue(user, uuid.uuid4().hex)

    async def rotate(self, refresh_token: str) -> TokenResponse:
        """refresh 토큰을 소비하고 같은 family 로 새 쌍을 발급한다.

        이미 소비된 토큰이 다시 오면 탈취로 보고 family 전체를 폐기한다(ADR-012).
        """
        claims = self.tokens.decode(refresh_token, REFRESH)
        family: str = claims["fam"]
        if await self.refresh_store.consume(claims["jti"]) is None:
            await self.refresh_store.revoke_family(family)
            raise InvalidTokenException()
        if await self.refresh_store.is_family_revoked(family):
            raise InvalidTokenException()
        user = await self.users.get_by_id(claims["sub"])
        if user is None or not user.is_active:
            await self.refresh_store.revoke_family(family)
            raise InvalidTokenException()
        return await self._issue(user, family)

    async def logout(self, refresh_token: str) -> None:
        """refresh 토큰의 family 를 폐기한다. 이미 쓰였거나 폐기된 토큰이어도 성공이다."""
        claims = self.tokens.decode(refresh_token, REFRESH)
        await self.refresh_store.revoke_family(claims["fam"])
