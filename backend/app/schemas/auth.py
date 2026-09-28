"""Wire contracts for registration, login, and the authenticated user."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    """New-account submission."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    """Sign-in submission."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """Exchange a refresh token for a new access token."""

    refresh_token: str


class TokenPair(BaseModel):
    """What the client stores after a successful login or refresh."""

    access_token: str
    refresh_token: str
    # "bearer" is the OAuth2 spec's token-type constant, not a secret —
    # bandit's S105 pattern-matches the field name containing "token".
    token_type: str = "bearer"  # noqa: S105


class UserPublic(BaseModel):
    """The authenticated user's own profile — never includes the password hash."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    household_id: str | None
