"""Live inference: combine a household's actual recent meter history (from
the database — the same real readings the dashboard already shows) with the
trained quantile models to forecast the next 1-4 hours, and turn each hour's
median net position into a buy/sell/hold call using the same domain-layer
battery policy that decides real trades
(`app.domain.battery.policy.plan_position`) — so the panel's advice is
computed the way the market itself would actually act on it, not a separate
guess.

Simplifying assumption, stated plainly: every horizon's recommendation uses
the household's *current* battery state of charge, not a projection of where
it will be after 1-3 more hours of trading. Compounding a battery trajectory
forward under forecast uncertainty is a further step (and would need its own
uncertainty treatment) — what this answers is "given today's battery, would
this hour's typical position be a sale or a purchase", which is exactly the
buy/sell signal being asked for.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.battery.model import Battery
from app.domain.battery.policy import BatteryAction, plan_position
from app.forecasting.baseline import seasonal_naive
from app.forecasting.features import HORIZONS_HOURS, HourlyLags, feature_row, household_family
from app.forecasting.model import ModelMap, load_models, predict_quantiles
from app.models.simulation import MeterReading
from app.simulator.profiles import consumption_kw, generation_kw
from app.simulator.scenarios import Scenario

HOURS_PER_DAY = 24

_MODELS: ModelMap | None = None
_MODELS_LOADED = False

MODEL_LIGHTGBM = "lightgbm-quantile"
MODEL_SEASONAL_NAIVE = "seasonal-naive"


def _get_models() -> ModelMap:
    global _MODELS, _MODELS_LOADED
    if not _MODELS_LOADED:
        _MODELS = load_models()
        _MODELS_LOADED = True
    return _MODELS or {}


@dataclass(frozen=True, slots=True)
class HourForecast:
    horizon_hours: int
    hour_of_day: float
    consumption_p10: float
    consumption_p50: float
    consumption_p90: float
    generation_p10: float
    generation_p50: float
    generation_p90: float
    net_p50_kw: float
    recommended_action: str  # "sell" | "buy" | "hold"
    projected_net_for_market_kw: float


async def _hour_average(
    session: AsyncSession, household_id: str, hour_index: int, *, tick_minutes: int
) -> tuple[float, float] | None:
    """This household's mean consumption/generation over one already-elapsed
    simulated hour, from its real persisted meter readings — None if that
    hour hasn't been simulated yet."""
    if hour_index < 0:
        return None
    ticks_per_hour = 60 // tick_minutes
    start_tick = hour_index * ticks_per_hour
    rows = (
        await session.scalars(
            select(MeterReading).where(
                MeterReading.household_id == household_id,
                MeterReading.tick_index >= start_tick,
                MeterReading.tick_index < start_tick + ticks_per_hour,
            )
        )
    ).all()
    if len(rows) < ticks_per_hour:
        return None
    return (
        sum(r.consumption_kw for r in rows) / len(rows),
        sum(r.generation_kw for r in rows) / len(rows),
    )


async def _hour_average_or_estimate(
    session: AsyncSession,
    household_id: str,
    hour_index: int,
    *,
    member_count: int,
    solar_capacity_kwp: float,
    scenario: Scenario,
    seed: int,
    tick_minutes: int,
) -> tuple[float, float]:
    """Real history where it exists; the pure simulator standing in for a
    day that hasn't actually been played yet otherwise — only matters in the
    first 24 simulated hours of a brand-new deployment, before any real
    'yesterday' exists to look back on."""
    real = await _hour_average(session, household_id, hour_index, tick_minutes=tick_minutes)
    if real is not None:
        return real

    ticks_per_hour = 60 // tick_minutes
    base_tick = hour_index * ticks_per_hour
    cons_total = 0.0
    gen_total = 0.0
    for sub in range(ticks_per_hour):
        tick_index = base_tick + sub
        cons_total += consumption_kw(
            household_id,
            tick_index,
            member_count=member_count,
            tick_minutes=tick_minutes,
            scenario=scenario,
            seed=seed,
        )
        gen_total += generation_kw(
            tick_index,
            solar_capacity_kwp=solar_capacity_kwp,
            tick_minutes=tick_minutes,
            scenario=scenario,
        )
    return cons_total / ticks_per_hour, gen_total / ticks_per_hour


async def forecast_household(
    session: AsyncSession,
    *,
    household_id: str,
    member_count: int,
    solar_capacity_kwp: float,
    battery: Battery,
    evening_reserve: float,
    tick_index: int,
    tick_minutes: int,
    scenario: Scenario,
    seed: int,
) -> tuple[str, list[HourForecast]]:
    """This household's next 1-4 hours. Returns which tier actually served
    the forecast (`MODEL_LIGHTGBM` or `MODEL_SEASONAL_NAIVE`, the ADR-0004
    fallback) alongside the hourly forecasts themselves."""
    now_hour = tick_index // (60 // tick_minutes)
    family = household_family(household_id, member_count, seed)
    models = _get_models()

    async def lag(hours_ago: int) -> tuple[float, float]:
        return await _hour_average_or_estimate(
            session,
            household_id,
            now_hour - hours_ago,
            member_count=member_count,
            solar_capacity_kwp=solar_capacity_kwp,
            scenario=scenario,
            seed=seed,
            tick_minutes=tick_minutes,
        )

    lag_1h, lag_2h, lag_24h = await lag(1), await lag(2), await lag(24)
    lags = HourlyLags(
        lag_1h_consumption_kw=lag_1h[0],
        lag_1h_generation_kw=lag_1h[1],
        lag_2h_consumption_kw=lag_2h[0],
        lag_2h_generation_kw=lag_2h[1],
        lag_24h_consumption_kw=lag_24h[0],
        lag_24h_generation_kw=lag_24h[1],
    )

    model_name = MODEL_LIGHTGBM if models else MODEL_SEASONAL_NAIVE
    forecasts: list[HourForecast] = []

    for horizon in HORIZONS_HOURS:
        target_hour = now_hour + horizon
        target_hour_of_day = float(target_hour % HOURS_PER_DAY)
        target_is_weekend = (target_hour // HOURS_PER_DAY) % 7 in (5, 6)

        if models:
            row = feature_row(
                family=family,
                solar_capacity_kwp=solar_capacity_kwp,
                target_hour_of_day=target_hour_of_day,
                target_is_weekend=target_is_weekend,
                horizon_hours=horizon,
                lags=lags,
            )
            quantiles = predict_quantiles(models, row)
            cons, gen = quantiles["consumption_kw"], quantiles["generation_kw"]
        else:
            baseline = seasonal_naive(lags.lag_24h_consumption_kw, lags.lag_24h_generation_kw)
            cons = {
                "p10": baseline.consumption_kw,
                "p50": baseline.consumption_kw,
                "p90": baseline.consumption_kw,
            }
            gen = {
                "p10": baseline.generation_kw,
                "p50": baseline.generation_kw,
                "p90": baseline.generation_kw,
            }

        net_p50 = gen["p50"] - cons["p50"]
        is_evening = not (6.0 <= target_hour_of_day < 18.0)
        plan = plan_position(
            battery,
            net_generation_kw=net_p50,
            duration_h=1.0,
            evening_reserve=evening_reserve,
            is_evening=is_evening,
        )

        if plan.battery_action is BatteryAction.DISCHARGING and plan.net_for_market_kw > 1e-6:
            action = "sell"
        elif plan.net_for_market_kw < -1e-6:
            action = "buy"
        else:
            action = "hold"

        forecasts.append(
            HourForecast(
                horizon_hours=horizon,
                hour_of_day=target_hour_of_day,
                consumption_p10=cons["p10"],
                consumption_p50=cons["p50"],
                consumption_p90=cons["p90"],
                generation_p10=gen["p10"],
                generation_p50=gen["p50"],
                generation_p90=gen["p90"],
                net_p50_kw=net_p50,
                recommended_action=action,
                projected_net_for_market_kw=plan.net_for_market_kw,
            )
        )

    return model_name, forecasts
