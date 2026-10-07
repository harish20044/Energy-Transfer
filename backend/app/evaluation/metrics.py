"""Objectives O2-O7, measured on completed session runs (O1 lives in
`app.evaluation.forecast`). Every figure is computed from what the runs
recorded — trades, deliveries, decisions, timings — never assumed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from app.domain.grid import distflow
from app.domain.grid.network import Network
from app.domain.market.auction import Trade
from app.evaluation.ac_check import ac_check
from app.evaluation.allocative import slot_welfare
from app.evaluation.optimum import community_cost, solve_optimum
from app.evaluation.runner import SessionRun

_EPS = 1e-6
# Individual rationality tolerance: a rounding paisa is not a loss.
_IR_TOLERANCE_INR = 0.01


def net_injection(trades: Sequence[Trade]) -> dict[str, float]:
    """Each household's net export to neighbours for the slot (kW average)."""
    net: dict[str, float] = {}
    for trade in trades:
        net[trade.seller_household_id] = net.get(trade.seller_household_id, 0.0) + trade.kwh
        net[trade.buyer_household_id] = net.get(trade.buyer_household_id, 0.0) - trade.kwh
    return net


def linear_violations(network: Network, injection: dict[str, float]) -> dict[str, float]:
    flow = distflow.solve(network, injection)
    loading = [
        abs(flow.line_flow_kw[line.id]) / line.thermal_limit_kw * 100.0 for line in network.lines
    ]
    voltages = [v for bus, v in flow.bus_voltage_pu.items() if bus in network.household_buses()]
    return {
        "thermal": float(
            sum(
                abs(flow.line_flow_kw[line.id]) > line.thermal_limit_kw + _EPS
                for line in network.lines
            )
        ),
        "voltage": float(
            sum(
                v < network.voltage_min_pu - _EPS or v > network.voltage_max_pu + _EPS
                for v in voltages
            )
        ),
        "max_loading_pct": max(loading) if loading else 0.0,
        "min_voltage_pu": min(voltages) if voltages else 1.0,
        "max_voltage_pu": max(voltages) if voltages else 1.0,
    }


def _community(run: SessionRun, which: str) -> dict[str, float]:
    load = sum(sum(h.consumption_kw) for h in run.households.values()) * run.interval_hours
    gen = sum(sum(h.generation_kw) for h in run.households.values()) * run.interval_hours
    ledgers = [getattr(h, which) for h in run.households.values()]
    imported = sum(lg.eb_import_kwh for lg in ledgers)
    exported = sum(lg.eb_export_kwh for lg in ledgers)
    unserved = sum(lg.unserved_kwh for lg in ledgers)
    curtailed = sum(lg.curtailed_kwh for lg in ledgers)
    return {
        "load_kwh": load,
        "generation_kwh": gen,
        "eb_import_kwh": imported,
        "eb_export_kwh": exported,
        "unserved_kwh": unserved,
        "curtailed_kwh": curtailed,
        # Self-sufficiency: load met without the EB (and actually served).
        "ssr": (load - imported - unserved) / load if load > 0 else 0.0,
        # Self-consumption: local generation used locally, not exported or wasted.
        "scr": (gen - exported - curtailed) / gen if gen > 0 else 0.0,
    }


def session_metrics(run: SessionRun, *, with_ac: bool = True) -> dict[str, Any]:
    """Every per-session figure behind O2-O7."""
    # O2: the auction's allocative efficiency — welfare from the orders,
    # against the best matching of the same orders within the grid limits.
    welfare = [slot_welfare(cleared, run.network) for cleared in run.slots]
    # Beside it: the share of the saving a perfect-foresight schedule makes
    # that the agents captured — the price of forecasting, not of the auction.
    optimum = solve_optimum(run)
    alone_cost = community_cost(run, "alone")
    actual_cost = community_cost(run, "actual")
    achievable = alone_cost - optimum.cost_inr
    captured = alone_cost - actual_cost
    # O5: the least EB export any schedule could reach, physics permitting.
    export_floor = solve_optimum(run, minimise_export=True).eb_export_kwh

    # O4: the settled allocation, slot by slot, linear and AC.
    linear_thermal = linear_voltage = 0
    ac_thermal = ac_voltage = ac_unconverged = ac_slots = 0
    curtailments = unresolved = 0
    worst_linear_loading = worst_ac_loading = 0.0
    min_linear_v = min_ac_v = 1.0
    max_linear_v = max_ac_v = 1.0
    max_v_gap = 0.0
    for cleared in run.slots:
        safety = cleared.clearing.safety
        curtailments += len(safety.curtailments)
        unresolved += int(not safety.resolved)
        injection = net_injection(safety.trades)
        linear = linear_violations(run.network, injection)
        linear_thermal += int(linear["thermal"])
        linear_voltage += int(linear["voltage"])
        worst_linear_loading = max(worst_linear_loading, linear["max_loading_pct"])
        min_linear_v = min(min_linear_v, linear["min_voltage_pu"])
        max_linear_v = max(max_linear_v, linear["max_voltage_pu"])
        if with_ac and safety.trades:
            ac = ac_check(run.network, injection)
            ac_slots += 1
            if not ac.converged:
                ac_unconverged += 1
                continue
            ac_thermal += ac.thermal_violations
            ac_voltage += ac.voltage_violations
            worst_ac_loading = max(worst_ac_loading, ac.max_loading_pct)
            min_ac_v = min(min_ac_v, ac.min_voltage_pu)
            max_ac_v = max(max_ac_v, ac.max_voltage_pu)
            max_v_gap = max(
                max_v_gap,
                abs(ac.min_voltage_pu - linear["min_voltage_pu"]),
                abs(ac.max_voltage_pu - linear["max_voltage_pu"]),
            )

    # O6: each household's bill with neighbours vs the EB alone.
    households = []
    for hid, h in run.households.items():
        alone_bill, actual_bill = h.alone.bill, h.actual.bill
        households.append(
            {
                "household_id": hid,
                "bill_eb_only_inr": alone_bill,
                "bill_with_p2p_inr": actual_bill,
                "saving_inr": alone_bill - actual_bill,
                "reduction": (alone_bill - actual_bill) / alone_bill if alone_bill > 0 else None,
            }
        )

    # O7: every trade carries both parties' decision record and rationale.
    trades = explained = decisions = decisions_explained = 0
    for cleared in run.slots:
        for part in cleared.households.values():
            decisions += 1
            decisions_explained += int(bool(part.decision.message and part.decision.reasons))
        for trade in cleared.clearing.safety.trades:
            trades += 1
            parties = (
                cleared.households.get(trade.buyer_household_id),
                cleared.households.get(trade.seller_household_id),
            )
            explained += int(
                all(
                    p is not None
                    and bool(p.decision.message)
                    and bool(p.decision.reasons)
                    and bool(p.outcome)
                    for p in parties
                )
            )

    return {
        "name": run.spec.name,
        "households": len(run.households),
        "hours": run.spec.horizon_hours,
        "p2p_kwh": sum(h.actual.p2p_sold_kwh for h in run.households.values()),
        "optimum_p2p_kwh": optimum.p2p_kwh,
        "cost_eb_only_inr": alone_cost,
        "cost_actual_inr": actual_cost,
        "cost_optimum_inr": optimum.cost_inr,
        "saving_captured_inr": captured,
        "saving_achievable_inr": achievable,
        "efficiency": captured / achievable if achievable > _EPS else None,
        "allocative_realised_inr": sum(w.realised_inr for w in welfare),
        "allocative_optimal_inr": sum(w.optimal_inr for w in welfare),
        "eb_export_floor_kwh": export_floor,
        "eb_only": _community(run, "alone"),
        "actual": _community(run, "actual"),
        "slot_seconds": list(run.slot_seconds),
        "forecast_seconds": run.forecast_seconds,
        "slots": len(run.slots),
        "grid": {
            "linear_thermal_violations": linear_thermal,
            "linear_voltage_violations": linear_voltage,
            "ac_slots_checked": ac_slots,
            "ac_unconverged": ac_unconverged,
            "ac_thermal_violations": ac_thermal,
            "ac_voltage_violations": ac_voltage,
            "curtailments": curtailments,
            "unresolved_slots": unresolved,
            "max_linear_loading_pct": worst_linear_loading,
            "max_ac_loading_pct": worst_ac_loading,
            "min_linear_voltage_pu": min_linear_v,
            "min_ac_voltage_pu": min_ac_v,
            "max_linear_voltage_pu": max_linear_v,
            "max_ac_voltage_pu": max_ac_v,
            "max_ac_linear_voltage_gap_pu": max_v_gap,
        },
        "household_bills": households,
        "trades": trades,
        "trades_explained": explained,
        "decisions": decisions,
        "decisions_explained": decisions_explained,
    }


def summarise(
    sessions: Sequence[dict[str, Any]],
    scale: dict[str, Any],
    *,
    failed_sessions: int = 0,
) -> dict[str, Any]:
    """O2-O7 against their targets, across the whole suite."""
    achievable = sum(s["saving_achievable_inr"] for s in sessions)
    captured = sum(s["saving_captured_inr"] for s in sessions)
    foresight = captured / achievable if achievable > _EPS else None

    def allocative(group: Sequence[dict[str, Any]]) -> float | None:
        optimal = sum(s["allocative_optimal_inr"] for s in group)
        realised = sum(s["allocative_realised_inr"] for s in group)
        return realised / optimal if optimal > _EPS else None

    efficiency = allocative(sessions)

    slots_planned = sum(s["hours"] for s in sessions) + scale["hours"]
    slots_cleared = sum(s["slots"] for s in sessions) + scale["slots"]
    suite_latency = np.array([x for s in sessions for x in s["slot_seconds"]]) * 1000
    scale_latency = np.array(scale["slot_seconds"]) * 1000

    grid = [s["grid"] for s in (*sessions, scale)]

    def total(key: str) -> int:
        return int(sum(g[key] for g in grid))

    export_alone = sum(s["eb_only"]["eb_export_kwh"] for s in sessions)
    export_actual = sum(s["actual"]["eb_export_kwh"] for s in sessions)

    def pooled(which: str, numerator: str) -> float:
        load = sum(s[which]["load_kwh"] for s in sessions)
        gen = sum(s[which]["generation_kwh"] for s in sessions)
        if numerator == "ssr":
            met = sum(
                s[which]["load_kwh"] - s[which]["eb_import_kwh"] - s[which]["unserved_kwh"]
                for s in sessions
            )
            return met / load if load > 0 else 0.0
        used = sum(
            s[which]["generation_kwh"] - s[which]["eb_export_kwh"] - s[which]["curtailed_kwh"]
            for s in sessions
        )
        return used / gen if gen > 0 else 0.0

    bills = [b for s in sessions for b in s["household_bills"]]
    worse_off_days = [b for b in bills if b["saving_inr"] < -_IR_TOLERANCE_INR]
    # O6 per household over the whole evaluation period, as objectives.md
    # defines it: each home's bill with neighbours vs with the EB alone.
    season: dict[str, list[float]] = {}
    for b in bills:
        totals = season.setdefault(b["household_id"], [0.0, 0.0])
        totals[0] += b["bill_eb_only_inr"]
        totals[1] += b["saving_inr"]
    households: list[dict[str, Any]] = [
        {
            "household_id": hid,
            "bill_eb_only_inr": bill,
            "saving_inr": saving,
            # A share of a negative bill (a net seller's earnings) means nothing.
            "reduction": saving / bill if bill > 0 else None,
        }
        for hid, (bill, saving) in season.items()
    ]
    buyers = [h for h in households if h["reduction"] is not None]
    worse_off = [h for h in households if h["saving_inr"] < -_IR_TOLERANCE_INR]

    trades = sum(s["trades"] for s in sessions) + scale["trades"]
    explained = sum(s["trades_explained"] for s in sessions) + scale["trades_explained"]
    decisions = sum(s["decisions"] for s in sessions) + scale["decisions"]
    decisions_explained = (
        sum(s["decisions_explained"] for s in sessions) + scale["decisions_explained"]
    )

    o5_ssr = (pooled("eb_only", "ssr"), pooled("actual", "ssr"))
    o5_scr = (pooled("eb_only", "scr"), pooled("actual", "scr"))
    export_reduction = 1.0 - export_actual / export_alone if export_alone > 0 else 0.0
    export_floor = sum(s["eb_export_floor_kwh"] for s in sessions)
    possible_reduction = 1.0 - export_floor / export_alone if export_alone > 0 else 0.0
    share_of_possible = export_reduction / possible_reduction if possible_reduction > _EPS else 0.0
    mean_reduction = float(np.mean([h["reduction"] for h in buyers])) if buyers else 0.0
    p95_scale = float(np.percentile(scale_latency, 95)) if len(scale_latency) else 0.0

    return {
        "O2": {
            "efficiency": efficiency,
            "scale_efficiency": allocative([scale]),
            "welfare_realised_inr": sum(s["allocative_realised_inr"] for s in sessions),
            "welfare_optimal_inr": sum(s["allocative_optimal_inr"] for s in sessions),
            "foresight_efficiency": foresight,
            "saving_captured_inr": captured,
            "saving_achievable_inr": achievable,
            "met": efficiency is not None and efficiency >= 0.95,
        },
        "O3": {
            "autonomy": slots_cleared / slots_planned if slots_planned else 0.0,
            "failed_sessions": failed_sessions,
            "latency_ms_10_homes": _percentiles(suite_latency),
            "latency_ms_scale": _percentiles(scale_latency),
            "scale_households": scale["households"],
            "met": failed_sessions == 0 and slots_cleared == slots_planned and p95_scale < 200.0,
        },
        "O4": {
            "linear_violations": total("linear_thermal_violations")
            + total("linear_voltage_violations"),
            "ac_violations": total("ac_thermal_violations") + total("ac_voltage_violations"),
            "ac_thermal_violations": total("ac_thermal_violations"),
            "ac_voltage_violations": total("ac_voltage_violations"),
            "ac_slots_checked": total("ac_slots_checked"),
            "ac_unconverged": total("ac_unconverged"),
            "curtailments": total("curtailments"),
            "unresolved_slots": total("unresolved_slots"),
            "max_ac_linear_voltage_gap_pu": max(g["max_ac_linear_voltage_gap_pu"] for g in grid),
            "met": total("linear_thermal_violations") + total("linear_voltage_violations") == 0
            and total("ac_thermal_violations") + total("ac_voltage_violations") == 0
            and total("ac_unconverged") == 0,
        },
        "O5": {
            "export_reduction": export_reduction,
            "possible_reduction": possible_reduction,
            "share_of_possible": share_of_possible,
            "eb_export_kwh": {
                "eb_only": export_alone,
                "with_p2p": export_actual,
                "least_possible": export_floor,
            },
            "ssr": {"eb_only": o5_ssr[0], "with_p2p": o5_ssr[1]},
            "scr": {"eb_only": o5_scr[0], "with_p2p": o5_scr[1]},
            "met": share_of_possible >= 0.30 and o5_ssr[1] > o5_ssr[0] and o5_scr[1] > o5_scr[0],
        },
        "O6": {
            "mean_bill_reduction_net_buyers": mean_reduction,
            "households": households,
            "net_buyer_households": len(buyers),
            "worse_off_households": len(worse_off),
            "household_days": len(bills),
            "household_days_worse_off": len(worse_off_days),
            "worst_day_saving_inr": min((b["saving_inr"] for b in bills), default=0.0),
            "community_saving_inr": sum(b["saving_inr"] for b in bills),
            "met": mean_reduction >= 0.10 and not worse_off,
        },
        "O7": {
            "trades": trades,
            "trades_explained": explained,
            "coverage": explained / trades if trades else 1.0,
            "decisions": decisions,
            "decisions_explained": decisions_explained,
            "met": explained == trades and decisions_explained == decisions,
        },
    }


def _percentiles(values_ms: np.ndarray) -> dict[str, float]:
    if len(values_ms) == 0:
        return {"p50": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "p50": float(np.percentile(values_ms, 50)),
        "p95": float(np.percentile(values_ms, 95)),
        "max": float(values_ms.max()),
    }
