"""`TokenService` — claims·만료·iss/aud·필수 claim·종류 혼동·nbf (service-hardening F1, ADR-011)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.exception import InvalidTokenException
from app.core.security.tokens import ACCESS, REFRESH, TokenService
from config import JWTSettings

_SETTINGS = JWTSettings(
    _env_file=None,
    ACCESS_TOKEN_SECRET_KEY="a" * 64,
    REFRESH_TOKEN_SECRET_KEY="r" * 64,
    JWT_ISSUER="test-iss",
    JWT_AUDIENCE="test-aud",
    JWT_LEEWAY_SECONDS=0,
)


@pytest.fixture
def tokens() -> TokenService:
    return TokenService(_SETTINGS)


def _forge(secret: str = "a" * 64, algorithm: str = "HS256", **overrides):
    """정상 access claims 에서 일부만 바꾼 토큰을 직접 서명한다."""
    now = datetime.now(UTC)
    claims = {
        "sub": "u1",
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "j1",
        "iss": "test-iss",
        "aud": "test-aud",
        "username": "alice",
        "su": False,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, secret, algorithm=algorithm)


def test_access_token_carries_all_claims(tokens):
    claims = tokens.decode(tokens.issue_access("u1", "alice", False), ACCESS)
    assert claims["sub"] == "u1"
    assert claims["type"] == "access"
    assert claims["username"] == "alice"
    assert claims["iss"] == "test-iss"
    assert claims["aud"] == "test-aud"
    assert len(claims["jti"]) == 32
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == _SETTINGS.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_refresh_token_carries_family_and_returns_jti(tokens):
    token, jti = tokens.issue_refresh("u1", "fam1")
    claims = tokens.decode(token, REFRESH)
    assert claims["fam"] == "fam1"
    assert claims["jti"] == jti
    assert claims["type"] == "refresh"


@pytest.mark.parametrize("is_superuser", [True, False])
def test_access_token_carries_superuser_claim(tokens, is_superuser):
    """``su`` 는 인가 판정(Principal.is_superuser)의 근거다 (service-hardening F2, ADR-022 ②)."""
    claims = tokens.decode(tokens.issue_access("u1", "alice", is_superuser), ACCESS)
    assert claims["su"] is is_superuser


def test_each_token_has_a_unique_jti(tokens):
    a = tokens.decode(tokens.issue_access("u1", "alice", False), ACCESS)["jti"]
    b = tokens.decode(tokens.issue_access("u1", "alice", False), ACCESS)["jti"]
    assert a != b


def test_forged_valid_token_is_accepted(tokens):
    """아래 거부 테스트들의 대조군 — `_forge` 기본값은 통과해야 한다."""
    assert tokens.decode(_forge(), ACCESS)["sub"] == "u1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"nbf": datetime.now(UTC) + timedelta(minutes=1)},
        {"iss": "other-iss"},
        {"aud": "other-aud"},
        {"type": "refresh"},
        {"username": None},
        {"su": None},
        {"su": "true"},
        {"su": 1},
    ],
    ids=[
        "expired",
        "not-yet-valid",
        "wrong-issuer",
        "wrong-audience",
        "wrong-type",
        "no-username",
        "no-su",
        "su-not-bool-str",
        "su-not-bool-int",
    ],
)
def test_rejects_invalid_claims(tokens, overrides):
    with pytest.raises(InvalidTokenException):
        tokens.decode(_forge(**overrides), ACCESS)


@pytest.mark.parametrize("claim", ["exp", "iat", "nbf", "sub", "jti", "iss", "aud", "type"])
def test_rejects_missing_required_claim(tokens, claim):
    with pytest.raises(InvalidTokenException):
        tokens.decode(_forge(**{claim: None}), ACCESS)


def test_rejects_refresh_token_as_access(tokens):
    token, _ = tokens.issue_refresh("u1", "fam1")
    with pytest.raises(InvalidTokenException):
        tokens.decode(token, ACCESS)


def test_rejects_access_token_as_refresh_even_with_shared_secret():
    """키를 같게 잘못 설정해도 `type` 검사가 종류 혼동을 막는다."""
    shared = TokenService(_SETTINGS.model_copy(update={"REFRESH_TOKEN_SECRET_KEY": "a" * 64}))
    with pytest.raises(InvalidTokenException):
        shared.decode(shared.issue_access("u1", "alice", False), REFRESH)


def test_rejects_other_algorithm(tokens):
    """같은 키라도 설정에 없는 알고리즘으로 서명한 토큰은 거부한다."""
    token = _forge(algorithm="HS512")
    with pytest.raises(InvalidTokenException):
        tokens.decode(token, ACCESS)


def test_rejects_tampered_token(tokens):
    with pytest.raises(InvalidTokenException):
        tokens.decode(tokens.issue_access("u1", "alice", False) + "x", ACCESS)


def test_leeway_tolerates_small_clock_skew():
    lenient = TokenService(_SETTINGS.model_copy(update={"JWT_LEEWAY_SECONDS": 30}))
    token = _forge(nbf=datetime.now(UTC) + timedelta(seconds=10))
    assert lenient.decode(token, ACCESS)["sub"] == "u1"


def test_algorithm_setting_is_restricted_to_hmac():
    with pytest.raises(ValueError):
        JWTSettings(_env_file=None, JWT_ALGORITHM="none")
