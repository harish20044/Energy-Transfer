"""Password hashing and JWT issuance/verification."""

from __future__ import annotations

import time

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_hash_password_never_stores_the_plaintext() -> None:
    hashed = hash_password("correcthorsebattery")
    assert hashed != "correcthorsebattery"
    assert hashed.startswith("$argon2")


def test_verify_password_accepts_the_correct_password() -> None:
    hashed = hash_password("correcthorsebattery")
    assert verify_password("correcthorsebattery", hashed) is True


def test_verify_password_rejects_the_wrong_password() -> None:
    hashed = hash_password("correcthorsebattery")
    assert verify_password("wrongpassword", hashed) is False


def test_hashing_the_same_password_twice_gives_different_hashes() -> None:
    """Argon2 salts every hash, so two users with the same password never
    share a stored value — a leaked hash can't be matched across accounts."""
    assert hash_password("correcthorsebattery") != hash_password("correcthorsebattery")


def test_access_token_round_trips(settings: Settings) -> None:
    token = create_access_token(settings, user_id="user-123", role="household")
    payload = decode_token(settings, token, expected_type=TokenType.ACCESS)

    assert payload["sub"] == "user-123"
    assert payload["role"] == "household"
    assert payload["type"] == "access"


def test_refresh_token_round_trips(settings: Settings) -> None:
    token = create_refresh_token(settings, user_id="user-123")
    payload = decode_token(settings, token, expected_type=TokenType.REFRESH)

    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_two_tokens_for_the_same_user_have_different_ids(settings: Settings) -> None:
    """Distinct `jti` claims let one token be revoked without killing every
    session the user holds."""
    first = decode_token(
        settings,
        create_access_token(settings, user_id="user-123", role="household"),
        expected_type=TokenType.ACCESS,
    )
    second = decode_token(
        settings,
        create_access_token(settings, user_id="user-123", role="household"),
        expected_type=TokenType.ACCESS,
    )
    assert first["jti"] != second["jti"]


def test_an_access_token_is_rejected_where_a_refresh_token_is_required(
    settings: Settings,
) -> None:
    """Closes the access/refresh confusion: a stolen access token must not be
    replayable against the refresh endpoint."""
    access = create_access_token(settings, user_id="user-123", role="household")
    with pytest.raises(TokenError, match="Expected token type 'refresh'"):
        decode_token(settings, access, expected_type=TokenType.REFRESH)


def test_a_refresh_token_is_rejected_where_an_access_token_is_required(
    settings: Settings,
) -> None:
    refresh = create_refresh_token(settings, user_id="user-123")
    with pytest.raises(TokenError, match="Expected token type 'access'"):
        decode_token(settings, refresh, expected_type=TokenType.ACCESS)


def test_an_expired_token_is_rejected(settings: Settings) -> None:
    # Encoded directly (bypassing create_access_token) to force an already-past
    # expiry, rather than waiting out a real token's lifetime in the test.
    expired = jwt.encode(
        {"sub": "user-123", "type": "access", "exp": int(time.time()) - 60},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError, match="expired"):
        decode_token(settings, expired, expected_type=TokenType.ACCESS)


def test_a_token_signed_with_a_different_secret_is_rejected(settings: Settings) -> None:
    """Proves the signature is actually checked, not merely decoded."""
    forged = jwt.encode(
        {"sub": "user-123", "type": "access", "exp": int(time.time()) + 3600},
        "a-completely-different-secret",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError, match="invalid"):
        decode_token(settings, forged, expected_type=TokenType.ACCESS)


def test_a_malformed_token_is_rejected(settings: Settings) -> None:
    with pytest.raises(TokenError, match="invalid"):
        decode_token(settings, "not.a.token", expected_type=TokenType.ACCESS)
