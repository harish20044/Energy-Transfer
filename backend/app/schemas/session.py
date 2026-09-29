"""Wire contracts for planning sessions: the user's setup and what-ifs, and
what the forecast, the market and the delivered hours produced."""

from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.simulation import WeatherOut
from app.simulator.scenarios import Scenario

SessionStatus = Literal["setup", "planned", "playing", "complete"]
Horizon = Literal[4, 8, 12, 24]
PEAK_START_HOUR = 18
PEAK_END_HOUR = 22


class HouseholdWhatIf(BaseModel):
    household_id: str
    guests: int = Field(default=0, ge=0, le=4)
    # Family out from/to, as clock hours on the session's first day; `away_to`
    # past 24 runs into the next morning (e.g. 20 -> 26 = 8 pm to 2 am).
    away_from: float | None = Field(default=None, ge=0, lt=24)
    away_to: float | None = Field(default=None, gt=0, le=48)
    work_from_home: bool = False
    # 1.0 = no panels at all (a tenant, a shaded roof).
    panel_derate: float = Field(default=0.0, ge=0.0, le=1.0)
    # Battery size for the session: 0 = no battery, or a different size.
    battery_capacity_kwh: float | None = Field(default=None, ge=0.0, le=20.0)
    battery_start_soc: float | None = Field(default=None, ge=0.05, le=1.0)

    @model_validator(mode="after")
    def _away_window(self) -> Self:
        if (self.away_from is None) != (self.away_to is None):
            msg = "away_from and away_to must be given together"
            raise ValueError(msg)
        if (
            self.away_from is not None
            and self.away_to is not None
            and self.away_to <= self.away_from
        ):
            msg = "away_to must be after away_from"
            raise ValueError(msg)
        return self


class PowerCut(BaseModel):
    """An EB outage, in clock hours from midnight of the session's first day
    (may run past 24 into the next day)."""

    start_hour: int = Field(ge=0, le=47)
    end_hour: int = Field(ge=1, le=48)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end_hour <= self.start_hour:
            msg = "end_hour must be after start_hour"
            raise ValueError(msg)
        return self


class TariffWhatIf(BaseModel):
    retail_tariff: float | None = Field(default=None, ge=1.0, le=30.0)
    feed_in_tariff: float | None = Field(default=None, ge=0.0, le=20.0)
    # Extra charge on EB imports during the evening peak (6-10 pm), percent.
    peak_surcharge_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class SessionConfigIn(BaseModel):
    sim_date: date = Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))
    start_hour: int = Field(ge=0, le=23)
    horizon_hours: Horizon = 12
    scenario: Scenario = Scenario.AUTO
    households: list[HouseholdWhatIf] = Field(default_factory=list)
    power_cut: PowerCut | None = None
    tariffs: TariffWhatIf = Field(default_factory=TariffWhatIf)


class SessionHouseholdOut(BaseModel):
    household_id: str
    display_name: str
    start_soc: float
    guests: int
    away_from: float | None
    away_to: float | None
    work_from_home: bool
    panel_derate: float
    battery_capacity_kwh: float


class SessionOut(BaseModel):
    status: SessionStatus
    sim_date: date
    start_hour: int
    horizon_hours: int
    scenario: Scenario
    tick_minutes: int
    hours_delivered: int
    # Clock time the session has reached, hours from midnight of `sim_date`.
    clock_hours: float
    retail_tariff: float
    feed_in_tariff: float
    peak_surcharge_pct: float
    power_cut: PowerCut | None
    weather: WeatherOut
    households: list[SessionHouseholdOut]


class SlotSummaryOut(BaseModel):
    """The whole feeder in one slot — aggregates only, no household's own
    forecast is exposed."""

    slot: int
    day: date
    hour_of_day: int
    retail_tariff: float
    feed_in_tariff: float
    eb_available: bool
    forecast_need_kwh: float  # summed P50 shortfall before trading
    forecast_spare_kwh: float  # summed P50 surplus before trading
    p2p_kwh: float
    p2p_avg_price: float | None
    eb_bought_kwh: float
    eb_sold_kwh: float
    unserved_kwh: float
    delivered: bool
    actual_consumption_kwh: float | None
    actual_generation_kwh: float | None


class AgentMessageOut(BaseModel):
    household_id: str
    display_name: str
    strategy: str
    side: str
    firm: bool
    quantity_kwh: float
    limit_price: float | None
    opening_price: float | None
    message: str
    outcome: str
    reasons: list[str]


class OfferOut(BaseModel):
    household_id: str
    side: str
    price: float
    kwh: float


class TradeOut(BaseModel):
    buyer_household_id: str
    seller_household_id: str
    kwh: float
    price_per_kwh: float
    round_index: int


class RoundOut(BaseModel):
    round_index: int
    asks: list[OfferOut]
    bids: list[OfferOut]
    trades: list[TradeOut]


class EbFlowOut(BaseModel):
    household_id: str
    side: str  # "bid" = bought from the EB, "ask" = sold to the EB
    kwh: float
    price: float


class SlotMarketOut(BaseModel):
    slot: int
    hour_of_day: int
    retail_tariff: float
    feed_in_tariff: float
    eb_available: bool
    rounds: list[RoundOut]
    eb_flows: list[EbFlowOut]
    agents: list[AgentMessageOut]


class HourForecastOut(BaseModel):
    slot: int
    day: date
    hour_of_day: int
    consumption_p10: float
    consumption_p50: float
    consumption_p90: float
    generation_p10: float
    generation_p50: float
    generation_p90: float


class OwnSlotOut(BaseModel):
    slot: int
    hour_of_day: int
    forecast: HourForecastOut
    p2p_sold_kwh: float
    p2p_bought_kwh: float
    eb_bought_kwh: float
    eb_sold_kwh: float
    retail_tariff: float
    feed_in_tariff: float
    eb_available: bool
    decision: AgentMessageOut | None
    delivered: bool
    actual_consumption_kwh: float | None
    actual_generation_kwh: float | None
    actual_eb_import_kwh: float | None
    actual_eb_export_kwh: float | None
    actual_unserved_kwh: float | None
    battery_soc_end: float | None


class StatementOut(BaseModel):
    """Money kept apart, never netted into one signed balance: what was
    earned and what was paid, each positive, plus what the same hours would
    have cost dealing with the EB alone."""

    basis: Literal["planned", "delivered"]
    hours: int
    earned_from_neighbours_inr: float
    paid_to_neighbours_inr: float
    paid_to_eb_inr: float
    earned_from_eb_inr: float
    # The same hours dealing with the EB alone (battery still used for self-
    # consumption, no neighbours): what it would have paid and earned.
    eb_only_paid_inr: float
    eb_only_earned_inr: float
    # How much better off trading with neighbours left the household (can be
    # below zero only if forecast errors cost more than the trades saved).
    saved_vs_eb_only_inr: float
    units_sold_to_neighbours: float
    units_bought_from_neighbours: float
    units_from_eb: float
    units_to_eb: float
    units_unserved: float


class OwnSessionOut(BaseModel):
    household_id: str
    model: str
    slots: list[OwnSlotOut]
    planned: StatementOut | None
    delivered: StatementOut | None
