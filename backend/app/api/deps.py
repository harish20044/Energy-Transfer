"""Shared FastAPI dependencies: the current user, and role enforcement.

A token proves *who is asking*; these dependencies decide *what they may do*.
Keeping that check here, in one place, is what `require_role` buys — a route
that forgets to call it is a bug you can grep for, not a silent gap per route.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import TokenError, TokenType, decode_token
from app.models.user import User, UserRole

# tokenUrl points at the login route so /docs can drive the "Authorize" flow;
# this scheme never checks a fixed username/password itself — decode_token does.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
TokenDep = Annotated[str | None, Depends(_oauth2_scheme)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(token: TokenDep, settings: SettingsDep, db: DbDep) -> User:
    """Resolve the bearer token to a live, active user row.

    Re-fetches the user on every request rather than trusting claims baked
    into the token, so a deactivated account is locked out immediately
    instead of only once its access token happens to expire.
    """
    if token is None:
        raise _CREDENTIALS_ERROR

    try:
        payload = decode_token(settings, token, expected_type=TokenType.ACCESS)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _CREDENTIALS_ERROR from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_role(*allowed: UserRole) -> Callable[[CurrentUserDep], User]:
    """Build a dependency that additionally requires one of `allowed` roles.

    Usage: `user: Annotated[User, Depends(require_role(UserRole.OPERATOR))]`.
    """

    def _check(user: CurrentUserDep) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(r.value for r in allowed)}",
            )
        return user

    return _check
