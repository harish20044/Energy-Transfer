"""A planning session end to end against the real database: set it up,
let the agents trade, deliver the hours, read the money — and talk to the
agent (on the deterministic stub model, so tests never call an LLM)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update

from app.agents.llm import StubProvider
from app.core.db import get_sessionmaker
from app.models.agent import AgentDecisionRecord, AgentMemoryRecord
from app.models.household import Household
from app.models.session import SessionForecast, SessionHousehold, SessionPosition
from app.models.simulation import (
    LedgerEntryRecord,
    MeterReading,
    NegotiationOfferRecord,
    TradeRecord,
)
from app.models.user import User

pytestmark = pytest.mark.integration

Account = dict[str, str]
PLAN = {"sim_date": "2026-05-15", "start_hour": 14, "horizon_hours": 4, "scenario": "auto"}


@pytest.fixture
async def account(api_client: AsyncClient) -> AsyncIterator[Callable[..., Awaitable[Account]]]:
    """Registered users each linked to a fresh household; everything the
    session wrote about them is removed afterwards."""
    created: list[tuple[str, str]] = []

    async def _make(member_count: int = 4) -> Account:
        household_id = f"test-{uuid.uuid4().hex[:8]}"
        email = f"{household_id}@example.com"
        await api_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correcthorsebattery", "display_name": household_id},
        )
        async with get_sessionmaker()() as session:
            session.add(
                Household(id=household_id, display_name=household_id, member_count=member_count)
            )
            await session.execute(
                update(User).where(User.email == email).values(household_id=household_id)
            )
            await session.commit()
        created.append((email, household_id))
        login = await api_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "correcthorsebattery"}
        )
        return {"household_id": household_id, "token": login.json()["access_token"]}

    yield _make

    async with get_sessionmaker()() as session:
        for model in (
            MeterReading,
            AgentDecisionRecord,
            NegotiationOfferRecord,
            LedgerEntryRecord,
            TradeRecord,
            SessionPosition,
            SessionForecast,
            SessionHousehold,
        ):
            await session.execute(delete(model))
        for email, household_id in created:
            await session.execute(
                delete(AgentMemoryRecord).where(AgentMemoryRecord.household_id == household_id)
            )
            await session.execute(delete(User).where(User.email == email))
            await session.execute(delete(Household).where(Household.id == household_id))
        await session.commit()


def _auth(acct: Account) -> dict[str, str]:
    return {"Authorization": f"Bearer {acct['token']}"}


async def test_a_session_plans_trades_delivers_and_settles(
    api_client: AsyncClient, account: Callable[..., Awaitable[Account]]
) -> None:
    buyer = await account(member_count=6)
    await account(member_count=2)
    body = {
        **PLAN,
        "households": [
            {"household_id": buyer["household_id"], "panel_derate": 1.0, "battery_capacity_kwh": 0}
        ],
    }

    planned = await api_client.post("/api/v1/session/plan", json=body, headers=_auth(buyer))
    assert planned.status_code == 200, planned.text
    state = planned.json()
    assert state["status"] == "planned"
    assert state["horizon_hours"] == 4
    assert state["feed_in_tariff"] < state["retail_tariff"]

    overview = (await api_client.get("/api/v1/session/overview", headers=_auth(buyer))).json()
    assert [row["hour_of_day"] for row in overview] == [14, 15, 16, 17]

    market = (await api_client.get("/api/v1/session/market?slot=0", headers=_auth(buyer))).json()
    assert any(agent["household_id"] == buyer["household_id"] for agent in market["agents"])
    for round_ in market["rounds"]:
        for trade in round_["trades"]:
            assert market["feed_in_tariff"] <= trade["price_per_kwh"] <= market["retail_tariff"]

    own = (await api_client.get("/api/v1/households/me/session", headers=_auth(buyer))).json()
    assert len(own["slots"]) == 4
    assert own["planned"] is not None and own["delivered"] is None
    # A household with no panels is a buyer all afternoon.
    first = own["slots"][0]
    assert first["forecast"]["generation_p50"] == pytest.approx(0.0, abs=1e-6)
    assert first["p2p_bought_kwh"] + first["eb_bought_kwh"] > 0

    stepped = await api_client.post("/api/v1/session/next-hour", headers=_auth(buyer))
    assert stepped.json()["status"] == "playing"
    assert stepped.json()["hours_delivered"] == 1

    own = (await api_client.get("/api/v1/households/me/session", headers=_auth(buyer))).json()
    delivered = own["delivered"]
    assert delivered["hours"] == 1
    for key in (
        "earned_from_neighbours_inr",
        "paid_to_neighbours_inr",
        "paid_to_eb_inr",
        "earned_from_eb_inr",
        "eb_only_paid_inr",
        "eb_only_earned_inr",
    ):
        assert delivered[key] >= 0, key  # money is never a negative "balance"
    assert own["slots"][0]["delivered"] is True


async def test_a_session_stops_at_its_horizon(
    api_client: AsyncClient, account: Callable[..., Awaitable[Account]]
) -> None:
    acct = await account()
    await api_client.post("/api/v1/session/plan", json=PLAN, headers=_auth(acct))
    for _ in range(4):
        response = await api_client.post("/api/v1/session/next-hour", headers=_auth(acct))
    assert response.json()["status"] == "complete"
    extra = await api_client.post("/api/v1/session/next-hour", headers=_auth(acct))
    assert extra.status_code == 409

    reset = await api_client.post("/api/v1/session/reset", headers=_auth(acct))
    assert reset.json()["status"] == "setup"
    assert (
        await api_client.post("/api/v1/session/next-hour", headers=_auth(acct))
    ).status_code == 409


async def test_a_power_cut_takes_the_eb_out_of_those_slots(
    api_client: AsyncClient, account: Callable[..., Awaitable[Account]]
) -> None:
    acct = await account()
    body = {**PLAN, "power_cut": {"start_hour": 15, "end_hour": 17}}
    await api_client.post("/api/v1/session/plan", json=body, headers=_auth(acct))
    overview = (await api_client.get("/api/v1/session/overview", headers=_auth(acct))).json()
    assert [row["eb_available"] for row in overview] == [True, False, False, True]
    for row in overview:
        if not row["eb_available"]:
            assert row["eb_bought_kwh"] == 0 and row["eb_sold_kwh"] == 0


async def test_invalid_setups_are_rejected(
    api_client: AsyncClient, account: Callable[..., Awaitable[Account]]
) -> None:
    acct = await account()
    inverted = {**PLAN, "tariffs": {"retail_tariff": 3.0, "feed_in_tariff": 5.0}}
    assert (
        await api_client.post("/api/v1/session/plan", json=inverted, headers=_auth(acct))
    ).status_code == 422
    bad_horizon = {**PLAN, "horizon_hours": 7}
    assert (
        await api_client.post("/api/v1/session/plan", json=bad_horizon, headers=_auth(acct))
    ).status_code == 422
    half_window = {**PLAN, "households": [{"household_id": acct["household_id"], "away_from": 18}]}
    assert (
        await api_client.post("/api/v1/session/plan", json=half_window, headers=_auth(acct))
    ).status_code == 422


async def test_the_family_endpoint_shows_who_is_home_and_what_is_running(
    api_client: AsyncClient, account: Callable[..., Awaitable[Account]]
) -> None:
    acct = await account(member_count=5)
    await api_client.post("/api/v1/session/plan", json=PLAN, headers=_auth(acct))
    family = (await api_client.get("/api/v1/households/me/family", headers=_auth(acct))).json()
    assert len(family["members"]) == 5
    assert {m["status"] for m in family["members"]} <= {"home", "away", "asleep"}
    assert "cooling" in family["appliance_kw"]
    assert "ev" in family["appliance_kw"]


async def test_talking_to_the_agent_is_grounded_in_its_records(
    api_client: AsyncClient,
    account: Callable[..., Awaitable[Account]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.api.v1.agents.get_provider", lambda _settings: StubProvider())
    acct = await account()
    await api_client.post("/api/v1/session/plan", json=PLAN, headers=_auth(acct))

    response = await api_client.post(
        "/api/v1/agents/me/chat", json={"message": "What's your plan?"}, headers=_auth(acct)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "stub"
    assert "get_my_plan" in body["tools_used"]
    assert "2 pm" in body["reply"]

    memory = (await api_client.get("/api/v1/agents/me", headers=_auth(acct))).json()
    assert memory["graph_nodes"] == ["perceive", "project", "value", "order", "speak"]
    assert len(memory["price_by_hour"]) == 24
