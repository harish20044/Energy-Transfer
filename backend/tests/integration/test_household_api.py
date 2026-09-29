"""The household-scoped API.

Every route here derives its household from the caller's own JWT, never from
a path or query parameter — the property under test is that cross-household
access is structurally impossible to even *request*, not merely checked and
refused server-side.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.core.db import get_sessionmaker
from app.models.household import Household
from app.models.user import User

pytestmark = pytest.mark.integration

HouseholdAccount = dict[str, str]


async def _link_household(email: str, household_id: str, *, member_count: int) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        session.add(
            Household(id=household_id, display_name=household_id, member_count=member_count)
        )
        await session.execute(
            update(User).where(User.email == email).values(household_id=household_id)
        )
        await session.commit()


async def _login(api_client: AsyncClient, email: str, password: str) -> str:
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return str(response.json()["access_token"])


@pytest.fixture
async def make_household_account(
    api_client: AsyncClient,
) -> AsyncIterator[Callable[..., Awaitable[HouseholdAccount]]]:
    """A factory for registered users, each linked to its own fresh
    household, all cleaned up together once the test ends."""
    created: list[tuple[str, str]] = []

    async def _make(member_count: int = 4) -> HouseholdAccount:
        household_id = f"test-{uuid.uuid4().hex[:8]}"
        email = f"{household_id}@example.com"
        password = "correcthorsebattery"
        await api_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "display_name": household_id},
        )
        await _link_household(email, household_id, member_count=member_count)
        created.append((email, household_id))
        return {"email": email, "password": password, "household_id": household_id}

    yield _make

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        for email, household_id in created:
            await session.execute(delete(User).where(User.email == email))
            await session.execute(delete(Household).where(Household.id == household_id))
        await session.commit()


async def test_households_me_returns_the_callers_own_household(
    api_client: AsyncClient, make_household_account: Callable[..., Awaitable[HouseholdAccount]]
) -> None:
    account = await make_household_account(member_count=6)
    token = await _login(api_client, account["email"], account["password"])

    response = await api_client.get(
        "/api/v1/households/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == account["household_id"]
    assert body["member_count"] == 6


async def test_two_households_never_see_each_others_data(
    api_client: AsyncClient, make_household_account: Callable[..., Awaitable[HouseholdAccount]]
) -> None:
    """The core isolation guarantee: each login's token resolves only to its
    own household, no matter what else exists in the same database."""
    house_a = await make_household_account(member_count=2)
    house_b = await make_household_account(member_count=8)

    token_a = await _login(api_client, house_a["email"], house_a["password"])
    token_b = await _login(api_client, house_b["email"], house_b["password"])

    response_a = await api_client.get(
        "/api/v1/households/me", headers={"Authorization": f"Bearer {token_a}"}
    )
    response_b = await api_client.get(
        "/api/v1/households/me", headers={"Authorization": f"Bearer {token_b}"}
    )

    assert response_a.json()["id"] == house_a["household_id"]
    assert response_b.json()["id"] == house_b["household_id"]
    assert response_a.json()["id"] != response_b.json()["id"]


async def test_households_me_rejects_an_account_with_no_household(
    api_client: AsyncClient,
) -> None:
    email = f"no-household-{uuid.uuid4().hex[:8]}@example.com"
    password = "correcthorsebattery"
    await api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "No Household"},
    )
    token = await _login(api_client, email, password)

    response = await api_client.get(
        "/api/v1/households/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404

    session_factory = get_sessionmaker()
    async with session_factory() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()


async def test_households_me_rejects_a_missing_token(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/households/me")
    assert response.status_code == 401


async def test_evening_reserve_update_only_changes_the_callers_own_household(
    api_client: AsyncClient, make_household_account: Callable[..., Awaitable[HouseholdAccount]]
) -> None:
    house_a = await make_household_account()
    house_b = await make_household_account()
    token_a = await _login(api_client, house_a["email"], house_a["password"])
    token_b = await _login(api_client, house_b["email"], house_b["password"])

    update_response = await api_client.patch(
        "/api/v1/households/me/evening-reserve",
        json={"evening_reserve": 0.7},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["evening_reserve"] == pytest.approx(0.7)

    unaffected = await api_client.get(
        "/api/v1/households/me", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert unaffected.json()["evening_reserve"] == pytest.approx(0.4)


async def test_evening_reserve_update_rejects_an_out_of_range_value(
    api_client: AsyncClient, make_household_account: Callable[..., Awaitable[HouseholdAccount]]
) -> None:
    account = await make_household_account()
    token = await _login(api_client, account["email"], account["password"])

    response = await api_client.patch(
        "/api/v1/households/me/evening-reserve",
        json={"evening_reserve": 1.5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
