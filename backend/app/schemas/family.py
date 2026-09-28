"""Wire contract for a household's family composition and live room status."""

from __future__ import annotations

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
    role: str
    room: int | None
    home_now: bool


class RoomStatusOut(BaseModel):
    room: int
    occupied: bool
    ac_intensity: float


class FamilyOut(BaseModel):
    house: HouseDesignOut
    members: list[FamilyMemberOut]
    rooms: list[RoomStatusOut]
