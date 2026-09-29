"""Wire contracts for the shared simulation clock and its results."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Sky = Literal["clear", "partly cloudy", "overcast", "rain"]


class WeatherOut(BaseModel):
    """The simulated day's Chennai weather, as a household would see it."""

    date: date
    sky: Sky
    t_max_c: float
    t_min_c: float
    temperature_now_c: float
    sunrise_h: float
    sunset_h: float


class MeterReadingOut(BaseModel):
    model_config = {"from_attributes": True}

    tick_index: int
    consumption_kw: float
    generation_kw: float
    battery_soc: float
    battery_action: str
    grid_kwh: float
    created_at: datetime


class TradeOut(BaseModel):
    model_config = {"from_attributes": True}

    tick_index: int
    round_index: int
    buyer_household_id: str
    seller_household_id: str
    kwh: float
    price_per_kwh: float
    created_at: datetime


class CurtailmentOut(BaseModel):
    model_config = {"from_attributes": True}

    tick_index: int
    buyer_household_id: str
    seller_household_id: str
    curtailed_kwh: float
    reason: str
    created_at: datetime


class FeederLineOut(BaseModel):
    id: str
    from_bus: str
    to_bus: str
    thermal_limit_kw: float


class FeederOut(BaseModel):
    household_ids: list[str]
    lines: list[FeederLineOut]
