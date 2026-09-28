"""Pure feature engineering, shared by training and live inference — the same
function builds a training row and a live forecast's input, so there is no
train/serve skew by construction.

Deliberately excluded: the ground-truth `Scenario` for the hour being
predicted. In reality nobody knows four hours ahead of time whether a cloud
will roll in — a forecaster only ever has calendar facts (what a real family
does at this hour on this day of the week), a household's own physical
routine (who's actually home), and what its meter has already measured. The
`lag_*` features below are how the model infers "it's cloudy today" from
recent readings instead of being told, which is also what gives the P10/P90
band genuine content instead of collapsing to a point forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.simulator.family import Family, generate_family, snapshot_occupancy

HORIZONS_HOURS: tuple[int, ...] = (1, 2, 3, 4)

FEATURE_COLUMNS: tuple[str, ...] = (
    "hour_of_day",
    "is_weekend",
    "horizon_hours",
    "member_count",
    "occupied_bedrooms",
    "schedule_offset_hours",
    "solar_capacity_kwp",
    "present_count_target",
    "lag_1h_consumption_kw",
    "lag_1h_generation_kw",
    "lag_2h_consumption_kw",
    "lag_2h_generation_kw",
    "lag_24h_consumption_kw",
    "lag_24h_generation_kw",
)

TARGET_CONSUMPTION = "consumption_kw"
TARGET_GENERATION = "generation_kw"


@dataclass(frozen=True, slots=True)
class HourlyLags:
    """The three past readings a real smart meter would already have on hand
    by the time a forecast is requested."""

    lag_1h_consumption_kw: float
    lag_1h_generation_kw: float
    lag_2h_consumption_kw: float
    lag_2h_generation_kw: float
    lag_24h_consumption_kw: float
    lag_24h_generation_kw: float


def household_family(household_id: str, member_count: int, seed: int) -> Family:
    return generate_family(household_id, member_count, seed)


def present_count_at(family: Family, hour_of_day: float, is_weekend: bool) -> int:
    """Members physically home at a future hour — a fact about this
    household's routine (who's at work or school), not about the weather, so
    unlike consumption itself it's exactly knowable ahead of time and safe to
    use as a forecasting feature. `demand_factor=1.0` because occupancy
    itself doesn't depend on the scenario, only how hard an occupied room's
    AC runs does."""
    snapshot = snapshot_occupancy(family, hour_of_day, is_weekend, demand_factor=1.0)
    return snapshot.present_count


def feature_row(
    *,
    family: Family,
    solar_capacity_kwp: float,
    target_hour_of_day: float,
    target_is_weekend: bool,
    horizon_hours: int,
    lags: HourlyLags,
) -> dict[str, float]:
    """One forecasting input row for the hour `horizon_hours` ahead of now."""
    return {
        "hour_of_day": target_hour_of_day,
        "is_weekend": float(target_is_weekend),
        "horizon_hours": float(horizon_hours),
        "member_count": float(len(family.members)),
        "occupied_bedrooms": float(family.occupied_bedrooms),
        "schedule_offset_hours": family.schedule_offset_hours,
        "solar_capacity_kwp": solar_capacity_kwp,
        "present_count_target": float(
            present_count_at(family, target_hour_of_day, target_is_weekend)
        ),
        "lag_1h_consumption_kw": lags.lag_1h_consumption_kw,
        "lag_1h_generation_kw": lags.lag_1h_generation_kw,
        "lag_2h_consumption_kw": lags.lag_2h_consumption_kw,
        "lag_2h_generation_kw": lags.lag_2h_generation_kw,
        "lag_24h_consumption_kw": lags.lag_24h_consumption_kw,
        "lag_24h_generation_kw": lags.lag_24h_generation_kw,
    }
