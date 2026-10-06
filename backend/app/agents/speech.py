"""What an agent says: its plan for each hour before that slot's market opens,
and what happened once it cleared.

Built from the decision's own numbers only — a template can't invent a
reason the decision didn't have, which is why this, not an LLM, is the
voice of record (ADR-0005). Energy is in "units" (1 unit = 1 kWh), the way
every Tamil Nadu EB bill reads; money in rupees.
"""

from __future__ import annotations

from app.agents.types import SlotDecision, SlotObservation, Strategy


def units(kwh: float) -> str:
    return f"{kwh:.2f} units"


def inr(value: float | None) -> str:
    return f"₹{value:.2f}" if value is not None else "—"


def clock(hour: float) -> str:
    h = int(hour) % 24
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


def _hour_range(hour: int) -> str:
    return f"{clock(hour)}–{clock(hour + 1)}"


def _pct(fraction: float) -> str:
    return f"{round(fraction * 100)}%"


def slot_message(decision: SlotDecision, obs: SlotObservation) -> str:
    ctx = obs.context
    s = obs.slot
    when = _hour_range(decision.hour_of_day)
    q = units(decision.quantity_kwh)
    limit, opening = decision.limit_price, decision.opening_price
    soc = _pct(decision.stored_kwh / ctx.battery_start.capacity_kwh)
    risk = f"P{round(decision.risk_quantile * 100)}" if decision.risk_quantile is not None else ""
    hedged = decision.quantity_kwh - max(decision.spill_kwh, decision.short_kwh) > 0.05
    outage_later = any(not up for up in ctx.eb_available[s + 1 :])
    match decision.strategy:
        case Strategy.SELL_SURPLUS if hedged:
            return (
                f"{when}: offering {q} — the panels should out-produce our load by about "
                f"{units(decision.spill_kwh)} with the battery full, and the market's paying "
                f"well, so I'm offering up to the {risk} of that surplus; the EB takes only the "
                f"expected {units(decision.spill_kwh)} if neighbours don't. Asking "
                f"{inr(opening)}, won't go below {inr(limit)}."
            )
        case Strategy.SELL_SURPLUS:
            return (
                f"{when}: offering {q} — the panels should out-produce our load by about "
                f"{units(decision.spill_kwh)} with the battery full. Committing only the "
                f"{risk} of that surplus so a cloud doesn't leave me buying back at "
                f"{inr(ctx.retail[s])}. Asking {inr(opening)}, won't go below {inr(limit)}."
            )
        case Strategy.SELL_STORED if decision.charge_kwh > 0 and decision.full_by_hour is not None:
            return (
                f"{when}: offering {q} of this hour's solar instead of storing all of it — "
                f"the battery ({soc} now) will still be full by {clock(decision.full_by_hour)}. "
                f"Asking {inr(opening)}, floor {inr(limit)}."
            )
        case Strategy.SELL_STORED:
            return (
                f"{when}: offering {q} of stored charge — the battery ({soc}) holds more than "
                f"we'll need for the rest of the session, and I never sell below the "
                f"{_pct(ctx.reserve)} reserve. Asking {inr(opening)}, floor {inr(limit)}."
            )
        case Strategy.BUY_SHORTFALL if hedged:
            return (
                f"{when}: bidding for {q} — forecast load outruns our sun and battery by about "
                f"{units(decision.short_kwh)}; neighbours are cheap enough that covering the "
                f"{risk} of that need is worth it, since coming up short means paying the EB "
                f"{inr(ctx.retail[s])}. The EB covers only the expected "
                f"{units(decision.short_kwh)} if neighbours can't. Opening at {inr(opening)}, "
                f"up to {inr(limit)}."
            )
        case Strategy.BUY_SHORTFALL:
            return (
                f"{when}: need {q} — forecast load outruns our sun and battery by about "
                f"{units(decision.short_kwh)}; at the price I expect, hedging beyond that isn't "
                f"worth it — anything extra comes from the EB at {inr(ctx.retail[s])} as it "
                f"happens. Opening at {inr(opening)}, up to {inr(limit)}."
            )
        case Strategy.PREPARE_OUTAGE:
            return (
                f"{when}: buying {q} to store — there's an EB power cut coming and our battery "
                "alone won't carry the house through it. Paying up to the EB rate if "
                "neighbours can't cover it; the lights matter more."
            )
        case Strategy.BUY_TO_STORE:
            return (
                f"{when}: bidding for {q} to store — we'll be short later"
                f"{' (a power cut is due)' if outage_later else ' tonight'}, and a neighbour's "
                f"spare now beats the EB's {inr(max(ctx.retail[s:]))} later. Only from "
                f"neighbours; opening at {inr(opening)}, up to {inr(limit)}."
            )
        case Strategy.SELF_SUFFICIENT:
            return f"{when}: our own panels and battery ({soc}) cover this hour — nothing to trade."
        case _:
            return f"{when}: balanced — nothing to buy or sell."


def reasons_for(decision: SlotDecision, obs: SlotObservation) -> tuple[str, ...]:
    ctx = obs.context
    s = obs.slot
    f = ctx.forecast[s]
    learned = ctx.memory.expected_price(
        decision.hour_of_day, feed_in_tariff=ctx.feed_in[s], retail_tariff=ctx.retail[s]
    )
    price = f"Learned market price for {clock(decision.hour_of_day)}: {inr(learned)}"
    if abs(decision.expected_price - learned) >= 0.05:
        trend = "higher" if decision.expected_price > learned else "lower"
        price += f"; expecting {inr(decision.expected_price)} — today's market is clearing {trend}"
    reasons = [
        f"Forecast load {f.consumption_p10:.2f}–{f.consumption_p90:.2f} kW (P10–P90), "
        f"solar {f.generation_p10:.2f}–{f.generation_p90:.2f} kW",
        f"Battery expected at {units(decision.stored_kwh)} as the hour starts",
        price,
    ]
    if decision.risk_quantile is not None:
        reasons.append(
            f"Committed at the forecast's P{round(decision.risk_quantile * 100)} "
            "(newsvendor: cost of over- vs under-committing)"
        )
    if not ctx.eb_available[obs.slot]:
        reasons.append("EB power cut this hour — no grid to fall back on")
    return tuple(reasons)


def outcome_message(
    decision: SlotDecision,
    *,
    trades: list[tuple[str, float, float, int]],
    eb_kwh: float,
    eb_price: float | None,
    unserved_kwh: float,
) -> str:
    """After the slot clears. `trades` is (counterparty, kWh, price, round)
    for each of this household's matched trades."""
    if not decision.orders:
        return ""
    selling = decision.side == "sell"
    verb, preposition = ("Sold", "to") if selling else ("Bought", "from")
    parts = [
        f"{verb} {units(kwh)} {preposition} {name} at {inr(price)} (round {round_index + 1})"
        for name, kwh, price, round_index in trades
    ]
    if eb_kwh > 1e-6 and eb_price is not None:
        parts.append(f"{units(eb_kwh)} {'to' if selling else 'from'} the EB at {inr(eb_price)}")
    if unserved_kwh > 1e-6:
        parts.append(f"{units(unserved_kwh)} can't be supplied — the EB is down")
    if not parts:
        parts.append(
            "no neighbour met my price, so I'll keep it"
            if selling
            else "no neighbour had any to spare"
        )
    return "; ".join(parts) + "."
