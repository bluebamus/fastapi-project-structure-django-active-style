"""비밀번호 해시 (service-hardening ADR-010).

새 해시는 Argon2(pwdlib). 이전 버전이 저장한 bcrypt 해시(``$2`` 접두사)는 그때 규칙
(UTF-8 72바이트 절단)으로 검증하고, 맞으면 Argon2 새 해시를 함께 돌려준다 — 로그인 시점에
다시 저장해 점진적으로 옮긴다. 모든 연산이 CPU 집약적이라 호출자는 스레드로 격리한다.
"""

from __future__ import annotations

import bcrypt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

# 이전 버전(bcrypt 직접 사용)이 해시 전에 비밀번호를 잘라 낸 길이. bcrypt 는 72바이트
# 넘는 입력을 거부하므로 같은 규칙으로 잘라야 기존 해시가 맞는다.
_LEGACY_BCRYPT_MAX_BYTES = 72

# 새 비밀번호 길이 규칙 — 가입(auth)·사용자 생성(user)·운영 스크립트가 같은 값을 쓴다.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class PasswordHasher:
    """Argon2 해시 + 기존 bcrypt 해시 검증·이전."""

    def __init__(self) -> None:
        self._hash = PasswordHash((Argon2Hasher(),))
        # 사용자가 없거나 비밀번호가 없을 때도 같은 비용의 검증을 치르기 위한 해시.
        # 응답 시간 차이로 사용자명을 열거하는 것을 막는다.
        self.dummy_hash = self._hash.hash("constant-time-dummy-password")

    def hash(self, password: str) -> str:
        return self._hash.hash(password)

    def verify_and_update(self, password: str, stored_hash: str) -> tuple[bool, str | None]:
        """``(일치 여부, 새로 저장할 해시 또는 None)`` 을 돌려준다.

        bcrypt 해시가 맞으면 항상 새 Argon2 해시를, Argon2 해시는 매개변수가 바뀌었을 때만
        새 해시를 준다. 형식을 모르는 해시는 불일치다.
        """
        if stored_hash.startswith("$2"):
            try:
                ok = bcrypt.checkpw(
                    password.encode("utf-8")[:_LEGACY_BCRYPT_MAX_BYTES],
                    stored_hash.encode("utf-8"),
                )
            except ValueError:
                return False, None
            return (True, self.hash(password)) if ok else (False, None)
        try:
            return self._hash.verify_and_update(password, stored_hash)
        except UnknownHashError:
            return False, None
