"""Wire contract for a household's next 1-4 hour buy/sell forecast."""

from __future__ import annotations

from pydantic import BaseModel


class HourForecastOut(BaseModel):
    horizon_hours: int
    hour_of_day: float
    consumption_p10: float
    consumption_p50: float
    consumption_p90: float
    generation_p10: float
    generation_p50: float
    generation_p90: float
    net_p50_kw: float
    recommended_action: str
    projected_net_for_market_kw: float


class ForecastOut(BaseModel):
    household_id: str
    model: str
    hours: list[HourForecastOut]
