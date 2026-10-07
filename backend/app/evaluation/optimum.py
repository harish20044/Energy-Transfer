"""The hindsight optimum for objective O2: the cheapest the whole
neighbourhood could possibly have run the session, had it known in advance
exactly what every home would use and generate.

A linear program over every 15-minute interval of the session:

- per home and interval: EB import and export, battery charge and
  discharge, energy sent to and taken from neighbours, unserved load and
  curtailed solar;
- energy balance in every home in every interval;
- the battery as the delivery code models it: charge rate, discharge rate,
  round-trip efficiency charged on the way in, capacity, and the
  protection floor;
- neighbours' energy balances across the feeder in every interval (what one
  home sends, others take);
- the grid safety layer's own constraints on those neighbour flows: line
  thermal limits and bus voltages from the same linearised DistFlow;
- no EB at all during a power cut.

Community welfare is what the households pay the EB, net: payments between
neighbours are transfers and cancel. So the optimum minimises

    sum over intervals of  (retail x import - feed-in x export + VoLL x unserved)
    - feed-in x (battery energy at the end - battery energy at the start)

The last term values charge left in the batteries at the feed-in tariff, so
a schedule that just drains every battery by the end isn't counted as a
saving. Exactly the same cost function is applied to what the agents
actually did and to the EB-only replay (`community_cost`), so the three are
comparable; and since the agents' own operation is one feasible point of
this program, the optimum can never cost more than it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from app.domain.settlement.delivery import PROTECTION_FLOOR_SOC
from app.evaluation.runner import Ledger, SessionRun

# Value of lost load: what an unserved kWh costs the community. A modelling
# choice — about five times the retail tariff — so that serving load always
# beats leaving it unserved, as it should.
VOLL_INR_PER_KWH = 50.0

# A negligible cost per unit moved between neighbours (₹0.0001): many
# schedules tie on cost (h2 passing a unit on to the EB costs the same as h1
# exporting it), and this picks the one moving least, so the optimum's P2P
# volume means something. Excluded from the reported cost.
_TRANSFER_TIEBREAK_INR = 1e-4

_VARS = ("imp", "exp", "ch", "dis", "out", "inn", "uns", "cur", "soc")
_N_VARS = len(_VARS)


@dataclass(frozen=True, slots=True)
class Optimum:
    cost_inr: float
    eb_import_kwh: float
    eb_export_kwh: float
    p2p_kwh: float
    unserved_kwh: float


def community_cost(run: SessionRun, which: str) -> float:
    """`which` = "actual" (what the agents did) or "alone" (EB only), on
    the optimum's own cost function."""
    total = 0.0
    final_fit = run.feed_in[-1]
    for h in run.households.values():
        ledger: Ledger = getattr(h, which)
        end = h.actual_end_kwh if which == "actual" else h.alone_end_kwh
        total += ledger.paid_eb - ledger.earned_eb + VOLL_INR_PER_KWH * ledger.unserved_kwh
        total -= final_fit * (end - h.start_battery.stored_kwh)
    return total


def solve_optimum(run: SessionRun, *, minimise_export: bool = False) -> Optimum:
    """The cheapest schedule — or, with `minimise_export`, the one sending
    the least solar to the EB that physics allows (still serving every load
    it can), which bounds what any mechanism could do for objective O5. The
    reported cost is always the community cost of the schedule found."""
    households = list(run.households.values())
    n, t_count = len(households), run.intervals
    dt = run.interval_hours
    ticks_per_hour = 60 // run.tick_minutes

    def index(h: int, t: int, var: str) -> int:
        return (h * t_count + t) * _N_VARS + _VARS.index(var)

    size = n * t_count * _N_VARS
    cost = np.zeros(size)
    lower = np.zeros(size)
    upper = np.full(size, np.inf)
    final_fit = run.feed_in[-1]

    eq_rows: list[int] = []
    eq_cols: list[int] = []
    eq_vals: list[float] = []
    eq_rhs: list[float] = []

    def eq(terms: list[tuple[int, float]], rhs: float) -> None:
        row = len(eq_rhs)
        for col, val in terms:
            eq_rows.append(row)
            eq_cols.append(col)
            eq_vals.append(val)
        eq_rhs.append(rhs)

    for h, home in enumerate(households):
        battery = home.start_battery
        floor = min(PROTECTION_FLOOR_SOC * battery.capacity_kwh, battery.stored_kwh)
        eta = battery.round_trip_efficiency
        for t in range(t_count):
            slot = t // ticks_per_hour
            eb_on = run.eb_by_interval[t]
            retail, fit = run.retail[slot], run.feed_in[slot]
            if minimise_export:
                cost[index(h, t, "exp")] = dt
                cost[index(h, t, "uns")] = 1000.0 * dt  # serve load first
            else:
                cost[index(h, t, "imp")] = retail * dt
                cost[index(h, t, "exp")] = -fit * dt
                cost[index(h, t, "uns")] = VOLL_INR_PER_KWH * dt
                cost[index(h, t, "out")] = _TRANSFER_TIEBREAK_INR * dt
            if not eb_on:
                upper[index(h, t, "imp")] = 0.0
                upper[index(h, t, "exp")] = 0.0
            upper[index(h, t, "ch")] = battery.max_charge_kw
            upper[index(h, t, "dis")] = battery.max_discharge_kw
            # Solar is only ever curtailed when it has nowhere to go: during a
            # power cut, as delivery does. Otherwise it is used, stored or exported.
            upper[index(h, t, "cur")] = 0.0 if eb_on else home.generation_kw[t]
            lower[index(h, t, "soc")] = floor
            upper[index(h, t, "soc")] = max(floor, battery.capacity_kwh)
            # Energy balance, in kW over the interval:
            # gen - cur + dis + imp + inn + uns = load + ch + exp + out
            eq(
                [
                    (index(h, t, "cur"), -1.0),
                    (index(h, t, "dis"), 1.0),
                    (index(h, t, "imp"), 1.0),
                    (index(h, t, "inn"), 1.0),
                    (index(h, t, "uns"), 1.0),
                    (index(h, t, "ch"), -1.0),
                    (index(h, t, "exp"), -1.0),
                    (index(h, t, "out"), -1.0),
                ],
                home.consumption_kw[t] - home.generation_kw[t],
            )
            # Battery: soc[t] = soc[t-1] + dt (eta ch - dis)
            terms = [
                (index(h, t, "soc"), 1.0),
                (index(h, t, "ch"), -eta * dt),
                (index(h, t, "dis"), dt),
            ]
            if t == 0:
                eq(terms, battery.stored_kwh)
            else:
                eq([*terms, (index(h, t - 1, "soc"), -1.0)], 0.0)
        if not minimise_export:
            cost[index(h, t_count - 1, "soc")] -= final_fit

    for t in range(t_count):
        # What neighbours send equals what neighbours take.
        eq(
            [(index(h, t, "out"), 1.0) for h in range(n)]
            + [(index(h, t, "inn"), -1.0) for h in range(n)],
            0.0,
        )

    ub_rows: list[int] = []
    ub_cols: list[int] = []
    ub_vals: list[float] = []
    ub_rhs: list[float] = []

    def le(terms: dict[int, float], rhs: float) -> None:
        row = len(ub_rhs)
        for col, val in terms.items():
            ub_rows.append(row)
            ub_cols.append(col)
            ub_vals.append(val)
        ub_rhs.append(rhs)

    position = {home.household_id: h for h, home in enumerate(households)}
    network = run.network
    subtrees = {
        line.id: [position[b] for b in network.subtree(line.to_bus) if b in position]
        for line in network.lines
    }
    for t in range(t_count):
        # Line flow = -(net neighbour export of every home downstream).
        flows: dict[str, dict[int, float]] = {}
        for line in network.lines:
            flow: dict[int, float] = {}
            for h in subtrees[line.id]:
                flow[index(h, t, "out")] = -1.0
                flow[index(h, t, "inn")] = 1.0
            flows[line.id] = flow
            le(flow, line.thermal_limit_kw)
            le({k: -v for k, v in flow.items()}, line.thermal_limit_kw)
        for bus in network.household_buses():
            if bus not in position:
                continue
            # V = 1 - sum(R * flow) along the path from the substation.
            drop: dict[int, float] = {}
            for line in network.path_from_substation(bus):
                for col, coeff in flows[line.id].items():
                    drop[col] = drop.get(col, 0.0) + line.resistance_pu * coeff
            # Within the safety layer's operating band:
            # V <= vmax -> -drop <= vmax - 1;  V >= vmin -> drop <= 1 - vmin
            le({k: -v for k, v in drop.items()}, network.operating_max_pu - 1.0)
            le(drop, 1.0 - network.operating_min_pu)

    a_eq = coo_matrix((eq_vals, (eq_rows, eq_cols)), shape=(len(eq_rhs), size)).tocsr()
    a_ub = coo_matrix((ub_vals, (ub_rows, ub_cols)), shape=(len(ub_rhs), size)).tocsr()
    result = linprog(
        cost,
        A_ub=a_ub,
        b_ub=np.array(ub_rhs),
        A_eq=a_eq,
        b_eq=np.array(eq_rhs),
        bounds=np.column_stack([lower, upper]),
        method="highs",
    )
    if not result.success:
        msg = f"hindsight optimum failed for {run.spec.name}: {result.message}"
        raise RuntimeError(msg)
    x = result.x

    def total(var: str) -> float:
        return float(sum(x[index(h, t, var)] for h in range(n) for t in range(t_count)) * dt)

    community = sum(
        dt * run.retail[t // ticks_per_hour] * x[index(h, t, "imp")]
        - dt * run.feed_in[t // ticks_per_hour] * x[index(h, t, "exp")]
        + dt * VOLL_INR_PER_KWH * x[index(h, t, "uns")]
        for h in range(n)
        for t in range(t_count)
    ) - final_fit * sum(
        x[index(h, t_count - 1, "soc")] - home.start_battery.stored_kwh
        for h, home in enumerate(households)
    )
    return Optimum(
        cost_inr=float(community),
        eb_import_kwh=total("imp"),
        eb_export_kwh=total("exp"),
        p2p_kwh=total("out"),
        unserved_kwh=total("uns"),
    )
