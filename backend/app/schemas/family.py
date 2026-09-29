"""Wire contract for a household's family composition and live room status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HouseDesignOut(BaseModel):
    """The physical layout every household in this simulation shares."""

    bedrooms: int
    washrooms: int
    halls: int
    ac_units: int


class FamilyMemberOut(BaseModel):
    index: int
    age: int
    role: str  # parent | child | grandparent | guest
    occupation: str
    room: int | None
    status: Literal["home", "away", "asleep"]
    home_now: bool


class RoomStatusOut(BaseModel):
    room: int
    occupied: bool
    ac_on: bool
    ac_kw: float
    ac_intensity: float


class FamilyOut(BaseModel):
    house: HouseDesignOut
    members: list[FamilyMemberOut]
    rooms: list[RoomStatusOut]
    # What the house is drawing right now, by appliance group, kW.
    appliance_kw: dict[str, float]
