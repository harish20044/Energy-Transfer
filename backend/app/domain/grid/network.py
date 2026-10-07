"""The physical feeder: a radial (tree) low-voltage network connecting every
household back to one substation.

Values are expressed in per-unit (pu) for resistance/reactance, the standard
convention in linearized distribution power-flow — it keeps the voltage-drop
arithmetic in `distflow.py` free of unit-conversion bugs. Thermal limits are
kept in real kW since that is what a trade quantity is measured in and what a
dashboard actually displays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

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
    # The linearised check keeps this far inside the statutory band. Full AC
    # power flow (app/evaluation/ac_check.py) puts bus voltages up to
    # 0.013 pu beyond the linear estimate on a heavily loaded 100-home
    # feeder, so a check curtailing exactly to the limit lets real
    # violations through.
    voltage_margin_pu: float = 0.015

    @property
    def operating_min_pu(self) -> float:
        return self.voltage_min_pu + self.voltage_margin_pu

    @property
    def operating_max_pu(self) -> float:
        return self.voltage_max_pu - self.voltage_margin_pu

    def buses(self) -> frozenset[str]:
        return _topology(self).buses

    def household_buses(self) -> frozenset[str]:
        return _topology(self).buses - {SUBSTATION_BUS}

    def line_to(self, bus: str) -> Line:
        """The single line feeding `bus` from its parent — exists exactly
        once per non-substation bus in a well-formed tree."""
        matches = _topology(self).incoming.get(bus, ())
        if len(matches) != 1:
            msg = f"expected exactly one incoming line to {bus!r}, found {len(matches)}"
            raise ValueError(msg)
        return matches[0]

    def children_of(self, bus: str) -> tuple[str, ...]:
        return _topology(self).children.get(bus, ())

    def subtree(self, bus: str) -> frozenset[str]:
        """`bus` and every household downstream of it."""
        cache = _topology(self).subtrees
        if bus not in cache:
            result = {bus}
            frontier = [bus]
            while frontier:
                current = frontier.pop()
                for child in self.children_of(current):
                    if child not in result:
                        result.add(child)
                        frontier.append(child)
            cache[bus] = frozenset(result)
        return cache[bus]

    def path_from_substation(self, bus: str) -> tuple[Line, ...]:
        """Every line from the substation down to `bus`, in order."""
        cache = _topology(self).paths
        if bus not in cache:
            chain: list[Line] = []
            current = bus
            while current != SUBSTATION_BUS:
                line = self.line_to(current)
                chain.append(line)
                current = line.from_bus
            cache[bus] = tuple(reversed(chain))
        return cache[bus]


@dataclass(frozen=True, slots=True)
class _Topology:
    """A feeder's shape, worked out once: the grid safety layer asks for the
    same subtrees and paths on every check of every slot, and recomputing
    them each time grows with the cube of the feeder's size."""

    buses: frozenset[str]
    incoming: dict[str, tuple[Line, ...]]
    children: dict[str, tuple[str, ...]]
    # Filled on first use, so a malformed tree still fails where it always did.
    subtrees: dict[str, frozenset[str]] = field(default_factory=dict)
    paths: dict[str, tuple[Line, ...]] = field(default_factory=dict)


@lru_cache(maxsize=64)
def _topology(network: Network) -> _Topology:
    buses = {SUBSTATION_BUS}
    incoming: dict[str, list[Line]] = {}
    children: dict[str, list[str]] = {}
    for line in network.lines:
        buses.add(line.from_bus)
        buses.add(line.to_bus)
        incoming.setdefault(line.to_bus, []).append(line)
        children.setdefault(line.from_bus, []).append(line.to_bus)
    return _Topology(
        buses=frozenset(buses),
        incoming={bus: tuple(lines) for bus, lines in incoming.items()},
        children={bus: tuple(kids) for bus, kids in children.items()},
    )


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
