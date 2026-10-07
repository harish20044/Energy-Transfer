"""Planning sessions: the user picks when, what weather and which what-ifs;
each household's agent forecasts, plans and bids hour by hour against its
neighbours and the EB; then the hours are delivered one at a time against
what really happens.

Nothing here runs on its own — every step is an explicit request, the way a
household would actually plan ahead rather than watch a clock tick.

1. **plan**: forecast every household's next 4-24 hours, then clear one
   hourly market slot at a time in order. Each agent sees the contracts it
   already made for earlier slots, so a household that bought cheap noon
   solar to store bids for less at night.
2. **next hour**: deliver the next slot's four 15-minute intervals: real
   (simulated) weather and family, contracts honoured, the battery absorbing
   forecast errors first and the EB settling the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory import AgentMemory
from app.agents.persistence import load_memories, save_memory
from app.agents.types import SessionContext
from app.core.config import Settings
from app.domain.battery.model import Battery
from app.domain.grid.network import default_feeder
from app.domain.ledger.hashchain import LedgerEntry, append
from app.domain.settlement.delivery import deliver
from app.engine.market_run import SessionMarket
from app.forecasting.predict import forecast_household
from app.models.agent import AgentDecisionRecord
from app.models.household import Household
from app.models.session import SessionForecast, SessionHousehold, SessionPosition
from app.models.simulation import (
    SIMULATION_STATE_SINGLETON_ID,
    CurtailmentRecord,
    LedgerEntryRecord,
    MeterReading,
    NegotiationOfferRecord,
    SimulationState,
    TradeRecord,
)
from app.schemas.session import PEAK_END_HOUR, PEAK_START_HOUR, HouseholdWhatIf, SessionConfigIn
from app.simulator.family import HouseholdOverride
from app.simulator.household import HouseholdDay, simulate_household_day
from app.simulator.scenarios import Scenario

MINUTES_PER_DAY = 24 * 60
# A household with no battery still needs a *valid* one for the domain
# layer (capacity must be positive); zero charge/discharge rates make it
# behave exactly like no battery at all.
_NO_BATTERY_CAPACITY_KWH = 0.01
# Where a warm start begins: the battery is assumed half full a day before
# the session, then the preceding 24 hours are replayed without trading.
_WARM_START_SOC = 0.5


class SessionError(ValueError):
    """A session request that doesn't fit the session's current state."""


def household_order(household_id: str) -> tuple[int, int, str]:
    """h1, h2, ... h10 in numeric order (not "h10" < "h2") — the order
    `default_feeder` lays them on the feeder, which must be identical every
    time. Any other id sorts after them, alphabetically."""
    suffix = household_id[1:]
    if household_id.startswith("h") and suffix.isdigit():
        return (0, int(suffix), "")
    return (1, 0, household_id)


async def get_or_create_state(session: AsyncSession) -> SimulationState:
    state = await session.get(SimulationState, SIMULATION_STATE_SINGLETON_ID)
    if state is None:
        state = SimulationState(id=SIMULATION_STATE_SINGLETON_ID)
        session.add(state)
        await session.flush()
    return state


def touch(state: SimulationState) -> None:
    """Mark `state` as just-modified — see `SimulationState.updated_at`."""
    state.updated_at = datetime.now(UTC)


def battery_for(household: Household, soc: float, capacity_kwh: float | None = None) -> Battery:
    """The household's battery — or, for a session what-if, one of a
    different size (0 = none), with rates scaled to its size as real
    products are (a 3 kW inverter per 10 kWh)."""
    capacity = household.battery_capacity_kwh if capacity_kwh is None else capacity_kwh
    if capacity <= 0:
        return Battery(
            capacity_kwh=_NO_BATTERY_CAPACITY_KWH, soc=0.0, max_charge_kw=0.0, max_discharge_kw=0.0
        )
    scale = (
        1.0 if household.battery_capacity_kwh <= 0 else capacity / household.battery_capacity_kwh
    )
    return Battery(
        capacity_kwh=capacity,
        soc=min(1.0, max(0.0, soc)),
        max_charge_kw=household.battery_max_charge_kw * scale,
        max_discharge_kw=household.battery_max_discharge_kw * scale,
    )


def retail_at(base: float, surcharge_pct: float, hour_of_day: int) -> float:
    """The EB's import tariff for an hour, with any evening-peak surcharge."""
    if PEAK_START_HOUR <= hour_of_day < PEAK_END_HOUR:
        return base * (1.0 + surcharge_pct / 100.0)
    return base


def eb_up(power_cut: dict[str, int] | None, clock_hours: float) -> bool:
    """Is the EB supplying at `clock_hours` (from midnight of the session's
    first day)?"""
    if not power_cut:
        return True
    return not (power_cut["start_hour"] <= clock_hours < power_cut["end_hour"])


def override_of(what_if: HouseholdWhatIf | SessionHousehold) -> HouseholdOverride:
    return HouseholdOverride(
        guests=what_if.guests,
        away_from=what_if.away_from,
        away_to=what_if.away_to,
        work_from_home=what_if.work_from_home,
        panel_derate=what_if.panel_derate,
    )


def household_day(
    household: Household,
    day: date,
    *,
    sim_date: date,
    scenario: Scenario,
    override: HouseholdOverride,
    seed: int,
    tick_minutes: int,
) -> HouseholdDay:
    """The simulated day behind a household's meter: the session's weather
    and what-ifs on its own dates, climatology and history before them."""
    if day < sim_date:
        day_scenario, day_override = Scenario.AUTO, override.history()
    elif day == sim_date:
        day_scenario, day_override = scenario, override
    else:
        day_scenario, day_override = scenario, override.next_day()
    return simulate_household_day(
        household.id,
        household.member_count,
        household.solar_capacity_kwp,
        day,
        day_scenario,
        seed,
        tick_minutes,
        day_override,
    )


def reading_at(
    household: Household,
    clock_minutes: int,
    *,
    sim_date: date,
    scenario: Scenario,
    override: HouseholdOverride,
    seed: int,
    tick_minutes: int,
) -> tuple[float, float]:
    """(consumption_kw, generation_kw) for the interval starting
    `clock_minutes` after midnight of `sim_date` (may be negative)."""
    day = sim_date + timedelta(days=clock_minutes // MINUTES_PER_DAY)
    index = (clock_minutes % MINUTES_PER_DAY) // tick_minutes
    hd = household_day(
        household,
        day,
        sim_date=sim_date,
        scenario=scenario,
        override=override,
        seed=seed,
        tick_minutes=tick_minutes,
    )
    return float(hd.consumption_kw[index]), float(hd.generation_kw[index])


def warm_start_soc(
    household: Household,
    *,
    sim_date: date,
    start_hour: int,
    scenario: Scenario,
    override: HouseholdOverride,
    seed: int,
    tick_minutes: int,
    capacity_kwh: float,
) -> float:
    """The battery's charge at the session start, left by the 24 hours
    before it — full at 2 pm on a sunny day, low at dawn after a hot night —
    rather than an arbitrary number."""
    battery = battery_for(household, _WARM_START_SOC, capacity_kwh)
    start = start_hour * 60
    for minutes in range(start - MINUTES_PER_DAY, start, tick_minutes):
        consumption, generation = reading_at(
            household,
            minutes,
            sim_date=sim_date,
            scenario=scenario,
            override=override,
            seed=seed,
            tick_minutes=tick_minutes,
        )
        battery = deliver(
            battery,
            generation_kw=generation,
            consumption_kw=consumption,
            contracted_export_kw=0.0,
            duration_h=tick_minutes / 60.0,
            eb_available=True,
        ).battery
    return battery.soc


@dataclass(frozen=True, slots=True)
class PreparedHousehold:
    """Everything fixed about one household for a session, before trading."""

    context: SessionContext
    start_soc: float
    capacity_kwh: float
    override: HouseholdOverride


def prepare_household(
    household: Household,
    what_if: HouseholdWhatIf,
    *,
    sim_date: date,
    start_hour: int,
    scenario: Scenario,
    retail: tuple[float, ...],
    feed_in: tuple[float, ...],
    eb: tuple[bool, ...],
    seed: int,
    tick_minutes: int,
    memory: AgentMemory,
) -> PreparedHousehold:
    """A household's battery at the session start, its forecast for every
    slot, and the agent context built from both. Pure: the app persists the
    result, the evaluation harness uses it directly."""
    override = override_of(what_if)
    capacity = (
        what_if.battery_capacity_kwh
        if what_if.battery_capacity_kwh is not None
        else household.battery_capacity_kwh
    )
    start_soc = what_if.battery_start_soc if capacity > 0 else 0.0
    if start_soc is None:
        start_soc = warm_start_soc(
            household,
            sim_date=sim_date,
            start_hour=start_hour,
            scenario=scenario,
            override=override,
            seed=seed,
            tick_minutes=tick_minutes,
            capacity_kwh=capacity,
        )
    _, forecast = forecast_household(
        household_id=household.id,
        member_count=household.member_count,
        solar_capacity_kwp=household.solar_capacity_kwp,
        start_date=sim_date,
        start_hour=start_hour,
        horizon_hours=len(retail),
        scenario=scenario,
        seed=seed,
        tick_minutes=tick_minutes,
        override=override,
    )
    context = SessionContext(
        household_id=household.id,
        display_name=household.display_name,
        battery_start=battery_for(household, start_soc, capacity),
        reserve=household.evening_reserve,
        forecast=tuple(forecast),
        retail=retail,
        feed_in=feed_in,
        eb_available=eb,
        memory=memory,
    )
    return PreparedHousehold(
        context=context, start_soc=start_soc, capacity_kwh=capacity, override=override
    )


def session_tariffs(
    *,
    start_hour: int,
    horizon: int,
    retail_tariff: float,
    feed_in_tariff: float,
    peak_surcharge_pct: float,
    power_cut: dict[str, int] | None,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[bool, ...]]:
    """Per-slot retail tariff, feed-in tariff and EB availability."""
    slot_hours = [start_hour + s for s in range(horizon)]
    retail = tuple(retail_at(retail_tariff, peak_surcharge_pct, h % 24) for h in slot_hours)
    feed_in = (feed_in_tariff,) * horizon
    eb = tuple(eb_up(power_cut, float(h)) for h in slot_hours)
    return retail, feed_in, eb


async def _ordered_households(db: AsyncSession) -> list[Household]:
    households = (await db.scalars(select(Household))).all()
    return sorted(households, key=lambda h: household_order(h.id))


async def clear_session(db: AsyncSession) -> None:
    """Remove everything the previous session produced. Agents' learned
    memory is deliberately kept."""
    for model in (
        MeterReading,
        AgentDecisionRecord,
        NegotiationOfferRecord,
        TradeRecord,
        CurtailmentRecord,
        LedgerEntryRecord,
        SessionPosition,
        SessionForecast,
        SessionHousehold,
    ):
        await db.execute(delete(model))


async def reset_session(db: AsyncSession) -> SimulationState:
    await clear_session(db)
    state = await get_or_create_state(db)
    state.status = "setup"
    state.tick_index = 0
    touch(state)
    await db.commit()
    return state


async def plan_session(
    db: AsyncSession, settings: Settings, config: SessionConfigIn
) -> SimulationState:
    """Forecast every household and clear every hourly slot of the session."""
    base_retail = config.tariffs.retail_tariff or settings.retail_tariff
    base_fit = (
        config.tariffs.feed_in_tariff
        if config.tariffs.feed_in_tariff is not None
        else settings.feed_in_tariff
    )
    if base_fit >= base_retail:
        msg = f"the feed-in tariff (₹{base_fit}) must be below the retail tariff (₹{base_retail})"
        raise SessionError(msg)

    await clear_session(db)
    state = await get_or_create_state(db)
    horizon = config.horizon_hours
    tick_minutes = settings.market_tick_minutes
    power_cut = config.power_cut.model_dump() if config.power_cut else None
    state.sim_date = config.sim_date
    state.start_hour = config.start_hour
    state.horizon_hours = horizon
    state.scenario = config.scenario.value
    state.status = "planned"
    state.tick_index = 0
    state.what_ifs = {
        "power_cut": power_cut,
        "retail_tariff": base_retail,
        "feed_in_tariff": base_fit,
        "peak_surcharge_pct": config.tariffs.peak_surcharge_pct,
    }

    retail, feed_in, eb = session_tariffs(
        start_hour=config.start_hour,
        horizon=horizon,
        retail_tariff=base_retail,
        feed_in_tariff=base_fit,
        peak_surcharge_pct=config.tariffs.peak_surcharge_pct,
        power_cut=power_cut,
    )

    households = await _ordered_households(db)
    what_ifs = {w.household_id: w for w in config.households}
    memories = await load_memories(db)
    contexts: dict[str, SessionContext] = {}
    for household in households:
        what_if = what_ifs.get(household.id) or HouseholdWhatIf(household_id=household.id)
        prepared = prepare_household(
            household,
            what_if,
            sim_date=config.sim_date,
            start_hour=config.start_hour,
            scenario=config.scenario,
            retail=retail,
            feed_in=feed_in,
            eb=eb,
            seed=settings.sim_seed,
            tick_minutes=tick_minutes,
            memory=memories.get(household.id, AgentMemory()),
        )
        household.battery_soc = prepared.start_soc
        db.add(
            SessionHousehold(
                household_id=household.id,
                start_soc=prepared.start_soc,
                guests=what_if.guests,
                away_from=what_if.away_from,
                away_to=what_if.away_to,
                work_from_home=what_if.work_from_home,
                panel_derate=what_if.panel_derate,
                battery_capacity_kwh=prepared.capacity_kwh,
            )
        )
        for f in prepared.context.forecast:
            db.add(
                SessionForecast(
                    slot=f.slot,
                    household_id=household.id,
                    day=f.day,
                    hour_of_day=f.hour_of_day,
                    consumption_p10=f.consumption_p10,
                    consumption_p50=f.consumption_p50,
                    consumption_p90=f.consumption_p90,
                    generation_p10=f.generation_p10,
                    generation_p50=f.generation_p50,
                    generation_p90=f.generation_p90,
                )
            )
        contexts[household.id] = prepared.context

    network = default_feeder([h.id for h in households])
    market = SessionMarket(
        contexts,
        network=network,
        names={h.id: h.display_name for h in households},
        memories=memories,
    )
    chain: tuple[LedgerEntry, ...] = ()

    while not market.done:
        cleared = market.clear_next()
        slot, clearing = cleared.slot, cleared.clearing
        for negotiation_round in clearing.negotiation.rounds:
            for offer in (*negotiation_round.asks, *negotiation_round.bids):
                db.add(
                    NegotiationOfferRecord(
                        tick_index=slot,
                        round_index=negotiation_round.round_index,
                        household_id=offer.household_id,
                        side=offer.side.value,
                        price=offer.limit_price,
                        kwh=offer.kwh,
                    )
                )
        for trade in clearing.safety.trades:
            db.add(
                TradeRecord(
                    tick_index=slot,
                    round_index=trade.round_index,
                    buyer_household_id=trade.buyer_household_id,
                    seller_household_id=trade.seller_household_id,
                    kwh=trade.kwh,
                    price_per_kwh=trade.price_per_kwh,
                )
            )
            previous = len(chain)
            chain = append(
                chain,
                tick_index=slot,
                buyer_household_id=trade.buyer_household_id,
                seller_household_id=trade.seller_household_id,
                kwh=trade.kwh,
                price_per_kwh=trade.price_per_kwh,
            )
            entry = chain[previous]
            db.add(
                LedgerEntryRecord(
                    sequence=entry.sequence,
                    tick_index=entry.tick_index,
                    buyer_household_id=entry.buyer_household_id,
                    seller_household_id=entry.seller_household_id,
                    kwh=entry.kwh,
                    price_per_kwh=entry.price_per_kwh,
                    total_amount=entry.total_amount,
                    prev_hash=entry.prev_hash,
                    hash=entry.hash,
                )
            )
        for curtailment in clearing.safety.curtailments:
            db.add(
                CurtailmentRecord(
                    tick_index=slot,
                    buyer_household_id=curtailment.buyer_household_id,
                    seller_household_id=curtailment.seller_household_id,
                    curtailed_kwh=curtailment.curtailed_kwh,
                    reason=curtailment.reason,
                )
            )
        for hid, part in cleared.households.items():
            decision = part.decision
            db.add(
                SessionPosition(
                    slot=slot,
                    household_id=hid,
                    p2p_sold_kwh=part.sold_kwh,
                    p2p_bought_kwh=part.bought_kwh,
                    eb_bought_kwh=part.eb_bought_kwh,
                    eb_sold_kwh=part.eb_sold_kwh,
                    unserved_kwh=part.unserved_kwh,
                    retail_tariff=retail[slot],
                    feed_in_tariff=feed_in[slot],
                    eb_available=eb[slot],
                )
            )
            db.add(
                AgentDecisionRecord(
                    slot=slot,
                    household_id=hid,
                    hour_of_day=decision.hour_of_day,
                    strategy=decision.strategy.value,
                    side=decision.side,
                    firm=bool(decision.orders and decision.orders[0].firm),
                    quantity_kwh=decision.quantity_kwh,
                    limit_price=decision.limit_price,
                    opening_price=decision.opening_price,
                    risk_quantile=decision.risk_quantile,
                    expected_price=decision.expected_price,
                    spill_kwh=decision.spill_kwh,
                    short_kwh=decision.short_kwh,
                    stored_kwh=decision.stored_kwh,
                    message=decision.message,
                    outcome=part.outcome,
                    reasons=list(decision.reasons),
                )
            )

    for hid, memory in market.memories.items():
        await save_memory(db, hid, memory)
    touch(state)
    await db.commit()
    return state


async def advance_hour(db: AsyncSession, settings: Settings) -> SimulationState:
    """Deliver the next hour of the session against what really happens."""
    state = await get_or_create_state(db)
    if state.status not in ("planned", "playing"):
        msg = f"nothing to deliver: the session is {state.status}"
        raise SessionError(msg)
    tick_minutes = settings.market_tick_minutes
    ticks_per_hour = 60 // tick_minutes
    slot = state.tick_index // ticks_per_hour
    horizon = state.horizon_hours

    households = await _ordered_households(db)
    positions = {
        p.household_id: p
        for p in (
            await db.scalars(select(SessionPosition).where(SessionPosition.slot == slot))
        ).all()
    }
    setups = {s.household_id: s for s in (await db.scalars(select(SessionHousehold))).all()}
    power_cut = (state.what_ifs or {}).get("power_cut")
    scenario = Scenario(state.scenario)
    duration_h = tick_minutes / 60.0

    for step in range(ticks_per_hour):
        tick = state.tick_index + step
        clock_minutes = state.start_hour * 60 + tick * tick_minutes
        available = eb_up(power_cut, clock_minutes / 60.0)
        for household in households:
            setup = setups.get(household.id)
            override = override_of(setup) if setup else HouseholdOverride()
            consumption, generation = reading_at(
                household,
                clock_minutes,
                sim_date=state.sim_date,
                scenario=scenario,
                override=override,
                seed=settings.sim_seed,
                tick_minutes=tick_minutes,
            )
            position = positions.get(household.id)
            contracted_kw = (
                (position.p2p_sold_kwh - position.p2p_bought_kwh) if position else 0.0
            )  # a 1-hour slot's kWh is its average kW
            capacity = setup.battery_capacity_kwh if setup else None
            delivery = deliver(
                battery_for(household, household.battery_soc, capacity),
                generation_kw=generation,
                consumption_kw=consumption,
                contracted_export_kw=contracted_kw,
                duration_h=duration_h,
                eb_available=available,
            )
            household.battery_soc = delivery.battery.soc
            action = (
                "charging"
                if delivery.battery_kwh > 1e-9
                else "discharging"
                if delivery.battery_kwh < -1e-9
                else "idle"
            )
            db.add(
                MeterReading(
                    tick_index=tick,
                    household_id=household.id,
                    consumption_kw=consumption,
                    generation_kw=generation,
                    battery_soc=delivery.battery.soc,
                    battery_action=action,
                    grid_kwh=delivery.eb_import_kwh - delivery.eb_export_kwh,
                    contracted_kwh=contracted_kw * duration_h,
                    unserved_kwh=delivery.unserved_kwh,
                    curtailed_kwh=delivery.curtailed_kwh,
                )
            )

    state.tick_index += ticks_per_hour
    state.status = "complete" if state.tick_index >= horizon * ticks_per_hour else "playing"
    touch(state)
    await db.commit()
    return state
