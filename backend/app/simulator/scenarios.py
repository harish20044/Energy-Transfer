"""Named weather/demand scenarios. Each is just a pair of multipliers applied
on top of the base profiles in `app.simulator.profiles` — the scenario picks
how much sun there is and how hard households lean on cooling/heating, not a
separate model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Scenario(StrEnum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    EVENING_PEAK = "evening_peak"
    HEATWAVE = "heatwave"


@dataclass(frozen=True, slots=True)
class ScenarioProfile:
    solar_factor: float  # multiplies generation_kw
    demand_factor: float  # multiplies consumption_kw
    evening_peak_boost: float  # additional multiplier on the evening demand bump only


_PROFILES: dict[Scenario, ScenarioProfile] = {
    Scenario.CLEAR: ScenarioProfile(solar_factor=1.0, demand_factor=1.0, evening_peak_boost=1.0),
    Scenario.CLOUDY: ScenarioProfile(solar_factor=0.35, demand_factor=1.0, evening_peak_boost=1.0),
    Scenario.EVENING_PEAK: ScenarioProfile(
        solar_factor=1.0, demand_factor=1.0, evening_peak_boost=1.6
    ),
    # Full sun (batteries and exports should be plentiful) but demand spikes
    # too (air conditioning) — calibrated so several households exporting at
    # once genuinely breaches the feeder's voltage ceiling. See
    # app.domain.grid.network.default_feeder's calibration notes.
    Scenario.HEATWAVE: ScenarioProfile(
        solar_factor=1.15, demand_factor=1.5, evening_peak_boost=1.2
    ),
}


def profile_for(scenario: Scenario) -> ScenarioProfile:
    return _PROFILES[scenario]
