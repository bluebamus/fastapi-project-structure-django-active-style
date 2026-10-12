"""보호 라우트 테스트용 Bearer 헤더 — 실제 ``TokenService`` 로 서명한 access 토큰을 쓴다.

인증 주체는 무상태(ADR-014)라 DB 에 사용자 행이 없어도 토큰만으로 주체가 된다. 테스트는
``get_current_principal`` 을 override 하지 않고 이 헤더를 보낸다 — 운영과 같은 검증 경로
(서명·claims·``su``)를 지나야 인가 회귀가 잡힌다.
"""

from __future__ import annotations

from app.core.security.dependencies import get_token_service

USER_ID = "00000000-0000-4000-8000-0000000000a1"
OTHER_USER_ID = "00000000-0000-4000-8000-0000000000b2"
SUPERUSER_ID = "00000000-0000-4000-8000-0000000000c3"


def bearer(user_id: str, username: str, *, superuser: bool = False) -> dict[str, str]:
    token = get_token_service().issue_access(user_id, username, superuser)
    return {"Authorization": f"Bearer {token}"}


def user_headers() -> dict[str, str]:
    """일반 사용자 alice."""
    return bearer(USER_ID, "alice")


def other_user_headers() -> dict[str, str]:
    """다른 일반 사용자 mallory — 타인 리소스 403 확인용."""
    return bearer(OTHER_USER_ID, "mallory")


def superuser_headers() -> dict[str, str]:
    return bearer(SUPERUSER_ID, "admin", superuser=True)
