"""Bridges the pure domain tick to the database: loads every household and
the ledger's current state, calls `run_tick`, and persists exactly what it
returns."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_sessionmaker
from app.core.logging import get_logger
from app.domain.battery.model import Battery
from app.domain.engine.tick import HouseholdTickInput, TickResult, run_tick
from app.domain.grid.network import default_feeder
from app.domain.ledger.hashchain import LedgerEntry
from app.models.household import Household
from app.models.simulation import (
    SIMULATION_STATE_SINGLETON_ID,
    CurtailmentRecord,
    LedgerEntryRecord,
    MeterReading,
    SimulationState,
    TradeRecord,
)
from app.simulator.profiles import hour_of_day, reading_for
from app.simulator.scenarios import Scenario

log = get_logger(__name__)

# A household with no battery still needs a *valid* one to plug into the
# domain layer's Battery dataclass (which requires capacity_kwh > 0) — zero
# max charge/discharge rates make it accept and deliver exactly 0 kW every
# tick, which is the correct behaviour for "this house has no battery" without
# a separate code path in the tick engine itself.
_NO_BATTERY_CAPACITY_KWH = 0.01

# Daylight hours during which the evening reserve does not apply — outside
# this window a household may be drained past its reserve floor at night, but
# not once the reserve setting is meant to start protecting it for tomorrow
# morning's peak.
_DAYLIGHT_START_HOUR = 6.0
_DAYLIGHT_END_HOUR = 18.0


def _household_order(household_id: str) -> int:
    """Households sort by their numeric suffix (h1, h2, ... h10), not
    lexically ("h10" < "h2") — this order feeds `default_feeder`'s lateral
    assignment and must be identical every tick for a stable feeder."""
    return int(household_id[1:])


async def get_or_create_state(session: AsyncSession) -> SimulationState:
    state = await session.get(SimulationState, SIMULATION_STATE_SINGLETON_ID)
    if state is None:
        state = SimulationState(id=SIMULATION_STATE_SINGLETON_ID)
        session.add(state)
        await session.flush()
    return state


def touch(state: SimulationState) -> None:
    """Mark `state` as just-modified. Call before committing any change to
    it — see the comment on `SimulationState.updated_at` for why this isn't
    a server-side `onupdate` instead."""
    state.updated_at = datetime.now(UTC)


async def _load_ledger_chain(session: AsyncSession) -> tuple[LedgerEntry, ...]:
    rows = (
        await session.scalars(
            select(LedgerEntryRecord).order_by(LedgerEntryRecord.sequence)
        )
    ).all()
    return tuple(
        LedgerEntry(
            sequence=row.sequence,
            tick_index=row.tick_index,
            buyer_household_id=row.buyer_household_id,
            seller_household_id=row.seller_household_id,
            kwh=row.kwh,
            price_per_kwh=row.price_per_kwh,
            total_amount=row.total_amount,
            prev_hash=row.prev_hash,
            hash=row.hash,
        )
        for row in rows
    )


def _battery_for(household: Household) -> Battery:
    has_battery = household.battery_capacity_kwh > 0
    return Battery(
        capacity_kwh=household.battery_capacity_kwh if has_battery else _NO_BATTERY_CAPACITY_KWH,
        soc=household.battery_soc,
        max_charge_kw=household.battery_max_charge_kw,
        max_discharge_kw=household.battery_max_discharge_kw,
    )


async def advance_one_tick(session: AsyncSession, settings: Settings | None = None) -> TickResult:
    """Run exactly one tick against the real database and persist it."""
    settings = settings or get_settings()
    state = await get_or_create_state(session)
    households = (
        await session.scalars(select(Household).order_by(Household.id))
    ).all()
    ordered_households = sorted(households, key=lambda h: _household_order(h.id))

    scenario = Scenario(state.scenario)
    hour = hour_of_day(state.tick_index, tick_minutes=settings.market_tick_minutes)
    is_evening = not (_DAYLIGHT_START_HOUR <= hour < _DAYLIGHT_END_HOUR)
    duration_h = settings.market_tick_minutes / 60.0

    def _input_for(household: Household) -> HouseholdTickInput:
        reading = reading_for(
            household.id,
            state.tick_index,
            member_count=household.member_count,
            solar_capacity_kwp=household.solar_capacity_kwp,
            tick_minutes=settings.market_tick_minutes,
            scenario=scenario,
            seed=settings.sim_seed,
        )
        return HouseholdTickInput(
            household_id=household.id,
            consumption_kw=reading.consumption_kw,
            generation_kw=reading.generation_kw,
            battery=_battery_for(household),
            evening_reserve=household.evening_reserve,
        )

    inputs = tuple(_input_for(household) for household in ordered_households)

    network = default_feeder([household.id for household in ordered_households])
    ledger_chain = await _load_ledger_chain(session)

    result = run_tick(
        tick_index=state.tick_index,
        inputs=inputs,
        network=network,
        ledger_chain=ledger_chain,
        duration_h=duration_h,
        feed_in_tariff=settings.feed_in_tariff,
        retail_tariff=settings.retail_tariff,
        is_evening=is_evening,
    )

    households_by_id = {household.id: household for household in ordered_households}
    for outcome in result.household_outcomes:
        households_by_id[outcome.household_id].battery_soc = outcome.battery.soc
        session.add(
            MeterReading(
                tick_index=result.tick_index,
                household_id=outcome.household_id,
                consumption_kw=outcome.consumption_kw,
                generation_kw=outcome.generation_kw,
                battery_soc=outcome.battery.soc,
                battery_action=outcome.battery_action.value,
                grid_kwh=outcome.grid_kwh,
            )
        )

    for trade in result.safety.trades:
        session.add(
            TradeRecord(
                tick_index=result.tick_index,
                buyer_household_id=trade.buyer_household_id,
                seller_household_id=trade.seller_household_id,
                kwh=trade.kwh,
                price_per_kwh=trade.price_per_kwh,
            )
        )

    for curtailment in result.safety.curtailments:
        session.add(
            CurtailmentRecord(
                tick_index=result.tick_index,
                buyer_household_id=curtailment.buyer_household_id,
                seller_household_id=curtailment.seller_household_id,
                curtailed_kwh=curtailment.curtailed_kwh,
                reason=curtailment.reason,
            )
        )

    for entry in result.new_ledger_entries:
        session.add(
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

    state.tick_index += 1
    touch(state)
    await session.commit()
    return result


async def simulation_loop(*, poll_seconds: float = 0.5) -> None:
    """Runs for the lifetime of the process: advances a tick every
    `seconds_per_tick` while the simulation is playing, otherwise polls
    cheaply for the next `play`. One shared clock for every household on the
    feeder — there is no per-household loop."""
    session_factory = get_sessionmaker()
    while True:
        async with session_factory() as session:
            state = await get_or_create_state(session)
            running = state.running
            seconds_per_tick = state.seconds_per_tick
            # get_or_create_state only flushes, not commits — without this,
            # an idle process would insert-then-rollback the singleton row
            # every poll forever, instead of creating it exactly once.
            await session.commit()

        if not running:
            await asyncio.sleep(poll_seconds)
            continue

        try:
            async with session_factory() as session:
                await advance_one_tick(session)
        except Exception:
            log.exception("simulation.tick_failed")
            await asyncio.sleep(poll_seconds)
            continue

        await asyncio.sleep(seconds_per_tick)


def start_background_loop() -> asyncio.Task[None]:
    return asyncio.create_task(simulation_loop())


async def stop_background_loop(task: asyncio.Task[None]) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
