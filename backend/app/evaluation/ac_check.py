"""Full AC power flow (pandapower, Newton-Raphson) over the same feeder and
the same injections the grid safety layer checked with linearised DistFlow:
confirms the fast check in the clearing path never let a violation through
that the linearisation hid (objective O4).

The safety layer's model is kept exactly: the injections are the settled
neighbour trades (a household's net export to neighbours for the hour, as
average kW), inverters run at unity power factor, and the substation holds
1.0 pu. The per-unit feeder becomes physical units on a 1 kVA, 0.415 kV
base — the base the linearised model's kW arithmetic implies — with a
typical low-voltage cable X/R ratio, since the linear model ignores
reactance altogether.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

from app.domain.grid.network import SUBSTATION_BUS, Network

BASE_VOLTAGE_KV = 0.415  # LV three-phase, line to line
BASE_POWER_KVA = 1.0
# Typical of LV XLPE distribution cable.
X_OVER_R = 0.25


@dataclass(frozen=True, slots=True)
class AcResult:
    max_loading_pct: float
    min_voltage_pu: float
    max_voltage_pu: float
    thermal_violations: int
    voltage_violations: int
    converged: bool


def ac_check(network: Network, net_injection_kw: dict[str, float]) -> AcResult:
    # Imported here: heavy, and only the evaluation needs it.
    import pandapower as pp

    z_base_ohm = BASE_VOLTAGE_KV**2 / (BASE_POWER_KVA / 1000.0)
    net = pp.create_empty_network(sn_mva=BASE_POWER_KVA / 1000.0)
    buses = {
        bus: pp.create_bus(net, vn_kv=BASE_VOLTAGE_KV, name=bus) for bus in sorted(network.buses())
    }
    pp.create_ext_grid(net, buses[SUBSTATION_BUS], vm_pu=1.0)
    for line in network.lines:
        r_ohm = line.resistance_pu * z_base_ohm
        pp.create_line_from_parameters(
            net,
            buses[line.from_bus],
            buses[line.to_bus],
            length_km=1.0,
            r_ohm_per_km=r_ohm,
            x_ohm_per_km=r_ohm * X_OVER_R,
            c_nf_per_km=0.0,
            max_i_ka=line.thermal_limit_kw / (math.sqrt(3) * BASE_VOLTAGE_KV) / 1000.0,
            name=line.id,
        )
    for bus, kw in net_injection_kw.items():
        if abs(kw) < 1e-12:
            continue
        if kw > 0:
            pp.create_sgen(net, buses[bus], p_mw=kw / 1000.0)
        else:
            pp.create_load(net, buses[bus], p_mw=-kw / 1000.0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=False)
        except pp.LoadflowNotConverged:
            return AcResult(0.0, 0.0, 0.0, 0, 0, converged=False)

    loading = net.res_line["loading_percent"].to_numpy()
    voltage = net.res_bus["vm_pu"].to_numpy()
    return AcResult(
        max_loading_pct=float(loading.max()) if len(loading) else 0.0,
        min_voltage_pu=float(voltage.min()),
        max_voltage_pu=float(voltage.max()),
        thermal_violations=int((loading > 100.0 + 1e-6).sum()),
        voltage_violations=int(
            (
                (voltage < network.voltage_min_pu - 1e-6)
                | (voltage > network.voltage_max_pu + 1e-6)
            ).sum()
        ),
        converged=True,
    )
