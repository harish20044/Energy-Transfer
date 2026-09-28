"""Control surface for the one shared simulation clock every household's
feeder runs on.

Any signed-in account may drive play/pause/step/reset — there is exactly one
feeder and one clock for the whole demo, not one per household, so this is
shared infrastructure rather than something that needs household-scoped
isolation the way `/households/me` does.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import delete, select, update

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.domain.grid.network import default_feeder
from app.engine.runner import advance_one_tick, get_or_create_state, touch
from app.models.household import Household
from app.models.simulation import (
    CurtailmentRecord,
    LedgerEntryRecord,
    MeterReading,
    NegotiationOfferRecord,
    SimulationState,
    TradeRecord,
)
from app.schemas.simulation import (
    CurtailmentOut,
    FeederLineOut,
    FeederOut,
    NegotiationOfferOut,
    NegotiationRoundOut,
    NegotiationTickOut,
    PlayRequest,
    SimulationStateOut,
    TradeOut,
)
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
        tick_minutes=tick_minutes,
        updated_at=state.updated_at,
    )


@router.get("/state", response_model=SimulationStateOut)
async def read_state(
    _current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> SimulationStateOut:
    state = await get_or_create_state(db)
    await db.commit()
    return _to_out(state, tick_minutes=settings.market_tick_minutes)


@router.get("/negotiation", response_model=NegotiationTickOut)
async def read_negotiation(
    _current_user: CurrentUserDep,
    db: DbDep,
    tick_index: int = Query(ge=0),
) -> NegotiationTickOut:
    """The round-by-round order book for one tick — every offer and every
    trade, in the order they actually happened. This is market-wide
    information, the same as an order book on any real exchange, not a
    single household's private data, so any signed-in account can read it."""
    offers = (
        await db.scalars(
            select(NegotiationOfferRecord)
            .where(NegotiationOfferRecord.tick_index == tick_index)
            .order_by(NegotiationOfferRecord.round_index)
        )
    ).all()
    trades = (
        await db.scalars(
            select(TradeRecord)
            .where(TradeRecord.tick_index == tick_index)
            .order_by(TradeRecord.round_index)
        )
    ).all()

    round_indices = sorted({offer.round_index for offer in offers})
    rounds = [
        NegotiationRoundOut(
            round_index=round_index,
            asks=[
                NegotiationOfferOut.model_validate(o)
                for o in offers
                if o.round_index == round_index and o.side == "ask"
            ],
            bids=[
                NegotiationOfferOut.model_validate(o)
                for o in offers
                if o.round_index == round_index and o.side == "bid"
            ],
            trades=[
                TradeOut.model_validate(t) for t in trades if t.round_index == round_index
            ],
        )
        for round_index in round_indices
    ]

    return NegotiationTickOut(tick_index=tick_index, rounds=rounds)


@router.get("/trades", response_model=list[TradeOut])
async def read_recent_trades(
    _current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=1000),
) -> list[TradeRecord]:
    """Every household's trades, most recent first — the same order-book
    transparency a real exchange's public trade tape has."""
    rows = await db.scalars(
        select(TradeRecord).order_by(TradeRecord.id.desc()).limit(limit)
    )
    return list(rows)


@router.get("/curtailments", response_model=list[CurtailmentOut])
async def read_recent_curtailments(
    _current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=1000),
) -> list[CurtailmentRecord]:
    """Every trade the grid safety layer has had to cut back, most recent
    first — the evidence for objective O4."""
    rows = await db.scalars(
        select(CurtailmentRecord).order_by(CurtailmentRecord.id.desc()).limit(limit)
    )
    return list(rows)


@router.get("/network", response_model=FeederOut)
async def read_network(_current_user: CurrentUserDep, db: DbDep) -> FeederOut:
    """The feeder topology every household trades over — static for the life
    of the demo, so the frontend only needs to fetch it once."""
    households = await db.scalars(select(Household).order_by(Household.id))
    household_ids = sorted((h.id for h in households), key=lambda hid: int(hid[1:]))
    network = default_feeder(household_ids)
    return FeederOut(
        household_ids=household_ids,
        lines=[
            FeederLineOut(
                id=line.id,
                from_bus=line.from_bus,
                to_bus=line.to_bus,
                thermal_limit_kw=line.thermal_limit_kw,
            )
            for line in network.lines
        ],
    )


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
    await db.execute(delete(NegotiationOfferRecord))
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
