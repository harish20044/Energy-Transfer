"""Registration, login, refresh and the current-user route, against a real
database and a real HTTP client — the thing a curl command would actually see."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.models.user import User

pytestmark = pytest.mark.integration


async def _deactivate(email: str) -> None:
    """Flip a user's `is_active` flag directly in the database.

    There is no deactivation endpoint yet, so this reaches past the API the
    same way an admin action or a support script eventually will.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(update(User).where(User.email == email).values(is_active=False))
        await session.commit()


@pytest.fixture
async def registered_user() -> AsyncIterator[dict[str, str]]:
    """A unique, real account, deleted again once the test finishes.

    The email is randomised per test run so repeated runs never collide on
    the unique index — the same thing that would happen to two real signups.
    """
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    credentials = {"email": email, "password": "correcthorsebattery", "display_name": "Test User"}

    yield credentials

    # The API route commits its own session (see app.core.db.get_db), so
    # cleanup needs its own committing session too — the rolled-back
    # `db_session` fixture elsewhere in this package would not remove it.
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()


async def test_register_creates_an_account(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    response = await api_client.post("/api/v1/auth/register", json=registered_user)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == registered_user["email"]
    assert body["display_name"] == registered_user["display_name"]
    assert body["role"] == "household"
    assert "hashed_password" not in body
    assert "password" not in body


async def test_register_rejects_a_duplicate_email(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    first = await api_client.post("/api/v1/auth/register", json=registered_user)
    assert first.status_code == 201

    second = await api_client.post("/api/v1/auth/register", json=registered_user)

    assert second.status_code == 409


async def test_login_returns_a_working_token_pair(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 0
    assert len(body["refresh_token"]) > 0
    assert body["access_token"] != body["refresh_token"]


async def test_login_rejects_the_wrong_password(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": "wrongpassword"},
    )

    assert response.status_code == 401


async def test_login_rejects_an_email_that_was_never_registered(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-here@example.com", "password": "whatever12345"},
    )

    assert response.status_code == 401


async def test_me_returns_the_authenticated_profile(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    access_token = login.json()["access_token"]

    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


async def test_me_rejects_a_missing_token(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_a_garbage_token(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_refresh_issues_a_new_working_access_token(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    refresh_token = login.json()["refresh_token"]

    response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    new_access_token = response.json()["access_token"]

    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access_token}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == registered_user["email"]


async def test_refresh_rejects_an_access_token_used_in_place_of_a_refresh_token(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    """A stolen access token must not double as a refresh token."""
    await api_client.post("/api/v1/auth/register", json=registered_user)
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    access_token = login.json()["access_token"]

    response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401


async def test_login_rejects_a_deactivated_account(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)
    await _deactivate(registered_user["email"])

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )

    assert response.status_code == 403


async def test_refresh_rejects_a_token_for_a_deactivated_account(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    await api_client.post("/api/v1/auth/register", json=registered_user)
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    refresh_token = login.json()["refresh_token"]

    await _deactivate(registered_user["email"])

    response = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401


async def test_me_rejects_a_token_for_a_deactivated_account(
    api_client: AsyncClient, registered_user: dict[str, str]
) -> None:
    """A token issued before deactivation must stop working immediately, not
    merely once it happens to expire — the whole point of re-checking the
    database on every request instead of trusting the token's own claims."""
    await api_client.post("/api/v1/auth/register", json=registered_user)
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    access_token = login.json()["access_token"]

    await _deactivate(registered_user["email"])

    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401


async def test_me_rejects_a_token_whose_subject_is_not_a_valid_user_id(
    api_client: AsyncClient,
) -> None:
    """A syntactically valid, correctly signed token can still carry a `sub`
    that was never a UUID in the first place — defence in depth beyond
    trusting that only `create_access_token` ever produces one."""
    settings = get_settings()
    forged = jwt.encode(
        {"sub": "not-a-uuid", "type": "access", "exp": 9999999999},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401
