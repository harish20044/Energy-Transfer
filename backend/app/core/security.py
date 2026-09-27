"""Password hashing and JWT issuance/verification.

Argon2id (via argon2-cffi) for hashing — the current password-hashing
competition winner, and deliberately slow so brute-forcing a stolen hash is
expensive. PyJWT with HS256 for tokens: short-lived access tokens for API
calls, longer-lived refresh tokens to get a new one without re-entering a
password.

Deviation from the reviewed stack: Keycloak was proposed and is rejected here
for the same reason recorded in ADR-0003 — a ~1GB JVM service is more than
this machine's Docker budget can spare, and native auth is fully testable in
under 200 lines. See docs/adr/0003-native-jwt-authentication.md.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage. Never store `plain` itself."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored hash.

    Returns False on mismatch rather than raising, so callers get one
    boolean to branch on regardless of *why* verification failed.
    """
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


class TokenType(StrEnum):
    """Distinguishes an access token from a refresh token in the payload.

    Without this, a stolen refresh token could be replayed directly against
    an endpoint expecting an access token — the two must never be interchangeable.
    """

    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(
    settings: Settings,
    *,
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        # A unique id per token lets a specific token be revoked (denylisted)
        # without invalidating every other token the user holds.
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(settings: Settings, *, user_id: str, role: str) -> str:
    """Issue a short-lived token for authenticating API requests."""
    return _create_token(
        settings,
        subject=user_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={"role": role},
    )


def create_refresh_token(settings: Settings, *, user_id: str) -> str:
    """Issue a long-lived token used only to mint new access tokens."""
    return _create_token(
        settings,
        subject=user_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


class TokenError(Exception):
    """A token is missing, malformed, expired, or the wrong type for its use."""


def decode_token(settings: Settings, token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, raising :class:`TokenError` on any problem.

    Callers get one exception type to handle rather than PyJWT's several, and
    the expected-type check closes the access/refresh confusion above.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        msg = "Token has expired"
        raise TokenError(msg) from exc
    except jwt.InvalidTokenError as exc:
        msg = "Token is invalid"
        raise TokenError(msg) from exc

    if payload.get("type") != expected_type.value:
        msg = f"Expected token type '{expected_type.value}'"
        raise TokenError(msg)

    return payload
