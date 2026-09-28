"""A household's view of itself — and only itself.

Every route here takes its household id from the caller's own JWT
(`current_user.household_id`), never from a path or query parameter. There is
no `GET /households/{id}` in this API: accepting an id at all would make
isolation a bug waiting to happen (a client swapping ids in a URL) rather
than a structural impossibility.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, DbDep
from app.models.household import Household
from app.schemas.household import EveningReserveUpdate, HouseholdPublic

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
