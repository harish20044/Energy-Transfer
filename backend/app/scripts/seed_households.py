"""Seed the 10 demo households and their logins.

Idempotent: safe to re-run — an existing household or user is updated in
place rather than duplicated. Household ids ("h1".."h10") match the ids
`app.domain.grid.network.default_feeder` already expects, so nothing needs
translating before the domain engine can use these rows.

Placeholder names and emails throughout. When the real 10 household names
arrive, only the `HOUSEHOLDS` table below needs editing — ids, credentials
and every downstream relationship stay the same.

Run inside the backend container:
    docker exec energy-backend python -m app.scripts.seed_households
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.security import hash_password
from app.models.household import Household
from app.models.user import User, UserRole


@dataclass(frozen=True, slots=True)
class HouseholdSeed:
    id: str
    display_name: str
    email: str
    member_count: int
    solar_capacity_kwp: float
    battery_capacity_kwh: float
    battery_max_charge_kw: float
    battery_max_discharge_kw: float


def _password_for(household_id: str) -> str:
    """A distinct, guessable-only-if-you-have-the-list demo password per
    household — never reused across households, so one leaking doesn't hand
    over the rest."""
    return f"{household_id}-Energy2026"


HOUSEHOLDS: tuple[HouseholdSeed, ...] = (
    HouseholdSeed("h1", "House 1", "house1@example.com", 4, 5.0, 10.0, 3.0, 3.0),
    HouseholdSeed("h2", "House 2", "house2@example.com", 3, 0.0, 0.0, 0.0, 0.0),
    HouseholdSeed("h3", "House 3", "house3@example.com", 5, 6.0, 12.0, 4.0, 4.0),
    HouseholdSeed("h4", "House 4", "house4@example.com", 2, 3.0, 6.0, 2.0, 2.0),
    HouseholdSeed("h5", "House 5", "house5@example.com", 6, 0.0, 0.0, 0.0, 0.0),
    HouseholdSeed("h6", "House 6", "house6@example.com", 4, 4.0, 8.0, 3.0, 3.0),
    HouseholdSeed("h7", "House 7", "house7@example.com", 3, 5.0, 10.0, 3.0, 3.0),
    HouseholdSeed("h8", "House 8", "house8@example.com", 5, 0.0, 0.0, 0.0, 0.0),
    HouseholdSeed("h9", "House 9", "house9@example.com", 2, 4.0, 8.0, 2.5, 2.5),
    HouseholdSeed("h10", "House 10", "house10@example.com", 4, 6.0, 12.0, 4.0, 4.0),
)


async def seed() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        for entry in HOUSEHOLDS:
            household = await session.get(Household, entry.id)
            if household is None:
                household = Household(id=entry.id)
                session.add(household)
            household.display_name = entry.display_name
            household.member_count = entry.member_count
            household.solar_capacity_kwp = entry.solar_capacity_kwp
            household.battery_capacity_kwh = entry.battery_capacity_kwh
            household.battery_max_charge_kw = entry.battery_max_charge_kw
            household.battery_max_discharge_kw = entry.battery_max_discharge_kw

            user = await session.scalar(select(User).where(User.email == entry.email))
            if user is None:
                user = User(email=entry.email, role=UserRole.HOUSEHOLD)
                session.add(user)
            user.display_name = entry.display_name
            user.household_id = entry.id
            user.hashed_password = hash_password(_password_for(entry.id))
            user.is_active = True

        await session.commit()

    print(f"Seeded {len(HOUSEHOLDS)} households.\n")  # noqa: T201
    print(f"{'Household':<10} {'Email':<22} {'Password':<20} {'Members'}")  # noqa: T201
    for entry in HOUSEHOLDS:
        print(  # noqa: T201
            f"{entry.display_name:<10} {entry.email:<22} "
            f"{_password_for(entry.id):<20} {entry.member_count}"
        )


if __name__ == "__main__":
    asyncio.run(seed())
