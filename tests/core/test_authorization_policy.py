"""core 인가 부품 단위 시험 — `OwnershipPolicy`·`get_current_principal`·`require_superuser` (ADR-014~016)."""

from types import SimpleNamespace

import pytest

from app.core.exception import ForbiddenException, InvalidTokenException
from app.core.security.authorization import OwnershipPolicy, Principal
from app.core.security.dependencies import get_current_principal, require_superuser
from app.core.security.tokens import TokenService
from config import jwt_settings

ALICE = Principal(id="u-alice", username="alice", is_superuser=False)
ADMIN = Principal(id="u-admin", username="admin", is_superuser=True)


def test_owner_can_modify():
    OwnershipPolicy().ensure_can_modify("u-alice", ALICE)


@pytest.mark.parametrize("owner_id", ["u-bob", None], ids=["other-owner", "no-owner"])
def test_non_owner_is_forbidden(owner_id):
    with pytest.raises(ForbiddenException) as exc:
        OwnershipPolicy().ensure_can_modify(owner_id, ALICE)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("owner_id", ["u-bob", None], ids=["other-owner", "no-owner"])
def test_superuser_bypasses_ownership(owner_id):
    OwnershipPolicy().ensure_can_modify(owner_id, ADMIN)


def _request():
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.parametrize("is_superuser", [True, False])
async def test_principal_comes_from_access_claims_and_marks_request(is_superuser):
    tokens = TokenService(jwt_settings)
    request = _request()

    principal = await get_current_principal(
        request, tokens.issue_access("u1", "alice", is_superuser), tokens
    )

    assert principal == Principal(id="u1", username="alice", is_superuser=is_superuser)
    assert request.state.user_id == "u1"


async def test_invalid_token_leaves_request_unmarked():
    request = _request()
    with pytest.raises(InvalidTokenException):
        await get_current_principal(request, "garbage", TokenService(jwt_settings))
    assert not hasattr(request.state, "user_id")


async def test_require_superuser():
    assert await require_superuser(ADMIN) is ADMIN
    with pytest.raises(ForbiddenException):
        await require_superuser(ALICE)
