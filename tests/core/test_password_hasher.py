"""`PasswordHasher` — Argon2 해시·검증·옛 bcrypt 해시 이전 (service-hardening F1, ADR-010)."""

import bcrypt
import pytest

from app.core.security.password_hasher import PasswordHasher


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return PasswordHasher()


def test_hash_is_argon2_and_verifies(hasher):
    hashed = hasher.hash("s3cret-pw")
    assert hashed.startswith("$argon2id$")
    assert hasher.verify_and_update("s3cret-pw", hashed) == (True, None)
    assert hasher.verify_and_update("wrong", hashed) == (False, None)


def test_legacy_bcrypt_hash_verifies_and_returns_new_argon2_hash(hasher):
    legacy = bcrypt.hashpw(b"s3cret-pw", bcrypt.gensalt()).decode()
    ok, new_hash = hasher.verify_and_update("s3cret-pw", legacy)
    assert ok is True
    assert new_hash is not None and new_hash.startswith("$argon2id$")
    assert hasher.verify_and_update("s3cret-pw", new_hash) == (True, None)


def test_legacy_bcrypt_wrong_password_returns_no_hash(hasher):
    legacy = bcrypt.hashpw(b"s3cret-pw", bcrypt.gensalt()).decode()
    assert hasher.verify_and_update("wrong", legacy) == (False, None)


def test_legacy_bcrypt_uses_the_old_72_byte_truncation(hasher):
    """이전 버전은 72바이트로 잘라 해시했다 — 긴 비밀번호 계정도 이전되어야 한다."""
    long_pw = "가" * 40  # UTF-8 120바이트
    legacy = bcrypt.hashpw(long_pw.encode()[:72], bcrypt.gensalt()).decode()
    ok, new_hash = hasher.verify_and_update(long_pw, legacy)
    assert ok is True and new_hash is not None


def test_long_password_hashes_without_truncation(hasher):
    long_pw = "a" * 200
    hashed = hasher.hash(long_pw)
    assert hasher.verify_and_update(long_pw, hashed)[0] is True
    assert hasher.verify_and_update("a" * 72, hashed)[0] is False


@pytest.mark.parametrize("stored", ["", "plain-text", "$2b$broken", "$argon2id$broken"])
def test_unknown_or_broken_hash_is_a_mismatch(hasher, stored):
    assert hasher.verify_and_update("anything", stored) == (False, None)


def test_dummy_hash_is_argon2(hasher):
    assert hasher.dummy_hash.startswith("$argon2id$")
    assert hasher.verify_and_update("x", hasher.dummy_hash)[0] is False
