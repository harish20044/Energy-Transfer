"""Wire contract for a household's own profile."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HouseholdPublic(BaseModel):
    """A household's own configuration — never anyone else's."""

    model_config = {"from_attributes": True}

    id: str
    display_name: str
    member_count: int
    solar_capacity_kwp: float
    battery_capacity_kwh: float
    battery_max_charge_kw: float
    battery_max_discharge_kw: float
    evening_reserve: float


class EveningReserveUpdate(BaseModel):
    """The one setting a household can change about itself."""

    evening_reserve: float = Field(ge=0.0, le=1.0)
