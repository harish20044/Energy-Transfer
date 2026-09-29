"""The planning session: set it up, let the agents trade the hours ahead,
then deliver them one hour at a time.

Any signed-in account may drive the session — there is one feeder and one
session for the whole demo. Everything returned here is feeder-wide
(aggregates, or the market's own public order book and agents' public
offers); a household's private forecast and money live under
`/households/me/session`.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.core.config import Settings
from app.engine.session import (
    SessionError,
    advance_hour,
    get_or_create_state,
    household_order,
    plan_session,
    reset_session,
)
from app.models.agent import AgentDecisionRecord
from app.models.household import Household
from app.models.session import SessionForecast, SessionHousehold, SessionPosition
from app.models.simulation import MeterReading, NegotiationOfferRecord, SimulationState, TradeRecord
from app.schemas.session import (
    AgentMessageOut,
    EbFlowOut,
    OfferOut,
    PowerCut,
    RoundOut,
    SessionConfigIn,
    SessionHouseholdOut,
    SessionOut,
    SlotMarketOut,
    SlotSummaryOut,
    TradeOut,
)
from app.schemas.simulation import Sky, WeatherOut
from app.simulator.scenarios import Scenario
from app.simulator.weather import DayWeather, day_weather

router = APIRouter(prefix="/session", tags=["session"])


def sky_of(weather: DayWeather) -> Sky:
    if weather.rainy:
        return "rain"
    if weather.clearness >= 0.85:
        return "clear"
    if weather.clearness >= 0.6:
        return "partly cloudy"
    return "overcast"


def clock_hours(state: SimulationState, tick_minutes: int) -> float:
    return state.start_hour + state.tick_index * tick_minutes / 60.0


async def session_out(db: DbDep, state: SimulationState, settings: Settings) -> SessionOut:
    tick_minutes = settings.market_tick_minutes
    clock = clock_hours(state, tick_minutes)
    day = state.sim_date + timedelta(days=int(clock // 24))
    weather = day_weather(day, Scenario(state.scenario), settings.sim_seed, tick_minutes)
    slot_in_day = int((clock % 24) * 60 // tick_minutes) % len(weather.temperature_c)
    what_ifs = state.what_ifs or {}
    names = {h.id: h.display_name for h in (await db.scalars(select(Household))).all()}
    setups = sorted(
        (await db.scalars(select(SessionHousehold))).all(),
        key=lambda s: household_order(s.household_id),
    )
    return SessionOut(
        status=state.status,  # type: ignore[arg-type]
        sim_date=state.sim_date,
        start_hour=state.start_hour,
        horizon_hours=state.horizon_hours,
        scenario=Scenario(state.scenario),
        tick_minutes=tick_minutes,
        hours_delivered=state.tick_index // (60 // tick_minutes),
        clock_hours=clock,
        retail_tariff=what_ifs.get("retail_tariff", settings.retail_tariff),
        feed_in_tariff=what_ifs.get("feed_in_tariff", settings.feed_in_tariff),
        peak_surcharge_pct=what_ifs.get("peak_surcharge_pct", 0.0),
        power_cut=PowerCut(**what_ifs["power_cut"]) if what_ifs.get("power_cut") else None,
        weather=WeatherOut(
            date=day,
            sky=sky_of(weather),
            t_max_c=weather.t_max_c,
            t_min_c=weather.t_min_c,
            temperature_now_c=float(weather.temperature_c[slot_in_day]),
            sunrise_h=weather.sunrise_h,
            sunset_h=weather.sunset_h,
        ),
        households=[
            SessionHouseholdOut(
                household_id=s.household_id,
                display_name=names.get(s.household_id, s.household_id),
                start_soc=s.start_soc,
                guests=s.guests,
                away_from=s.away_from,
                away_to=s.away_to,
                work_from_home=s.work_from_home,
                panel_derate=s.panel_derate,
                battery_capacity_kwh=s.battery_capacity_kwh,
            )
            for s in setups
        ],
    )


@router.get("", response_model=SessionOut)
async def read_session(_user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> SessionOut:
    state = await get_or_create_state(db)
    await db.commit()
    return await session_out(db, state, settings)


@router.post("/plan", response_model=SessionOut)
async def plan(
    body: SessionConfigIn, _user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> SessionOut:
    """Forecast every household for the hours ahead and let their agents
    trade every hourly slot with each other and the EB."""
    try:
        state = await plan_session(db, settings, body)
    except SessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return await session_out(db, state, settings)


@router.post("/next-hour", response_model=SessionOut)
async def next_hour(_user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> SessionOut:
    """Deliver the next hour against what really happens."""
    try:
        state = await advance_hour(db, settings)
    except SessionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return await session_out(db, state, settings)


@router.post("/reset", response_model=SessionOut)
async def reset(_user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> SessionOut:
    """Back to setup. Agents keep what they've learned."""
    state = await reset_session(db)
    return await session_out(db, state, settings)


@router.get("/overview", response_model=list[SlotSummaryOut])
async def overview(_user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> list[SlotSummaryOut]:
    """The whole feeder, slot by slot: forecast need and spare, what traded
    between neighbours and with the EB, and — once delivered — what really
    happened."""
    state = await get_or_create_state(db)
    await db.commit()
    if state.status == "setup":
        return []
    ticks_per_hour = 60 // settings.market_tick_minutes
    forecasts = (await db.scalars(select(SessionForecast))).all()
    positions = (await db.scalars(select(SessionPosition))).all()
    trades = (await db.scalars(select(TradeRecord))).all()
    readings = (await db.scalars(select(MeterReading))).all()
    delivered_hours = state.tick_index // ticks_per_hour

    summaries: list[SlotSummaryOut] = []
    for slot in range(state.horizon_hours):
        slot_forecasts = [f for f in forecasts if f.slot == slot]
        slot_positions = [p for p in positions if p.slot == slot]
        slot_trades = [t for t in trades if t.tick_index == slot]
        slot_readings = [r for r in readings if r.tick_index // ticks_per_hour == slot]
        if not slot_forecasts or not slot_positions:
            continue
        p2p = sum(t.kwh for t in slot_trades)
        hours = settings.market_tick_minutes / 60.0
        summaries.append(
            SlotSummaryOut(
                slot=slot,
                day=slot_forecasts[0].day,
                hour_of_day=slot_forecasts[0].hour_of_day,
                retail_tariff=slot_positions[0].retail_tariff,
                feed_in_tariff=slot_positions[0].feed_in_tariff,
                eb_available=slot_positions[0].eb_available,
                forecast_need_kwh=sum(
                    max(0.0, f.consumption_p50 - f.generation_p50) for f in slot_forecasts
                ),
                forecast_spare_kwh=sum(
                    max(0.0, f.generation_p50 - f.consumption_p50) for f in slot_forecasts
                ),
                p2p_kwh=p2p,
                p2p_avg_price=(
                    sum(t.kwh * t.price_per_kwh for t in slot_trades) / p2p if p2p > 0 else None
                ),
                eb_bought_kwh=sum(p.eb_bought_kwh for p in slot_positions),
                eb_sold_kwh=sum(p.eb_sold_kwh for p in slot_positions),
                unserved_kwh=sum(p.unserved_kwh for p in slot_positions),
                delivered=slot < delivered_hours,
                actual_consumption_kwh=(
                    sum(r.consumption_kw for r in slot_readings) * hours if slot_readings else None
                ),
                actual_generation_kwh=(
                    sum(r.generation_kw for r in slot_readings) * hours if slot_readings else None
                ),
            )
        )
    return summaries


def agent_message(record: AgentDecisionRecord, name: str) -> AgentMessageOut:
    return AgentMessageOut(
        household_id=record.household_id,
        display_name=name,
        strategy=record.strategy,
        side=record.side,
        firm=record.firm,
        quantity_kwh=record.quantity_kwh,
        limit_price=record.limit_price,
        opening_price=record.opening_price,
        message=record.message,
        outcome=record.outcome,
        reasons=[str(r) for r in record.reasons],
    )


@router.get("/market", response_model=SlotMarketOut)
async def market(_user: CurrentUserDep, db: DbDep, slot: int = Query(ge=0, le=23)) -> SlotMarketOut:
    """One slot's negotiation, round by round, with every agent's offer and
    what it said — the market's public order book."""
    positions = (
        await db.scalars(select(SessionPosition).where(SessionPosition.slot == slot))
    ).all()
    if not positions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such slot")
    offers = (
        await db.scalars(
            select(NegotiationOfferRecord).where(NegotiationOfferRecord.tick_index == slot)
        )
    ).all()
    trades = (await db.scalars(select(TradeRecord).where(TradeRecord.tick_index == slot))).all()
    decisions = (
        await db.scalars(select(AgentDecisionRecord).where(AgentDecisionRecord.slot == slot))
    ).all()
    names = {h.id: h.display_name for h in (await db.scalars(select(Household))).all()}
    first = positions[0]
    rounds = sorted({o.round_index for o in offers})
    return SlotMarketOut(
        slot=slot,
        hour_of_day=decisions[0].hour_of_day if decisions else 0,
        retail_tariff=first.retail_tariff,
        feed_in_tariff=first.feed_in_tariff,
        eb_available=first.eb_available,
        rounds=[
            RoundOut(
                round_index=r,
                asks=[
                    OfferOut(household_id=o.household_id, side=o.side, price=o.price, kwh=o.kwh)
                    for o in offers
                    if o.round_index == r and o.side == "ask"
                ],
                bids=[
                    OfferOut(household_id=o.household_id, side=o.side, price=o.price, kwh=o.kwh)
                    for o in offers
                    if o.round_index == r and o.side == "bid"
                ],
                trades=[
                    TradeOut(
                        buyer_household_id=t.buyer_household_id,
                        seller_household_id=t.seller_household_id,
                        kwh=t.kwh,
                        price_per_kwh=t.price_per_kwh,
                        round_index=t.round_index,
                    )
                    for t in trades
                    if t.round_index == r
                ],
            )
            for r in rounds
        ],
        eb_flows=[
            *(
                EbFlowOut(
                    household_id=p.household_id,
                    side="bid",
                    kwh=p.eb_bought_kwh,
                    price=p.retail_tariff,
                )
                for p in positions
                if p.eb_bought_kwh > 1e-9
            ),
            *(
                EbFlowOut(
                    household_id=p.household_id,
                    side="ask",
                    kwh=p.eb_sold_kwh,
                    price=p.feed_in_tariff,
                )
                for p in positions
                if p.eb_sold_kwh > 1e-9
            ),
        ],
        agents=[
            agent_message(d, names.get(d.household_id, d.household_id))
            for d in sorted(decisions, key=lambda d: household_order(d.household_id))
        ],
    )
