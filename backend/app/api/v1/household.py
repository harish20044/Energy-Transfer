"""A household's view of itself — and only itself.

Every route here takes its household id from the caller's own JWT
(`current_user.household_id`), never from a path or query parameter. There is
no `GET /households/{id}` in this API: accepting an id at all would make
isolation a bug waiting to happen (a client swapping ids in a URL) rather
than a structural impossibility.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.api.v1.session import agent_message, clock_hours
from app.engine.session import get_or_create_state, household_day, override_of
from app.engine.statement import statements
from app.forecasting.predict import MODEL_LIGHTGBM, MODEL_SEASONAL_NAIVE, get_models
from app.models.agent import AgentDecisionRecord
from app.models.household import Household
from app.models.session import SessionForecast, SessionHousehold, SessionPosition
from app.models.simulation import MeterReading, TradeRecord
from app.schemas.family import FamilyMemberOut, FamilyOut, HouseDesignOut, RoomStatusOut
from app.schemas.household import EveningReserveUpdate, HouseholdPublic
from app.schemas.session import HourForecastOut, OwnSessionOut, OwnSlotOut
from app.schemas.simulation import MeterReadingOut, TradeOut
from app.simulator.family import AC_UNITS, BEDROOMS, HALLS, WASHROOMS, HouseholdOverride, Status
from app.simulator.household import AC_MAX_KW, AC_MIN_KW
from app.simulator.scenarios import Scenario

router = APIRouter(prefix="/households", tags=["households"])

_STATUS_LABEL = {Status.HOME: "home", Status.AWAY: "away", Status.ASLEEP: "asleep"}


async def _own_household(current_user: CurrentUserDep, db: AsyncSession) -> Household:
    if current_user.household_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This account is not linked to a household",
        )
    household = await db.get(Household, current_user.household_id)
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    return household


@router.get("/me", response_model=HouseholdPublic)
async def read_own_household(current_user: CurrentUserDep, db: DbDep) -> Household:
    """The signed-in household's own configuration."""
    return await _own_household(current_user, db)


@router.patch("/me/evening-reserve", response_model=HouseholdPublic)
async def update_evening_reserve(
    body: EveningReserveUpdate, current_user: CurrentUserDep, db: DbDep
) -> Household:
    """Change the reserve: the battery level the household's agent never
    sells stored charge below. Takes effect from the next planned session."""
    household = await _own_household(current_user, db)
    household.evening_reserve = body.evening_reserve
    await db.flush()
    return household


@router.get("/me/readings", response_model=list[MeterReadingOut])
async def read_own_readings(
    current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=96, ge=1, le=1000),
) -> list[MeterReading]:
    """This household's delivered meter intervals this session, most recent
    first."""
    household = await _own_household(current_user, db)
    rows = await db.scalars(
        select(MeterReading)
        .where(MeterReading.household_id == household.id)
        .order_by(MeterReading.tick_index.desc())
        .limit(limit)
    )
    return list(rows)


@router.get("/me/trades", response_model=list[TradeOut])
async def read_own_trades(
    current_user: CurrentUserDep,
    db: DbDep,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[TradeRecord]:
    """Every neighbour trade this household made this session, either side."""
    household = await _own_household(current_user, db)
    rows = await db.scalars(
        select(TradeRecord)
        .where(
            or_(
                TradeRecord.buyer_household_id == household.id,
                TradeRecord.seller_household_id == household.id,
            )
        )
        .order_by(TradeRecord.tick_index, TradeRecord.id)
        .limit(limit)
    )
    return list(rows)


@router.get("/me/family", response_model=FamilyOut)
async def read_own_family(
    current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> FamilyOut:
    """This household's family and what's happening in the house at the
    session's current moment — who's home, away or asleep, which bedroom ACs
    are running, and what every appliance group is drawing."""
    household = await _own_household(current_user, db)
    state = await get_or_create_state(db)
    tick_minutes = settings.market_tick_minutes
    clock = clock_hours(state, tick_minutes)
    if state.status == "complete":
        clock -= tick_minutes / 60.0  # the last delivered interval, not the one after
    setup = await db.get(SessionHousehold, household.id)
    override = override_of(setup) if setup else HouseholdOverride()
    day = state.sim_date + timedelta(days=int(clock // 24))
    hd = household_day(
        household,
        day,
        sim_date=state.sim_date,
        scenario=Scenario(state.scenario),
        override=override,
        seed=settings.sim_seed,
        tick_minutes=tick_minutes,
    )
    slot = int((clock % 24) * 60 // tick_minutes)
    family = hd.family
    statuses = [Status(int(hd.statuses[i, slot])) for i in range(len(family.members))]

    def room_occupied(room: int) -> bool:
        asleep_here = any(
            member.sleeping_room == room and statuses[i] is Status.ASLEEP
            for i, member in enumerate(family.members)
        )
        return asleep_here or float(hd.room_ac_kw[room - 1, slot]) > 0

    return FamilyOut(
        house=HouseDesignOut(
            bedrooms=BEDROOMS, washrooms=WASHROOMS, halls=HALLS, ac_units=AC_UNITS
        ),
        members=[
            FamilyMemberOut(
                index=member.index,
                age=member.age,
                role=member.role.value,
                occupation=member.occupation.value,
                room=member.room,
                status=_STATUS_LABEL[statuses[i]],  # type: ignore[arg-type]
                home_now=statuses[i] is not Status.AWAY,
            )
            for i, member in enumerate(family.members)
        ],
        rooms=[
            RoomStatusOut(
                room=room,
                occupied=room_occupied(room),
                ac_on=float(hd.room_ac_kw[room - 1, slot]) >= 0.5 * AC_MIN_KW,
                ac_kw=float(hd.room_ac_kw[room - 1, slot]),
                ac_intensity=min(1.0, float(hd.room_ac_kw[room - 1, slot]) / AC_MAX_KW),
            )
            for room in range(1, BEDROOMS + 1)
        ],
        appliance_kw={name: float(values[slot]) for name, values in hd.breakdown.items()},
    )


@router.get("/me/session", response_model=OwnSessionOut)
async def read_own_session(
    current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> OwnSessionOut:
    """This household's session, hour by hour: its forecast (P10/P50/P90),
    what its agent decided and said, what it traded with neighbours and the
    EB, what actually happened once delivered — and its money, planned and
    delivered, kept as separate earned and paid figures."""
    household = await _own_household(current_user, db)
    state = await get_or_create_state(db)
    tick_minutes = settings.market_tick_minutes
    ticks_per_hour = 60 // tick_minutes
    hours = tick_minutes / 60.0
    forecasts = {
        f.slot: f
        for f in (
            await db.scalars(
                select(SessionForecast).where(SessionForecast.household_id == household.id)
            )
        ).all()
    }
    positions = {
        p.slot: p
        for p in (
            await db.scalars(
                select(SessionPosition).where(SessionPosition.household_id == household.id)
            )
        ).all()
    }
    decisions = {
        d.slot: d
        for d in (
            await db.scalars(
                select(AgentDecisionRecord).where(AgentDecisionRecord.household_id == household.id)
            )
        ).all()
    }
    readings = (
        await db.scalars(select(MeterReading).where(MeterReading.household_id == household.id))
    ).all()
    delivered_hours = state.tick_index // ticks_per_hour

    slots: list[OwnSlotOut] = []
    for slot in sorted(forecasts):
        f, p = forecasts[slot], positions.get(slot)
        if p is None:
            continue
        in_slot = sorted(
            (r for r in readings if r.tick_index // ticks_per_hour == slot),
            key=lambda r: r.tick_index,
        )
        delivered = slot < delivered_hours and bool(in_slot)
        decision = decisions.get(slot)
        slots.append(
            OwnSlotOut(
                slot=slot,
                hour_of_day=f.hour_of_day,
                forecast=HourForecastOut(
                    slot=slot,
                    day=f.day,
                    hour_of_day=f.hour_of_day,
                    consumption_p10=f.consumption_p10,
                    consumption_p50=f.consumption_p50,
                    consumption_p90=f.consumption_p90,
                    generation_p10=f.generation_p10,
                    generation_p50=f.generation_p50,
                    generation_p90=f.generation_p90,
                ),
                p2p_sold_kwh=p.p2p_sold_kwh,
                p2p_bought_kwh=p.p2p_bought_kwh,
                eb_bought_kwh=p.eb_bought_kwh,
                eb_sold_kwh=p.eb_sold_kwh,
                retail_tariff=p.retail_tariff,
                feed_in_tariff=p.feed_in_tariff,
                eb_available=p.eb_available,
                decision=agent_message(decision, household.display_name) if decision else None,
                delivered=delivered,
                actual_consumption_kwh=sum(r.consumption_kw for r in in_slot) * hours
                if delivered
                else None,
                actual_generation_kwh=sum(r.generation_kw for r in in_slot) * hours
                if delivered
                else None,
                actual_eb_import_kwh=sum(max(0.0, r.grid_kwh) for r in in_slot)
                if delivered
                else None,
                actual_eb_export_kwh=sum(max(0.0, -r.grid_kwh) for r in in_slot)
                if delivered
                else None,
                actual_unserved_kwh=sum(r.unserved_kwh for r in in_slot) if delivered else None,
                battery_soc_end=in_slot[-1].battery_soc if delivered else None,
            )
        )

    planned, delivered_statement = await statements(db, state, household, tick_minutes=tick_minutes)
    return OwnSessionOut(
        household_id=household.id,
        model=MODEL_LIGHTGBM if get_models() else MODEL_SEASONAL_NAIVE,
        slots=slots,
        planned=planned,
        delivered=delivered_statement,
    )
