"""Wire contracts for the shared simulation clock and its results."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.simulator.scenarios import Scenario


class SimulationStateOut(BaseModel):
    model_config = {"from_attributes": True}

    tick_index: int
    running: bool
    scenario: Scenario
    seconds_per_tick: float
    simulated_day: int
    simulated_hour: float
    updated_at: datetime


class PlayRequest(BaseModel):
    scenario: Scenario | None = None
    seconds_per_tick: float | None = Field(default=None, gt=0, le=60)


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
    buyer_household_id: str
    seller_household_id: str
    kwh: float
    price_per_kwh: float
    created_at: datetime


class HouseholdBalanceOut(BaseModel):
    household_id: str
    net_balance: float
    total_sold_kwh: float
    total_bought_kwh: float
