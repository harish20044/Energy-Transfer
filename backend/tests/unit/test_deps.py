"""`require_role`: the dependency that turns a valid token into an authorization
decision. Tested directly against a plain `User` instance — no HTTP layer, no
database — since the function itself takes only a user and returns a user."""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.api.deps import require_role
from app.models.user import User, UserRole

pytestmark = pytest.mark.unit


def _user(role: UserRole) -> User:
    return User(
        id=uuid.uuid4(),
        email="test@example.com",
        hashed_password="irrelevant",
        display_name="Test User",
        role=role,
    )


def test_require_role_allows_a_matching_role() -> None:
    check = require_role(UserRole.OPERATOR)
    operator = _user(UserRole.OPERATOR)

    assert check(operator) is operator


def test_require_role_allows_any_of_several_roles() -> None:
    check = require_role(UserRole.OPERATOR, UserRole.ADMIN)

    assert check(_user(UserRole.ADMIN)) is not None


def test_require_role_rejects_a_non_matching_role() -> None:
    check = require_role(UserRole.OPERATOR)
    household_user = _user(UserRole.HOUSEHOLD)

    with pytest.raises(HTTPException) as exc_info:
        check(household_user)

    assert exc_info.value.status_code == 403
    assert "operator" in exc_info.value.detail
