"""The households' trading agents: a LangGraph decision graph run for every
hourly slot of a planning session, in time order, after the forecasts are in.

    perceive -> project -> value -> order -> speak

One run per slot takes every household's agent through these steps together
(`decide_slots`): each step is applied to each agent on its own, and an
agent only ever sees its own observation — its forecast, battery, contracts
and learned prices — so every household still decides for itself. Running
them as one graph rather than one graph per household pays LangGraph's
per-run overhead once per slot instead of once per household, which is what
keeps a slot's clearing fast as the feeder grows (objective O3).

- **perceive**: the slot, its tariffs and whether the EB is up, and every
  neighbour contract the agent has already made for earlier slots.
- **project**: walk the battery through the rest of the session on the
  median forecast, net of those contracts — what will spill, what will be
  short, and how much stored charge is genuinely spare. Before an EB power
  cut the agent holds back enough charge to ride through it.
- **value**: how much to commit under uncertainty. This is a newsvendor
  problem (as in Bitar et al., 2012, "Bringing wind energy to market"):
  promising a neighbour energy you don't have means buying the gap from
  the EB at retail; holding back means exporting the rest at the feed-in
  rate. The cost-minimising commitment is a quantile of the forecast set by
  those two costs and the price the agent expects (its own learned
  estimate, corrected by how this session's market is actually clearing —
  `app.agents.memory`) — sellers commit around their P35, buyers around
  their P65 at typical prices, far more cautiously during a power cut, when
  a broken promise means lights out. Never past the forecast's P10 to P90:
  that band is what the forecaster is calibrated for (conformal, ~80%
  coverage); beyond it a Gaussian tail is a guess, and a wrong price belief
  would otherwise buy or promise several times what the house needs.
- **order**: firm orders for a real surplus or shortfall (the EB takes what
  neighbours don't of the *expected* quantity; the newsvendor's hedge on
  top is for neighbours only), optional ones for opportunities — selling spare stored
  charge, or buying cheap neighbour energy to store for a shortfall later
  (never from the EB at retail — that would be a loss) — and firm buying
  ahead of a power cut. Opening prices come from the agent's learned margin.
- **speak**: what it's doing and why (`app.agents.speech`).

Deterministic and auditable — no LLM anywhere in this graph (ADR-0005). The
market clamps every price into the tariff band.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from functools import lru_cache
from itertools import pairwise
from statistics import NormalDist
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.speech import reasons_for, slot_message
from app.agents.types import SlotDecision, SlotObservation, Strategy
from app.domain.battery.schedule import SlotPlan, project, spare_storage_kwh, storable_kwh
from app.domain.market.orderbook import Side
from app.domain.market.slot_market import SlotOrder
from app.domain.settlement.delivery import PROTECTION_FLOOR_SOC

GRAPH_NODES: tuple[str, ...] = ("perceive", "project", "value", "order", "speak")

_MIN_ORDER_KWH = 0.05
# Cost of cycling a unit through the battery (wear), ₹/kWh.
_DEGRADATION_INR = 0.5
# Stored charge sells for no less than this fraction of the learned price.
_STORED_FLOOR_FRACTION = 0.85
# During an EB power cut a broken promise means lights out, not a retail bill.
_OUTAGE_SELL_QUANTILE = 0.1
_OUTAGE_BUY_QUANTILE = 0.9
# The forecast's calibrated band: commitments stay between its P10 and P90.
_MIN_COMMIT_QUANTILE, _MAX_COMMIT_QUANTILE = 0.1, 0.9
# P10 and P90 are 2 x 1.2816 standard deviations apart.
_P10_P90_SIGMAS = 2 * 1.2816


class _State(TypedDict, total=False):
    obs: SlotObservation
    plans: tuple[SlotPlan, ...]
    outage_hold_kwh: float
    sigma_kwh: float
    expected_price: float
    sell_quantile: float
    buy_quantile: float
    spare_kwh: float
    storable_kwh: float
    outage_need_kwh: float
    strategy: Strategy
    orders: tuple[SlotOrder, ...]
    risk_quantile: float | None
    decision: SlotDecision


def _commit_quantile(quantile: float) -> float:
    return min(_MAX_COMMIT_QUANTILE, max(_MIN_COMMIT_QUANTILE, quantile))


def _z(quantile: float) -> float:
    return NormalDist().inv_cdf(_commit_quantile(quantile))


def _perceive(state: _State) -> _State:
    return {"obs": state["obs"]}


def _project(state: _State) -> _State:
    obs = state["obs"]
    ctx = obs.context
    battery = ctx.battery_start
    protection = PROTECTION_FLOOR_SOC * battery.capacity_kwh
    net = [
        f.generation_p50 - f.consumption_p50 - committed
        for f, committed in zip(ctx.forecast, obs.committed_kwh, strict=True)
    ]
    # Charge needed to ride through every EB power cut still ahead, from
    # the cautious (P90 load, P10 sun) view: it's held back from ordinary use
    # in the hours before the cut begins.
    floors: list[float] = []
    for slot in range(len(net)):
        hold = 0.0
        if ctx.eb_available[slot]:
            hold = sum(
                max(0.0, ctx.forecast[t].consumption_p90 - ctx.forecast[t].generation_p10)
                for t in range(slot + 1, len(net))
                if not ctx.eb_available[t]
            )
        floors.append(min(0.95 * battery.capacity_kwh, protection + hold))
    plans = project(battery, net, floor_kwh=floors)
    return {"plans": plans, "outage_hold_kwh": floors[obs.slot] - protection}


def _value(state: _State) -> _State:
    obs = state["obs"]
    ctx = obs.context
    s = obs.slot
    f = ctx.forecast[s]
    fit, retail = ctx.feed_in[s], ctx.retail[s]
    learned = ctx.memory.expected_price(f.hour_of_day, feed_in_tariff=fit, retail_tariff=retail)
    expected = min(retail, max(fit, learned + obs.price_surprise))
    sigma = math.hypot(
        (f.generation_p90 - f.generation_p10) / _P10_P90_SIGMAS,
        (f.consumption_p90 - f.consumption_p10) / _P10_P90_SIGMAS,
    )
    if ctx.eb_available[s]:
        spread = max(retail - fit, 1e-6)
        sell_q = _commit_quantile((expected - fit) / spread)  # under-selling cost / total
        buy_q = _commit_quantile((retail - expected) / spread)  # under-buying cost / total
    else:
        sell_q, buy_q = _OUTAGE_SELL_QUANTILE, _OUTAGE_BUY_QUANTILE

    plans = state["plans"]
    battery = ctx.battery_start
    spare = spare_storage_kwh(
        plans,
        s,
        sale_floor_kwh=ctx.reserve * battery.capacity_kwh + state["outage_hold_kwh"],
        max_discharge_kwh=battery.max_discharge_kw,
    )
    storable = storable_kwh(
        plans, s, capacity_kwh=battery.capacity_kwh, max_charge_kwh=battery.max_charge_kw
    )
    outage_need = sum(
        plans[t].short_kwh for t in range(s + 1, len(plans)) if not ctx.eb_available[t]
    )
    return {
        "sigma_kwh": sigma,
        "expected_price": expected,
        "sell_quantile": sell_q,
        "buy_quantile": buy_q,
        "spare_kwh": spare,
        "storable_kwh": storable,
        "outage_need_kwh": outage_need,
    }


def _order(state: _State) -> _State:
    obs = state["obs"]
    ctx = obs.context
    s = obs.slot
    plan = state["plans"][s]
    fit, retail = ctx.feed_in[s], ctx.retail[s]
    expected = state["expected_price"]
    memory = ctx.memory
    soc = plan.stored_start_kwh / ctx.battery_start.capacity_kwh
    efficiency = ctx.battery_start.round_trip_efficiency

    def ask(
        kwh: float, floor: float, *, firm: bool, urgency: float, firm_kwh: float | None = None
    ) -> SlotOrder:
        floor = min(retail, max(fit, floor))
        return SlotOrder(
            household_id=ctx.household_id,
            side=Side.ASK,
            kwh=kwh,
            limit_price=floor,
            firm=firm,
            opening_price=min(retail, floor * (1 + memory.sell_margin)),
            urgency=min(1.0, max(0.0, urgency)),
            firm_kwh=firm_kwh,
        )

    def bid(
        kwh: float, ceiling: float, *, firm: bool, urgency: float, firm_kwh: float | None = None
    ) -> SlotOrder:
        ceiling = min(retail, max(fit, ceiling))
        return SlotOrder(
            household_id=ctx.household_id,
            side=Side.BID,
            kwh=kwh,
            limit_price=ceiling,
            firm=firm,
            opening_price=max(fit, ceiling * (1 - memory.buy_margin)),
            urgency=min(1.0, max(0.0, urgency)),
            firm_kwh=firm_kwh,
        )

    sigma = state["sigma_kwh"]
    orders: tuple[SlotOrder, ...] = ()
    risk: float | None = None
    strategy = Strategy.SELF_SUFFICIENT if plan.discharge_kwh or plan.charge_kwh else Strategy.IDLE

    if plan.spill_kwh > _MIN_ORDER_KWH:
        risk = state["sell_quantile"]
        kwh = max(0.0, plan.spill_kwh + _z(risk) * sigma)
        if kwh > _MIN_ORDER_KWH:
            orders = (
                ask(
                    kwh,
                    fit,
                    firm=True,
                    urgency=0.4 + 0.5 * soc,
                    firm_kwh=min(kwh, plan.spill_kwh),
                ),
            )
            strategy = Strategy.SELL_SURPLUS
    elif plan.short_kwh > _MIN_ORDER_KWH:
        risk = state["buy_quantile"]
        kwh = plan.short_kwh + max(0.0, _z(risk) * sigma)
        orders = (
            bid(
                kwh,
                retail,
                firm=True,
                urgency=0.4 + 0.5 * (1 - soc),
                firm_kwh=plan.short_kwh,
            ),
        )
        strategy = Strategy.BUY_SHORTFALL
    elif state["outage_need_kwh"] > _MIN_ORDER_KWH and state["storable_kwh"] > _MIN_ORDER_KWH:
        kwh = min(state["storable_kwh"], state["outage_need_kwh"] / efficiency)
        orders = (bid(kwh, retail, firm=True, urgency=0.8),)
        strategy = Strategy.PREPARE_OUTAGE
    elif state["storable_kwh"] > _MIN_ORDER_KWH:
        later_retail = max(ctx.retail[s + 1 :], default=retail)
        ceiling = efficiency * later_retail - _DEGRADATION_INR
        if ceiling > fit:
            orders = (bid(state["storable_kwh"], ceiling, firm=False, urgency=0.3),)
            strategy = Strategy.BUY_TO_STORE
    elif state["spare_kwh"] > _MIN_ORDER_KWH:
        floor = max(fit + _DEGRADATION_INR, _STORED_FLOOR_FRACTION * expected)
        orders = (ask(state["spare_kwh"], floor, firm=False, urgency=0.2 + 0.5 * soc),)
        strategy = Strategy.SELL_STORED

    return {"orders": orders, "strategy": strategy, "risk_quantile": risk}


def _speak(state: _State) -> _State:
    obs = state["obs"]
    s = obs.slot
    plan = state["plans"][s]
    decision = SlotDecision(
        household_id=obs.context.household_id,
        slot=s,
        hour_of_day=obs.context.forecast[s].hour_of_day,
        strategy=state["strategy"],
        orders=state["orders"],
        expected_net_kwh=plan.net_kwh,
        spill_kwh=plan.spill_kwh,
        short_kwh=plan.short_kwh,
        spare_kwh=state["spare_kwh"],
        storable_kwh=state["storable_kwh"],
        stored_kwh=plan.stored_start_kwh,
        charge_kwh=plan.charge_kwh,
        full_by_hour=next(
            (
                obs.context.forecast[p.slot].hour_of_day
                for p in state["plans"][s + 1 :]
                if p.spill_kwh > _MIN_ORDER_KWH
            ),
            None,
        ),
        risk_quantile=state["risk_quantile"],
        expected_price=state["expected_price"],
        message="",
        reasons=(),
    )
    return {
        "decision": replace(
            decision, message=slot_message(decision, obs), reasons=reasons_for(decision, obs)
        )
    }


class _Agents(TypedDict):
    """The graph's state: every household agent's own state, in order."""

    agents: list[_State]


def _for_each_agent(step: Callable[[_State], _State]) -> Any:  # a LangGraph node
    """A graph node applying one decision step to every agent, each on its
    own state alone."""

    def node(state: _Agents) -> _Agents:
        return {"agents": [{**agent, **step(agent)} for agent in state["agents"]]}

    return node


_STEPS: dict[str, Callable[[_State], _State]] = {
    "perceive": _perceive,
    "project": _project,
    "value": _value,
    "order": _order,
    "speak": _speak,
}


@lru_cache(maxsize=1)
def compiled_graph() -> Any:  # LangGraph's CompiledStateGraph is generic over untyped internals
    builder = StateGraph(_Agents)
    for name in GRAPH_NODES:
        builder.add_node(name, _for_each_agent(_STEPS[name]))
    builder.add_edge(START, GRAPH_NODES[0])
    for upstream, downstream in pairwise(GRAPH_NODES):
        builder.add_edge(upstream, downstream)
    builder.add_edge(GRAPH_NODES[-1], END)
    return builder.compile()


def decide_slots(observations: Sequence[SlotObservation]) -> list[SlotDecision]:
    """Every household's agent decides this slot, in the order given."""
    if not observations:
        return []
    result = compiled_graph().invoke({"agents": [{"obs": obs} for obs in observations]})
    return [agent["decision"] for agent in result["agents"]]


def decide_slot(observation: SlotObservation) -> SlotDecision:
    """One household's agent decides one slot of the session."""
    return decide_slots([observation])[0]
