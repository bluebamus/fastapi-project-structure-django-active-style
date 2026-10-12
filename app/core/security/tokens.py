"""JWT 발급·검증 (service-hardening ADR-011).

claims: ``sub, type, iat, nbf, exp, jti, iss, aud`` + access 는 ``username``·``su``(슈퍼유저 여부),
refresh 는 ``fam``.
access 와 refresh 는 서명 키가 다르고 ``type`` 도 검사한다 — 키가 같게 설정돼도 종류 혼동이
막힌다. 검증 실패는 이유와 관계없이 ``InvalidTokenException``(401) 하나로 올린다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from app.core.exception import InvalidTokenException
from config import JWTSettings

TokenType = Literal["access", "refresh"]

ACCESS: TokenType = "access"
REFRESH: TokenType = "refresh"

# 두 종류에 공통인 필수 claim. 하나라도 없으면 PyJWT 가 MissingRequiredClaimError 를 낸다.
_REQUIRED_CLAIMS = ["exp", "iat", "nbf", "sub", "jti", "iss", "aud", "type"]
# 종류별 추가 필수 claim 과 그 타입 — PyJWT 의 require 는 등록 claim 만 다루므로 직접 확인한다.
# access 의 ``su`` 는 인가 판정(`Principal.is_superuser`)의 근거라 bool 이 아니면 거부한다.
_TYPE_CLAIMS: dict[TokenType, dict[str, type]] = {
    ACCESS: {"username": str, "su": bool},
    REFRESH: {"fam": str},
}


class TokenService:
    """JWT access/refresh 토큰을 발급하고 검증한다."""

    def __init__(self, settings: JWTSettings) -> None:
        self._settings = settings
        self.access_ttl = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        self.refresh_ttl = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    def _secret(self, token_type: TokenType) -> str:
        if token_type == ACCESS:
            return self._settings.ACCESS_TOKEN_SECRET_KEY
        return self._settings.REFRESH_TOKEN_SECRET_KEY

    def _encode(
        self, sub: str, token_type: TokenType, ttl: timedelta, extra: dict[str, Any]
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        jti = uuid.uuid4().hex
        payload: dict[str, Any] = {
            "sub": sub,
            "type": token_type,
            "iat": now,
            "nbf": now,
            "exp": now + ttl,
            "jti": jti,
            "iss": self._settings.JWT_ISSUER,
            "aud": self._settings.JWT_AUDIENCE,
            **extra,
        }
        token = jwt.encode(
            payload, self._secret(token_type), algorithm=self._settings.JWT_ALGORITHM
        )
        return token, jti

    def issue_access(self, sub: str, username: str, is_superuser: bool) -> str:
        """access 토큰을 발급한다 — ``su`` 는 발급 시점의 슈퍼유저 여부다."""
        token, _ = self._encode(
            sub, ACCESS, self.access_ttl, {"username": username, "su": is_superuser}
        )
        return token

    def issue_refresh(self, sub: str, family: str) -> tuple[str, str]:
        """refresh 토큰을 발급하고 ``(토큰, jti)`` 를 돌려준다 — jti 는 저장소에 등록한다."""
        return self._encode(sub, REFRESH, self.refresh_ttl, {"fam": family})

    def decode(self, token: str, expected_type: TokenType) -> dict[str, Any]:
        """토큰을 검증하고 claims 를 돌려준다.

        Raises:
            InvalidTokenException: 서명·만료·nbf·iss·aud·필수 claim·종류 중 하나라도 어긋남.
        """
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secret(expected_type),
                algorithms=[self._settings.JWT_ALGORITHM],
                audience=self._settings.JWT_AUDIENCE,
                issuer=self._settings.JWT_ISSUER,
                leeway=self._settings.JWT_LEEWAY_SECONDS,
                options={"require": _REQUIRED_CLAIMS},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException() from exc
        if claims["type"] != expected_type or not all(
            isinstance(claims.get(name), kind) for name, kind in _TYPE_CLAIMS[expected_type].items()
        ):
            raise InvalidTokenException()
        return claims
