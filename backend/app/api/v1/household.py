"""A household's view of itself — and only itself.

Every route here takes its household id from the caller's own JWT
(`current_user.household_id`), never from a path or query parameter. There is
no `GET /households/{id}` in this API: accepting an id at all would make
isolation a bug waiting to happen (a client swapping ids in a URL) rather
than a structural impossibility.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.engine.runner import get_or_create_state
from app.models.household import Household
from app.models.simulation import LedgerEntryRecord, MeterReading, TradeRecord
from app.schemas.family import FamilyMemberOut, FamilyOut, HouseDesignOut, RoomStatusOut
from app.schemas.household import EveningReserveUpdate, HouseholdPublic
from app.schemas.simulation import HouseholdBalanceOut, MeterReadingOut, TradeOut
from app.simulator.family import (
    AC_UNITS,
    BEDROOMS,
    HALLS,
    WASHROOMS,
    generate_family,
    snapshot_occupancy,
)
from app.simulator.profiles import hour_of_day, is_weekend
from app.simulator.scenarios import Scenario, profile_for

router = APIRouter(prefix="/households", tags=["households"])


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
    """Change the one dial a household actually controls — read by the
    battery policy on every tick, not decorative."""
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
    """This household's own meter history, most recent tick first."""
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
    limit: int = Query(default=50, ge=1, le=1000),
) -> list[TradeRecord]:
    """Every settled trade this household was a party to, either side."""
    household = await _own_household(current_user, db)
    rows = await db.scalars(
        select(TradeRecord)
        .where(
            or_(
                TradeRecord.buyer_household_id == household.id,
                TradeRecord.seller_household_id == household.id,
            )
        )
        .order_by(TradeRecord.tick_index.desc())
        .limit(limit)
    )
    return list(rows)


@router.get("/me/balance", response_model=HouseholdBalanceOut)
async def read_own_balance(current_user: CurrentUserDep, db: DbDep) -> HouseholdBalanceOut:
    """Net settlement position from the hash-chained ledger: positive means
    this household has been paid more than it has spent."""
    household = await _own_household(current_user, db)

    sold = await db.execute(
        select(
            func.coalesce(func.sum(LedgerEntryRecord.total_amount), 0.0),
            func.coalesce(func.sum(LedgerEntryRecord.kwh), 0.0),
        ).where(LedgerEntryRecord.seller_household_id == household.id)
    )
    sold_amount, sold_kwh = sold.one()

    bought = await db.execute(
        select(
            func.coalesce(func.sum(LedgerEntryRecord.total_amount), 0.0),
            func.coalesce(func.sum(LedgerEntryRecord.kwh), 0.0),
        ).where(LedgerEntryRecord.buyer_household_id == household.id)
    )
    bought_amount, bought_kwh = bought.one()

    return HouseholdBalanceOut(
        household_id=household.id,
        net_balance=sold_amount - bought_amount,
        total_sold_kwh=sold_kwh,
        total_bought_kwh=bought_kwh,
    )


@router.get("/me/family", response_model=FamilyOut)
async def read_own_family(
    current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> FamilyOut:
    """This household's own family and live room occupancy — who's actually
    home right now, and which of the house's 4 bedroom ACs that's running."""
    household = await _own_household(current_user, db)
    state = await get_or_create_state(db)

    hour = hour_of_day(state.tick_index, tick_minutes=settings.market_tick_minutes)
    weekend = is_weekend(state.tick_index, tick_minutes=settings.market_tick_minutes)
    scenario = Scenario(state.scenario)

    family = generate_family(household.id, household.member_count, settings.sim_seed)
    snapshot = snapshot_occupancy(family, hour, weekend, profile_for(scenario).demand_factor)

    return FamilyOut(
        house=HouseDesignOut(
            bedrooms=BEDROOMS, washrooms=WASHROOMS, halls=HALLS, ac_units=AC_UNITS
        ),
        members=[
            FamilyMemberOut(
                index=member.index,
                age=member.age,
                role=member.role.value,
                room=member.room,
                home_now=snapshot.home_now[member.index],
            )
            for member in family.members
        ],
        rooms=[
            RoomStatusOut(room=room.room, occupied=room.occupied, ac_intensity=room.ac_intensity)
            for room in snapshot.rooms
        ],
    )
