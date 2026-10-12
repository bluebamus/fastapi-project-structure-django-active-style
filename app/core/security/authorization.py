"""인가 — 인증 주체와 소유권 판정 (service-hardening ADR-014·ADR-015·ADR-016).

권한은 슈퍼유저/일반 2단계다. 판정 규칙은 여기 한 곳에만 둔다 — 서비스마다 흩어지면
하나가 빠져도 보이지 않는다(IDOR).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exception import ForbiddenException


@dataclass(frozen=True, slots=True)
class Principal:
    """검증된 access 토큰이 말하는 요청 주체. DB 를 조회하지 않고 claims 에서 만든다.

    ``is_superuser`` 는 토큰 발급 시점의 값이다 — 강등은 access 만료(기본 15분)와
    refresh 폐기로 반영된다(R-201).
    """

    id: str
    username: str
    is_superuser: bool


class OwnershipPolicy:
    """수정·삭제 권한 판정 — 소유자 또는 슈퍼유저만 통과한다."""

    def ensure_can_modify(self, owner_id: str | None, principal: Principal) -> None:
        """소유자도 슈퍼유저도 아니면 403.

        ``owner_id`` 가 None(작성자 컬럼 도입 전의 행)이면 슈퍼유저만 수정할 수 있다.

        Raises:
            ForbiddenException: 권한이 없을 때.
        """
        if principal.is_superuser:
            return
        if owner_id is None or owner_id != principal.id:
            raise ForbiddenException()
