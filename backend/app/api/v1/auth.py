"""Registration, login, token refresh, and the current-user profile."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbDep) -> User:
    """Create a new account. Every new user starts as a household owner —
    the `household` role — never `operator` or `admin`; those are granted
    out of band, not self-selected at signup."""
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    return user


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: DbDep, settings: SettingsDep) -> TokenPair:
    """Exchange email + password for a token pair.

    The same generic error for "no such user" and "wrong password" is
    deliberate: distinguishing them lets an attacker enumerate which emails
    have accounts.
    """
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    return TokenPair(
        access_token=create_access_token(settings, user_id=str(user.id), role=user.role.value),
        refresh_token=create_refresh_token(settings, user_id=str(user.id)),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbDep, settings: SettingsDep) -> TokenPair:
    """Exchange a refresh token for a new token pair, without a password."""
    try:
        payload = decode_token(settings, body.refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user = await db.scalar(select(User).where(User.id == uuid.UUID(payload["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return TokenPair(
        access_token=create_access_token(settings, user_id=str(user.id), role=user.role.value),
        refresh_token=create_refresh_token(settings, user_id=str(user.id)),
    )


@router.get("/me", response_model=UserPublic)
async def read_current_user(current_user: CurrentUserDep) -> User:
    """The signed-in user's own profile — proves the token actually works."""
    return current_user
