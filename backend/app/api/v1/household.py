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

from app.api.deps import CurrentUserDep, DbDep
from app.models.household import Household
from app.models.simulation import LedgerEntryRecord, MeterReading, TradeRecord
from app.schemas.household import EveningReserveUpdate, HouseholdPublic
from app.schemas.simulation import HouseholdBalanceOut, MeterReadingOut, TradeOut

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
