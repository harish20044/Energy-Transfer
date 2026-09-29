"""Live inference: forecast one household's next 1-24 hours from the moment a
planning session starts, under the session's weather and "what-if"
conditions.

The meter history the features read is exactly what the simulator produced
for each elapsed hour — the same values the persisted meter readings hold —
so it's read from the same source. Turning a forecast into what to buy or
sell is the household agent's job (`app.agents`), not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.forecasting.baseline import seasonal_naive
from app.forecasting.features import (
    HOURS_PER_DAY,
    MAX_HORIZON_HOURS,
    TARGET_CONSUMPTION,
    TARGET_GENERATION,
    TODAY_OFFSET,
    feature_row,
    features_for_household,
    hourly_window,
    target_index,
)
from app.forecasting.model import (
    ConformalOffsets,
    ModelMap,
    load_conformal,
    load_models,
    predict_quantiles,
)
from app.simulator.family import NO_OVERRIDE, HouseholdOverride
from app.simulator.scenarios import Scenario

MODEL_LIGHTGBM = "lightgbm-quantile"
MODEL_SEASONAL_NAIVE = "seasonal-naive"

_MODELS: ModelMap | None = None
_CONFORMAL: ConformalOffsets | None = None


def get_models() -> ModelMap:
    global _MODELS, _CONFORMAL
    if _MODELS is None:
        _MODELS = load_models()
        _CONFORMAL = load_conformal()
    return _MODELS


@dataclass(frozen=True, slots=True)
class HourForecast:
    slot: int  # 0 = the hour the session starts in
    day: date
    hour_of_day: int
    consumption_p10: float
    consumption_p50: float
    consumption_p90: float
    generation_p10: float
    generation_p50: float
    generation_p90: float

    @property
    def net_p50_kw(self) -> float:
        return self.generation_p50 - self.consumption_p50


def forecast_household(
    *,
    household_id: str,
    member_count: int,
    solar_capacity_kwp: float,
    start_date: date,
    start_hour: int,
    horizon_hours: int,
    scenario: Scenario,
    seed: int,
    tick_minutes: int = 15,
    override: HouseholdOverride = NO_OVERRIDE,
) -> tuple[str, list[HourForecast]]:
    """`horizon_hours` hourly forecasts starting with the hour that begins at
    `start_hour` on `start_date`, and which tier served them
    (`MODEL_LIGHTGBM`, or `MODEL_SEASONAL_NAIVE` — the ADR-0004 fallback)."""
    if not 1 <= horizon_hours <= MAX_HORIZON_HOURS:
        msg = f"horizon_hours must be 1-{MAX_HORIZON_HOURS}, got {horizon_hours}"
        raise ValueError(msg)
    window = hourly_window(
        household_id,
        member_count,
        solar_capacity_kwp,
        start_date,
        scenario,
        seed,
        tick_minutes,
        override,
        tomorrow_scenario=scenario,
    )
    family = features_for_household(household_id, member_count, seed)
    now_index = TODAY_OFFSET + start_hour
    rows = [
        feature_row(window, now_index=now_index, horizon_hours=h, family=family, seed=seed)
        for h in range(1, horizon_hours + 1)
    ]

    models = get_models()
    if models:
        predictions = predict_quantiles(models, rows, _CONFORMAL)
        model_name = MODEL_LIGHTGBM
    else:
        predictions = []
        for row in rows:
            naive = seasonal_naive(row["lag_day_consumption_kw"], row["lag_day_generation_kw"])
            predictions.append(
                {
                    TARGET_CONSUMPTION: dict.fromkeys(("p10", "p50", "p90"), naive.consumption_kw),
                    TARGET_GENERATION: dict.fromkeys(("p10", "p50", "p90"), naive.generation_kw),
                }
            )
        model_name = MODEL_SEASONAL_NAIVE

    forecasts: list[HourForecast] = []
    for slot, prediction in enumerate(predictions):
        target = target_index(now_index, slot + 1)
        cons, gen = prediction[TARGET_CONSUMPTION], prediction[TARGET_GENERATION]
        forecasts.append(
            HourForecast(
                slot=slot,
                day=start_date + timedelta(days=target // HOURS_PER_DAY - 2),
                hour_of_day=target % HOURS_PER_DAY,
                consumption_p10=cons["p10"],
                consumption_p50=cons["p50"],
                consumption_p90=cons["p90"],
                generation_p10=gen["p10"],
                generation_p50=gen["p50"],
                generation_p90=gen["p90"],
            )
        )
    return model_name, forecasts
