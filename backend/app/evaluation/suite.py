"""The evaluation suite: a fixed set of seeded sessions, chosen to cover what
a user can set on the plan page, rather than one flattering day.

Twelve 24-hour sessions from 6 am on the ten seeded homes — every season,
every weather scenario, both neighbourhood types, family what-ifs, an EB
power cut and peak surcharges — run in this order with the agents' memory
carried from one to the next, as it would be in use. Plus one 100-home
session for the scale test (objective O3), which also stresses the grid
safety layer (O4): a hundred homes on three laterals carry far more power
than ten.
"""

from __future__ import annotations

from datetime import date

from app.evaluation.runner import SessionSpec
from app.schemas.session import HouseholdWhatIf
from app.simulator.scenarios import Scenario

_NO_PANELS = (3, 5, 8)
_BIG_BATTERY = (2, 4, 9)
SCALE_HOUSEHOLDS = 100


def mixed(count: int = 10) -> tuple[HouseholdWhatIf, ...]:
    """The plan page's "Mixed neighbourhood" preset, repeated every ten
    homes: three with no panels and no battery (tenants, shaded roofs),
    three with a 15 kWh battery, the rest as built."""
    what_ifs: list[HouseholdWhatIf] = []
    for i in range(1, count + 1):
        position = (i - 1) % 10 + 1
        if position in _NO_PANELS:
            what_ifs.append(
                HouseholdWhatIf(household_id=f"h{i}", panel_derate=1.0, battery_capacity_kwh=0)
            )
        elif position in _BIG_BATTERY:
            what_ifs.append(HouseholdWhatIf(household_id=f"h{i}", battery_capacity_kwh=15))
    return tuple(what_ifs)


FAMILY_WHAT_IFS: tuple[HouseholdWhatIf, ...] = (
    HouseholdWhatIf(household_id="h1", guests=2),
    HouseholdWhatIf(household_id="h4", away_from=9, away_to=18),
    HouseholdWhatIf(household_id="h6", work_from_home=True),
    HouseholdWhatIf(household_id="h7", away_from=18, away_to=23),
    HouseholdWhatIf(household_id="h10", panel_derate=0.3),
)


def _day(
    name: str,
    when: date,
    scenario: Scenario,
    *,
    what_ifs: tuple[HouseholdWhatIf, ...] = (),
    power_cut: tuple[int, int] | None = None,
    peak_surcharge_pct: float = 0.0,
) -> SessionSpec:
    return SessionSpec(
        name=name,
        sim_date=when,
        start_hour=6,
        horizon_hours=24,
        scenario=scenario,
        what_ifs=what_ifs,
        power_cut=power_cut,
        peak_surcharge_pct=peak_surcharge_pct,
    )


SUITE: tuple[SessionSpec, ...] = (
    _day("Jan · identical homes", date(2026, 1, 15), Scenario.AUTO),
    _day("Jan · mixed", date(2026, 1, 15), Scenario.AUTO, what_ifs=mixed()),
    _day("Mar · family what-ifs", date(2026, 3, 10), Scenario.AUTO, what_ifs=FAMILY_WHAT_IFS),
    _day("Apr · clear sky, mixed", date(2026, 4, 15), Scenario.CLEAR, what_ifs=mixed()),
    _day("May · identical homes", date(2026, 5, 15), Scenario.AUTO),
    _day("May · mixed", date(2026, 5, 15), Scenario.AUTO, what_ifs=mixed()),
    _day("May · heatwave, mixed", date(2026, 5, 20), Scenario.HEATWAVE, what_ifs=mixed()),
    _day(
        "Jun · clear, mixed, +20% peak",
        date(2026, 6, 10),
        Scenario.CLEAR,
        what_ifs=mixed(),
        peak_surcharge_pct=20.0,
    ),
    _day("Jul · broken cloud, mixed", date(2026, 7, 15), Scenario.CLOUDY, what_ifs=mixed()),
    _day("Oct · monsoon rain, mixed", date(2026, 10, 25), Scenario.RAINY, what_ifs=mixed()),
    _day(
        "Nov · mixed, EB cut 7-9 pm",
        date(2026, 11, 20),
        Scenario.AUTO,
        what_ifs=mixed(),
        power_cut=(19, 21),
    ),
    _day(
        "Dec · identical, +20% peak",
        date(2026, 12, 10),
        Scenario.AUTO,
        peak_surcharge_pct=20.0,
    ),
)

SCALE_SESSION = SessionSpec(
    name=f"May · {SCALE_HOUSEHOLDS} homes, mixed",
    sim_date=date(2026, 5, 15),
    start_hour=10,
    horizon_hours=12,
    scenario=Scenario.AUTO,
    what_ifs=mixed(SCALE_HOUSEHOLDS),
)
