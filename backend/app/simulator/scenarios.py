"""Named weather/demand scenarios. Each is just a pair of multipliers applied
on top of the base profiles in `app.simulator.profiles` — the scenario picks
how much sun there is and how hard households lean on cooling, not a
separate model.

There is deliberately no "evening peak" scenario: every household already
has an evening every day, and `app.simulator.family`'s occupancy model
produces that ramp on its own — everyone comes home and switches their
room's AC on around the same few hours, regardless of which scenario is
selected. Making it a togglable scenario would have implied it was special;
it isn't, it's just what a normal day looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Scenario(StrEnum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    HEATWAVE = "heatwave"


@dataclass(frozen=True, slots=True)
class ScenarioProfile:
    solar_factor: float  # multiplies generation_kw
    demand_factor: float  # multiplies AC duty cycle in consumption_kw


_PROFILES: dict[Scenario, ScenarioProfile] = {
    Scenario.CLEAR: ScenarioProfile(solar_factor=1.0, demand_factor=1.0),
    Scenario.CLOUDY: ScenarioProfile(solar_factor=0.35, demand_factor=1.0),
    # Full sun (batteries and exports should be plentiful) but demand spikes
    # too (air conditioning) — calibrated so several households exporting at
    # once genuinely breaches the feeder's voltage ceiling. See
    # app.domain.grid.network.default_feeder's calibration notes.
    Scenario.HEATWAVE: ScenarioProfile(solar_factor=1.15, demand_factor=1.5),
}


def profile_for(scenario: Scenario) -> ScenarioProfile:
    return _PROFILES[scenario]
