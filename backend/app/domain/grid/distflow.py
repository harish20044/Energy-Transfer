"""Linearized DistFlow: the sub-millisecond feasibility check that runs
inside the clearing loop on every tick (objective O3's latency budget).

Simplifications, stated plainly rather than left implicit:

- **Real power only.** Reactive power and inverter power factor are not
  modeled, so this is a real-power linearization, not full AC power flow.
- **Linearized voltage drop.** Uses the standard LinDistFlow approximation
  ``V_bus ≈ V_substation - sum(R_pu * P_line_pu)`` along the path from the
  substation, dropping the (much smaller) quadratic term full DistFlow keeps.

Both are the right trade-off here: the quantity actually being protected is
thermal loading, where this is exact (Kirchhoff's current law has no
linearization error on a tree), and the voltage check only needs to be
directionally correct enough to catch the reverse-power-flow-from-solar case
this project cares about, not to replace a load-flow study.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from app.domain.grid.network import SUBSTATION_BUS, Network

SUBSTATION_VOLTAGE_PU = 1.0


@dataclass(frozen=True, slots=True)
class FlowResult:
    """One tick's power flow, given a net injection at every household."""

    # Positive = flowing away from the substation (net local consumption);
    # negative = flowing toward it (the lateral is a net exporter — the
    # reverse-flow case high solar penetration causes).
    line_flow_kw: dict[str, float]
    bus_voltage_pu: dict[str, float]


@dataclass(frozen=True, slots=True)
class _FlowMatrices:
    """A feeder's shape as two matrices, built once per feeder: which
    households sit below each line, and each household's path back to the
    substation weighted by line resistance. A solve is then two
    matrix-vector products instead of a walk of the tree per line and bus."""

    buses: tuple[str, ...]
    line_ids: tuple[str, ...]
    below: npt.NDArray[np.float64]  # lines x buses: 1 where the bus is downstream
    path_resistance: npt.NDArray[np.float64]  # buses x lines: R_pu on the path


@lru_cache(maxsize=64)
def _matrices(network: Network) -> _FlowMatrices:
    buses = tuple(sorted(network.household_buses()))
    position = {bus: i for i, bus in enumerate(buses)}
    line_index = {line.id: j for j, line in enumerate(network.lines)}
    below = np.zeros((len(network.lines), len(buses)))
    for j, line in enumerate(network.lines):
        for bus in network.subtree(line.to_bus):
            if bus in position:
                below[j, position[bus]] = 1.0
    path_resistance = np.zeros((len(buses), len(network.lines)))
    for bus, i in position.items():
        for line in network.path_from_substation(bus):
            path_resistance[i, line_index[line.id]] = line.resistance_pu
    return _FlowMatrices(
        buses=buses,
        line_ids=tuple(line.id for line in network.lines),
        below=below,
        path_resistance=path_resistance,
    )


def solve(network: Network, net_injection_kw: dict[str, float]) -> FlowResult:
    """Compute every line's flow and every bus's voltage for one tick.

    `net_injection_kw` is keyed by household bus id; positive means that
    household is a net exporter this tick, negative a net importer. Buses
    with no entry are treated as exactly balanced (0 kW).
    """
    m = _matrices(network)
    injection = np.array([net_injection_kw.get(bus, 0.0) for bus in m.buses])
    # A net-exporting subtree pushes power backward, toward the substation —
    # the negative sign is what makes that show up as reverse flow rather
    # than as unusually low forward demand.
    flows = -(m.below @ injection)
    drops = m.path_resistance @ flows
    line_flow_kw = dict(zip(m.line_ids, flows.tolist(), strict=True))
    bus_voltage_pu: dict[str, float] = {SUBSTATION_BUS: SUBSTATION_VOLTAGE_PU}
    bus_voltage_pu.update(zip(m.buses, (SUBSTATION_VOLTAGE_PU - drops).tolist(), strict=True))
    return FlowResult(line_flow_kw=line_flow_kw, bus_voltage_pu=bus_voltage_pu)
