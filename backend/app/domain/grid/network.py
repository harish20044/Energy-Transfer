"""The physical feeder: a radial (tree) low-voltage network connecting every
household back to one substation.

Values are expressed in per-unit (pu) for resistance/reactance, the standard
convention in linearized distribution power-flow — it keeps the voltage-drop
arithmetic in `distflow.py` free of unit-conversion bugs. Thermal limits are
kept in real kW since that is what a trade quantity is measured in and what a
dashboard actually displays.
"""

from __future__ import annotations

from dataclasses import dataclass

SUBSTATION_BUS = "substation"


@dataclass(frozen=True, slots=True)
class Line:
    """One segment of feeder between two buses."""

    id: str
    from_bus: str
    to_bus: str
    resistance_pu: float
    thermal_limit_kw: float


@dataclass(frozen=True, slots=True)
class Network:
    """A radial feeder. `lines` must form a tree rooted at `SUBSTATION_BUS` —
    every bus reachable by exactly one path back to the substation, which is
    what lets `distflow.py` compute a line's flow as "the sum of every
    household downstream of it" with no cycles to worry about."""

    lines: tuple[Line, ...]
    voltage_min_pu: float = 0.95
    voltage_max_pu: float = 1.05

    def buses(self) -> frozenset[str]:
        buses = {SUBSTATION_BUS}
        for line in self.lines:
            buses.add(line.from_bus)
            buses.add(line.to_bus)
        return frozenset(buses)

    def household_buses(self) -> frozenset[str]:
        return self.buses() - {SUBSTATION_BUS}

    def line_to(self, bus: str) -> Line:
        """The single line feeding `bus` from its parent — exists exactly
        once per non-substation bus in a well-formed tree."""
        matches = [line for line in self.lines if line.to_bus == bus]
        if len(matches) != 1:
            msg = f"expected exactly one incoming line to {bus!r}, found {len(matches)}"
            raise ValueError(msg)
        return matches[0]

    def children_of(self, bus: str) -> tuple[str, ...]:
        return tuple(line.to_bus for line in self.lines if line.from_bus == bus)

    def subtree(self, bus: str) -> frozenset[str]:
        """`bus` and every household downstream of it."""
        result = {bus}
        frontier = [bus]
        while frontier:
            current = frontier.pop()
            for child in self.children_of(current):
                if child not in result:
                    result.add(child)
                    frontier.append(child)
        return frozenset(result)

    def path_from_substation(self, bus: str) -> tuple[Line, ...]:
        """Every line from the substation down to `bus`, in order."""
        chain: list[Line] = []
        current = bus
        while current != SUBSTATION_BUS:
            line = self.line_to(current)
            chain.append(line)
            current = line.from_bus
        return tuple(reversed(chain))


def default_feeder(household_ids: list[str]) -> Network:
    """A representative small residential feeder: three laterals of roughly
    equal length branching from one substation, each a simple radial chain of
    households — the common real-world topology for a low-voltage
    residential distribution feeder, and what lets one overloaded lateral be
    demonstrated without affecting the other two.

    Accepts any number of households (used for both a 10-house demo and
    smaller test fixtures); splits them into three laterals as evenly as
    possible.
    """
    if not household_ids:
        msg = "default_feeder requires at least one household"
        raise ValueError(msg)

    lateral_count = min(3, len(household_ids))
    laterals: list[list[str]] = [[] for _ in range(lateral_count)]
    for index, household_id in enumerate(household_ids):
        laterals[index % lateral_count].append(household_id)

    # Representative LV cable per-unit impedance and ampacity-derived thermal
    # limit for a short residential lateral segment. Calibrated so ordinary
    # rooftop-solar-scale flows (a few kW per house) stay comfortably within
    # both limits, while a stress scenario stacking several houses' exports
    # on one lateral (as a "heatwave" or "all sunny at once" scenario would)
    # can genuinely breach them — the thing the safety layer exists to catch.
    resistance_pu_per_segment = 0.0015
    thermal_limit_kw = 20.0

    lines: list[Line] = []
    for lateral in laterals:
        previous_bus = SUBSTATION_BUS
        for household_id in lateral:
            lines.append(
                Line(
                    id=f"{previous_bus}->{household_id}",
                    from_bus=previous_bus,
                    to_bus=household_id,
                    resistance_pu=resistance_pu_per_segment,
                    thermal_limit_kw=thermal_limit_kw,
                )
            )
            previous_bus = household_id

    return Network(lines=tuple(lines))
