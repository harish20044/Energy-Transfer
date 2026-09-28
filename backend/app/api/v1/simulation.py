"""Control surface for the one shared simulation clock every household's
feeder runs on.

Any signed-in account may drive play/pause/step/reset — there is exactly one
feeder and one clock for the whole demo, not one per household, so this is
shared infrastructure rather than something that needs household-scoped
isolation the way `/households/me` does.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import delete, update

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.engine.runner import advance_one_tick, get_or_create_state, touch
from app.models.household import Household
from app.models.simulation import (
    CurtailmentRecord,
    LedgerEntryRecord,
    MeterReading,
    SimulationState,
    TradeRecord,
)
from app.schemas.simulation import PlayRequest, SimulationStateOut
from app.simulator.profiles import day_index, hour_of_day

router = APIRouter(prefix="/simulation", tags=["simulation"])


def _to_out(state: SimulationState, *, tick_minutes: int) -> SimulationStateOut:
    return SimulationStateOut(
        tick_index=state.tick_index,
        running=state.running,
        scenario=state.scenario,  # type: ignore[arg-type]
        seconds_per_tick=state.seconds_per_tick,
        simulated_day=day_index(state.tick_index, tick_minutes=tick_minutes),
        simulated_hour=hour_of_day(state.tick_index, tick_minutes=tick_minutes),
        updated_at=state.updated_at,
    )


@router.get("/state", response_model=SimulationStateOut)
async def read_state(
    _current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> SimulationStateOut:
    state = await get_or_create_state(db)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)


@router.post("/play", response_model=SimulationStateOut)
async def play(
    _current_user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    body: PlayRequest = PlayRequest(),  # noqa: B008 -- immutable request body, never mutated
) -> SimulationStateOut:
    state = await get_or_create_state(db)
    state.running = True
    if body.scenario is not None:
        state.scenario = body.scenario.value
    if body.seconds_per_tick is not None:
        state.seconds_per_tick = body.seconds_per_tick
    touch(state)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)


@router.post("/pause", response_model=SimulationStateOut)
async def pause(
    _current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> SimulationStateOut:
    state = await get_or_create_state(db)
    state.running = False
    touch(state)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)


@router.post("/step", response_model=SimulationStateOut)
async def step(
    _current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> SimulationStateOut:
    """Advance exactly one tick, regardless of whether the clock is playing —
    useful for walking through a demo one step at a time."""
    await advance_one_tick(db, settings)
    state = await get_or_create_state(db)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)


@router.post("/reset", response_model=SimulationStateOut)
async def reset(
    _current_user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    body: PlayRequest = PlayRequest(),  # noqa: B008 -- immutable request body, never mutated
) -> SimulationStateOut:
    """Wipe every tick's history and every household's battery back to its
    starting charge — a fresh day, optionally under a different scenario."""
    await db.execute(delete(MeterReading))
    await db.execute(delete(TradeRecord))
    await db.execute(delete(CurtailmentRecord))
    await db.execute(delete(LedgerEntryRecord))
    await db.execute(update(Household).values(battery_soc=0.5))

    state = await get_or_create_state(db)
    state.tick_index = 0
    state.running = False
    if body.scenario is not None:
        state.scenario = body.scenario.value
    if body.seconds_per_tick is not None:
        state.seconds_per_tick = body.seconds_per_tick
    touch(state)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)
