"""Talk to your agent: a tool-calling LLM loop (LangGraph) that explains the
household agent's real decisions and takes one kind of instruction.

    model -> (tools -> model)* -> answer

The model never trades and never sees anything but what its tools return:
the session, this household's forecast and its agent's recorded decisions,
its money, its family right now, and one slot's market in detail. Every
number it quotes comes from those records (ADR-0005: the LLM sits beside
the trading path, never in it). The single write it may make is the one
ADR-0005 names — preference interpretation: "keep more charge for tonight"
becomes a validated change to the household's reserve, applied from the
next planned session.

If the model is unreachable the loop falls back to the deterministic stub,
so the household always gets an answer.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import ChatProvider, ChatProviderError, Message, StubProvider
from app.agents.speech import clock
from app.core.config import Settings
from app.models.household import Household
from app.models.session import SessionHousehold
from app.models.user import User
from app.schemas.household import EveningReserveUpdate

MAX_TOOL_ROUNDS = 4

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolContext:
    db: AsyncSession
    user: User
    household: Household
    settings: Settings


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _band(p10: float, p50: float, p90: float) -> str:
    return f"{p50:.2f} ({p10:.2f}-{p90:.2f})"


def tool_specs() -> list[Message]:
    def spec(name: str, description: str, properties: dict[str, Any] | None = None) -> Message:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties or {},
                    "required": list(properties or {}),
                },
            },
        }

    return [
        spec(
            "get_session",
            "The planning session: date, start time, horizon, status, weather, EB tariffs, "
            "any power cut.",
        ),
        spec(
            "get_my_plan",
            "Hour by hour for this household: the forecast (P10-P90), what the agent decided and "
            "said, what it traded with neighbours and the EB, and what actually happened "
            "once delivered.",
        ),
        spec(
            "get_my_money",
            "This household's money for the session, planned and delivered, as separate "
            "earned and paid figures, and savings vs dealing with the EB alone.",
        ),
        spec(
            "get_my_family_now",
            "Who in the family is home, away or asleep right now, which bedroom ACs are on, "
            "and what each appliance group is drawing.",
        ),
        spec(
            "explain_hour",
            "Full detail for one hour of the session: the agent's reasons, and the market's "
            "round-by-round offers and trades.",
            {
                "hour_of_day": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 23,
                    "description": "Clock hour, 0-23",
                }
            },
        ),
        spec(
            "set_reserve",
            "Change the battery reserve: the charge level the agent never sells below. Only "
            "when the user clearly asks. Applies from the next planned session.",
            {"percent": {"type": "integer", "minimum": 10, "maximum": 90}},
        ),
    ]


def build_tools(ctx: ToolContext) -> dict[str, ToolFn]:
    # Imported here: the API modules import the agents package, so a
    # module-level import would be circular.
    from app.api.v1.household import read_own_family, read_own_session
    from app.api.v1.session import market, session_out
    from app.engine.session import get_or_create_state

    async def get_session(_: dict[str, Any]) -> Any:
        state = await get_or_create_state(ctx.db)
        out = await session_out(ctx.db, state, ctx.settings)
        return {
            "status": out.status,
            "date": out.sim_date.isoformat(),
            "starts": clock(out.start_hour),
            "horizon_hours": out.horizon_hours,
            "hours_delivered": out.hours_delivered,
            "weather": out.weather.model_dump(mode="json"),
            "scenario": out.scenario.value,
            "eb_retail_per_unit": out.retail_tariff,
            "eb_feed_in_per_unit": out.feed_in_tariff,
            "evening_peak_surcharge_pct": out.peak_surcharge_pct,
            "power_cut": out.power_cut.model_dump() if out.power_cut else None,
        }

    async def get_my_plan(_: dict[str, Any]) -> Any:
        own = await read_own_session(ctx.user, ctx.db, ctx.settings)
        hours = []
        for s in own.slots:
            f = s.forecast
            entry: dict[str, Any] = {
                "hour": clock(s.hour_of_day),
                "forecast_load_kw": _band(f.consumption_p10, f.consumption_p50, f.consumption_p90),
                "forecast_solar_kw": _band(f.generation_p10, f.generation_p50, f.generation_p90),
                "plan": s.decision.message if s.decision else "",
                "outcome": s.decision.outcome if s.decision else "",
                "sold_to_neighbours": _r(s.p2p_sold_kwh),
                "bought_from_neighbours": _r(s.p2p_bought_kwh),
                "from_eb": _r(s.eb_bought_kwh),
                "to_eb": _r(s.eb_sold_kwh),
            }
            if s.delivered:
                entry["actual"] = {
                    "load_kwh": _r(s.actual_consumption_kwh),
                    "solar_kwh": _r(s.actual_generation_kwh),
                    "eb_import_kwh": _r(s.actual_eb_import_kwh),
                    "eb_export_kwh": _r(s.actual_eb_export_kwh),
                    "battery_end_pct": _r((s.battery_soc_end or 0) * 100, 0),
                }
            hours.append(entry)
        setup = await ctx.db.get(SessionHousehold, ctx.household.id)
        battery = (
            {
                "capacity_units": setup.battery_capacity_kwh,
                "start_percent": round(setup.start_soc * 100),
                "reserve_percent": round(ctx.household.evening_reserve * 100),
            }
            if setup and setup.battery_capacity_kwh > 0
            else "this household has no battery this session"
        )
        return {
            "household": ctx.household.display_name,
            "forecast_model": own.model,
            "battery": battery,
            "panels": (
                f"{ctx.household.solar_capacity_kwp:g} kWp"
                + (
                    f", {round(setup.panel_derate * 100)}% lost to dust/shade"
                    if setup and setup.panel_derate
                    else ""
                )
            ),
            "hours": hours,
        }

    async def get_my_money(_: dict[str, Any]) -> Any:
        own = await read_own_session(ctx.user, ctx.db, ctx.settings)
        return {
            "planned": own.planned.model_dump() if own.planned else None,
            "delivered": own.delivered.model_dump() if own.delivered else None,
            "note": "Rupees and units; earned and paid are separate positive amounts.",
        }

    async def get_my_family_now(_: dict[str, Any]) -> Any:
        family = await read_own_family(ctx.user, ctx.db, ctx.settings)
        return {
            "members": [
                {"age": m.age, "role": m.role, "occupation": m.occupation, "status": m.status}
                for m in family.members
            ],
            "bedroom_acs_on": [r.room for r in family.rooms if r.ac_on],
            "appliance_kw": {k: round(v, 3) for k, v in family.appliance_kw.items()},
        }

    async def explain_hour(args: dict[str, Any]) -> Any:
        hour = int(args.get("hour_of_day", -1))
        state = await get_or_create_state(ctx.db)
        slot = (hour - state.start_hour) % 24
        if slot >= state.horizon_hours:
            return {"error": f"{clock(hour)} is outside this session"}
        detail = await market(ctx.user, ctx.db, slot=slot)
        mine = next((a for a in detail.agents if a.household_id == ctx.household.id), None)
        return {
            "hour": clock(hour),
            "eb_available": detail.eb_available,
            "eb_retail": detail.retail_tariff,
            "my_decision": mine.model_dump() if mine else None,
            "rounds": [
                {
                    "round": r.round_index + 1,
                    "asks": [(a.household_id, round(a.price, 2), round(a.kwh, 2)) for a in r.asks],
                    "bids": [(b.household_id, round(b.price, 2), round(b.kwh, 2)) for b in r.bids],
                    "trades": [
                        (
                            t.seller_household_id,
                            t.buyer_household_id,
                            round(t.kwh, 2),
                            round(t.price_per_kwh, 2),
                        )
                        for t in r.trades
                    ],
                }
                for r in detail.rounds
            ],
        }

    async def set_reserve(args: dict[str, Any]) -> Any:
        try:
            update = EveningReserveUpdate(evening_reserve=float(args.get("percent", 0)) / 100.0)
        except (ValidationError, TypeError, ValueError) as exc:
            return {"error": f"not a valid reserve: {exc}"}
        ctx.household.evening_reserve = update.evening_reserve
        await ctx.db.commit()
        return {
            "reserve_percent": round(update.evening_reserve * 100),
            "applies": "from the next planned session",
        }

    return {
        "get_session": get_session,
        "get_my_plan": get_my_plan,
        "get_my_money": get_my_money,
        "get_my_family_now": get_my_family_now,
        "explain_hour": explain_hour,
        "set_reserve": set_reserve,
    }


def system_prompt(household: Household) -> str:
    return (
        f"You are the autonomous energy-trading agent for {household.display_name}, one of ten "
        "homes on a rooftop-solar microgrid in Chennai. Before each session you forecast your "
        "household's next hours and trade every hour with the neighbours and with the EB (the "
        "utility, TNPDCL) on its behalf. Those decisions are already made and recorded; now the "
        "household is talking to you. Speak in the first person, warmly and plainly, like a "
        "helpful family member who handles the electricity. Always use your tools for facts and "
        "never invent a number, a trade or a reason. Energy is in 'units' (1 unit = 1 kWh) as on "
        "an EB bill; money in rupees. Never describe money as a negative balance — say what was "
        "paid and what was earned. Keep answers under 120 words unless asked for detail. Only "
        "call set_reserve when the user clearly asks you to keep more or less charge."
    )


class _AdvisorState(TypedDict):
    messages: list[Message]
    rounds: int
    tools_used: list[str]


async def converse(
    ctx: ToolContext,
    provider: ChatProvider,
    history: list[Message],
    user_message: str,
) -> tuple[str, list[str], str]:
    """The agent's reply, the tools it used, and which provider answered."""
    tools = build_tools(ctx)
    specs = tool_specs()
    active: dict[str, ChatProvider] = {"provider": provider}
    fell_back = False

    async def model_node(state: _AdvisorState) -> dict[str, Any]:
        nonlocal fell_back
        try:
            message = await active["provider"].complete(state["messages"], specs)
        except ChatProviderError:
            fell_back = True
            active["provider"] = StubProvider()
            message = await active["provider"].complete(state["messages"], specs)
        message = {k: v for k, v in message.items() if k in ("role", "content", "tool_calls")}
        message["role"] = "assistant"
        return {"messages": [*state["messages"], message], "rounds": state["rounds"] + 1}

    async def tools_node(state: _AdvisorState) -> dict[str, Any]:
        last = state["messages"][-1]
        results: list[Message] = []
        used = list(state["tools_used"])
        for call in last.get("tool_calls") or []:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            fn = tools.get(name)
            output = await fn(args) if fn else {"error": f"unknown tool {name}"}
            used.append(name)
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "content": json.dumps(output, default=str),
                }
            )
        return {"messages": [*state["messages"], *results], "tools_used": used}

    def route(state: _AdvisorState) -> str:
        last = state["messages"][-1]
        if last.get("tool_calls") and state["rounds"] <= MAX_TOOL_ROUNDS:
            return "tools"
        return END

    builder = StateGraph(_AdvisorState)
    builder.add_node("model", model_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route, {"tools": "tools", END: END})
    builder.add_edge("tools", "model")
    graph = builder.compile()

    messages: list[Message] = [
        {"role": "system", "content": system_prompt(ctx.household)},
        *history,
        {"role": "user", "content": user_message},
    ]
    result = await graph.ainvoke({"messages": messages, "rounds": 0, "tools_used": []})
    reply = str(result["messages"][-1].get("content") or "").strip()
    if not reply:
        reply = "I checked my records but couldn't put an answer together — could you ask again?"
    if fell_back:
        reply = (
            "(My language model isn't reachable right now, so here's the plain version.) " + reply
        )
    return reply, list(result["tools_used"]), active["provider"].name
