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


def solve(network: Network, net_injection_kw: dict[str, float]) -> FlowResult:
    """Compute every line's flow and every bus's voltage for one tick.

    `net_injection_kw` is keyed by household bus id; positive means that
    household is a net exporter this tick, negative a net importer. Buses
    with no entry are treated as exactly balanced (0 kW).
    """
    line_flow_kw: dict[str, float] = {}
    for line in network.lines:
        subtree_net_export_kw = sum(
            net_injection_kw.get(bus, 0.0) for bus in network.subtree(line.to_bus)
        )
        # A net-exporting subtree pushes power backward, toward the
        # substation — the negative sign is what makes that show up as
        # reverse flow rather than as unusually low forward demand.
        line_flow_kw[line.id] = -subtree_net_export_kw

    bus_voltage_pu: dict[str, float] = {SUBSTATION_BUS: SUBSTATION_VOLTAGE_PU}
    for bus in network.household_buses():
        drop_pu = sum(
            line.resistance_pu * line_flow_kw[line.id] for line in network.path_from_substation(bus)
        )
        bus_voltage_pu[bus] = SUBSTATION_VOLTAGE_PU - drop_pu

    return FlowResult(line_flow_kw=line_flow_kw, bus_voltage_pu=bus_voltage_pu)
