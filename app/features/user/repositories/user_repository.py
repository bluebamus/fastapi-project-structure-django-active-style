"""User Repository — 사용자 데이터 접근.

BaseRepository 의 CRUD 를 그대로 사용하고, username 조회만 특화로 추가한다.
"""

from sqlalchemy import select

from app.core.repositories.repository_base import BaseRepository
from app.features.user.models.models import User


class UserRepository(BaseRepository[User, str]):
    """사용자 Repository."""

    model = User

    async def get_by_username(self, username: str) -> User | None:
        """사용자명으로 단건 조회한다.

        공통 Base 의 filter 기반 조회에 기대지 않고 이 기능 Repository 가 직접
        소유한다 — 어떤 컬럼으로 무엇을 찾는지가 여기 드러나야 한다(계획서 §4).
        """
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
