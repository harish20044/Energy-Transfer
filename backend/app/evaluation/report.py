"""Render the evaluation results as `docs/evaluation.md`."""

from __future__ import annotations

from typing import Any

_TARGET_NAMES = {"consumption_kw": "Load", "generation_kw": "Solar"}
_MODEL_NAMES = {
    "seasonal_naive": "Same hour yesterday (baseline)",
    "lightgbm_raw": "LightGBM, raw quantiles",
    "lightgbm_calibrated": "LightGBM + conformal calibration (served)",
    "lstm_raw": "LSTM, raw quantiles",
    "lstm_calibrated": "LSTM + conformal calibration",
}


def _pct(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value * 100:.{digits}f}%"


def _inr(value: float) -> str:
    sign = "−" if value < 0 else ""
    return f"{sign}₹{abs(value):,.2f}"


def _met(flag: bool) -> str:
    return "**Met**" if flag else "**Not met**"


def render_markdown(results: dict[str, Any]) -> str:
    s = results["summary"]
    forecast = results["forecast"]
    sessions = results["sessions"]
    scale = results["scale"]
    lines: list[str] = []
    add = lines.append

    add("# Evaluation: objectives O1–O7")
    add("")
    add(
        f"Generated {results['generated_utc']} by `python -m app.evaluation` "
        f"(seed {results['seed']}, {results['runtime_seconds'] / 60:.0f} min). "
        "Every figure below is measured, not assumed: the harness runs the app's own forecaster, "
        "agents, market, grid safety layer and delivery code in memory, on a fixed suite of "
        "seeded sessions. Targets are the ones set in [objectives.md](objectives.md)."
    )
    add("")

    # ----------------------------------------------------------------- summary
    o1 = s["O1"]
    load, solar = forecast["targets"]["consumption_kw"], forecast["targets"]["generation_kw"]
    cal = forecast["scores"]["lightgbm_calibrated"]
    o2, o3, o4, o5, o6, o7 = (s[k] for k in ("O2", "O3", "O4", "O5", "O6", "O7"))
    add("## Results at a glance")
    add("")
    add("| Objective | Target | Result | |")
    add("|---|---|---|---|")
    add(
        "| **O1** Forecasting | nMAE at least 25% below same-hour-yesterday; P10 and P90 "
        "calibrated (10% ± 3 pp of actuals below P10, 90% ± 3 pp below P90) | "
        f"nMAE {_pct(load['nmae_improvement'])} lower for load, "
        f"{_pct(solar['nmae_improvement'])} for solar · below P10: "
        f"{_pct(cal['consumption_kw']['below_p10'])} / {_pct(cal['generation_kw']['below_p10'])}"
        f" · below P90: {_pct(cal['consumption_kw']['below_p90'])} / "
        f"{_pct(cal['generation_kw']['below_p90'])} | {_met(o1['met'])} |"
    )
    add(
        "| **O2** Matching efficiency | ≥ 95% of the saving a hindsight-optimal schedule "
        f"could have made | {_pct(o2['efficiency'])} ({_inr(o2['saving_captured_inr'])} of "
        f"{_inr(o2['saving_achievable_inr'])}) | {_met(o2['met'])} |"
    )
    add(
        "| **O3** Autonomy and speed | Every slot clears and settles unattended; clearing an "
        f"hour for {o3['scale_households']} homes takes p95 < 200 ms | "
        f"{_pct(o3['autonomy'], 0)} of slots unattended · p95 "
        f"{o3['latency_ms_scale']['p95']:.0f} ms at {o3['scale_households']} homes "
        f"({o3['latency_ms_10_homes']['p95']:.0f} ms at 10) | {_met(o3['met'])} |"
    )
    add(
        "| **O4** Grid safety | Zero violations in the settled allocation, by the fast linear "
        "check and by full AC power flow | "
        f"{o4['linear_violations']} linear · {o4['ac_violations']} AC "
        f"({o4['ac_slots_checked']} slots checked, {o4['curtailments']} curtailments) | "
        f"{_met(o4['met'])} |"
    )
    add(
        "| **O5** Renewable use | EB export at least 30% lower than EB-only; "
        "self-sufficiency and self-consumption both up | "
        f"export {_pct(o5['export_reduction'])} lower · self-sufficiency "
        f"{_pct(o5['ssr']['eb_only'])} → {_pct(o5['ssr']['with_p2p'])} · self-consumption "
        f"{_pct(o5['scr']['eb_only'])} → {_pct(o5['scr']['with_p2p'])} | {_met(o5['met'])} |"
    )
    add(
        "| **O6** Economic benefit | Mean bill reduction ≥ 10% (band 10–20%); no household "
        "worse off than EB-only | "
        f"{_pct(o6['mean_bill_reduction_net_consumers'])} mean reduction · "
        f"{o6['worse_off']} of {o6['household_sessions']} household-sessions worse off "
        f"(worst {_inr(o6['worst_saving_inr'])}) | {_met(o6['met'])} |"
    )
    add(
        "| **O7** Explainability | 100% of trades carry both parties' decision record and "
        f"rationale | {_pct(o7['coverage'], 0)} of {o7['trades']:,} trades · "
        f"{o7['decisions_explained']:,} of {o7['decisions']:,} decisions | {_met(o7['met'])} |"
    )
    add("")
    met = sum(1 for k in ("O1", "O2", "O3", "O4", "O5", "O6", "O7") if s[k]["met"])
    add(f"**{met} of 7 objectives met.** Where a target is missed, the gap is reported as found.")
    add("")

    # ----------------------------------------------------------------- suite
    add("## The suite")
    add("")
    add(
        "Twelve 24-hour sessions from 6 am on the ten seeded homes, run in order with the agents' "
        "learned memory carried from one to the next, plus one 12-hour session on a 100-home "
        "feeder for the scale test. *Mixed* is the plan page's preset: three homes with no "
        "panels and no battery, three with a 15 kWh battery."
    )
    add("")
    add(
        "| Session | P2P units | Efficiency (O2) | EB export cut (O5) | Community saving | "
        "Worst home | Trades explained |"
    )
    add("|---|---|---|---|---|---|---|")
    for x in [*sessions, *([scale] if results["scale_run"] else [])]:
        alone_x = x["eb_only"]["eb_export_kwh"]
        cut = 1 - x["actual"]["eb_export_kwh"] / alone_x if alone_x > 0 else None
        saving = sum(b["saving_inr"] for b in x["household_bills"])
        worst = min(b["saving_inr"] for b in x["household_bills"])
        add(
            f"| {x['name']} | {x['p2p_kwh']:.1f} | {_pct(x['efficiency'])} | {_pct(cut)} | "
            f"{_inr(saving)} | {_inr(worst)} | {x['trades_explained']}/{x['trades']} |"
        )
    if results["failures"]:
        add("")
        add("Sessions that failed to run:")
        for f in results["failures"]:
            add(f"- {f['session']}: `{f['error']}`")
    add("")

    # ----------------------------------------------------------------- O1
    add("## O1 · Forecasting")
    add("")
    add(
        f"Scored on the {forecast['test_days']} held-out test days of the forecaster's training "
        f"year ({forecast['test_rows']:,} rows, every horizon from 1 to 24 hours), which no model "
        "saw while training or calibrating. Every model is scored by the same function "
        "(`app.forecasting.model.score_quantiles`). Pinball loss and nMAE: lower is better. "
        "Coverage and calibration count daylight hours only for solar."
    )
    add("")
    add(
        "| Model | Target | Pinball (kW) | nMAE of P50 | P10–P90 coverage | Below P10 | Below P90 |"
    )
    add("|---|---|---|---|---|---|---|")
    for key, label in _MODEL_NAMES.items():
        if key not in forecast["scores"]:
            continue
        for target, m in forecast["scores"][key].items():
            add(
                f"| {label} | {_TARGET_NAMES[target]} | {m['pinball']:.4f} | "
                f"{m['nmae_p50']:.3f} | {_pct(m['p10_p90_coverage'])} | {_pct(m['below_p10'])} | "
                f"{_pct(m['below_p90'])} |"
            )
    add("")
    lstm = forecast.get("lstm")
    if lstm:
        add(
            f"The LSTM ({lstm['model']}, {lstm['parameters']:,} parameters, {lstm['epochs']} "
            f"epochs, {lstm['train_seconds'] / 60:.0f} min on CPU, PyTorch {lstm['torch']}) is "
            "trained on the same training days and calibrated on the same calibration days as "
            "LightGBM (`app.evaluation.lstm`). It is an offline benchmark and is never served."
        )
    else:
        add(
            "The LSTM benchmark has not been run on this machine yet: "
            "`docker compose --profile bench run --rm bench`."
        )
    add("")

    # ----------------------------------------------------------------- O2
    add("## O2 · Matching efficiency")
    add("")
    add(
        "The benchmark is the best any mechanism could have done: a linear program "
        "(`app.evaluation.optimum`) that knows every home's actual load and solar in advance "
        "and schedules every battery, every neighbour exchange and every EB import and export, "
        "within the same battery physics and the same grid constraints the safety layer "
        "enforces. Payments between neighbours are transfers, so community welfare is the "
        "community's net EB bill (plus ₹50 per unserved unit, minus charge left in the batteries "
        "at the feed-in tariff). Efficiency is the share of the achievable saving over EB-only "
        "that the agents captured: (EB-only − actual) / (EB-only − optimum), pooled over the "
        "suite. The gap is the price of committing hours ahead on forecasts, in hourly blocks, "
        "instead of knowing the future."
    )
    add("")
    add("| Session | EB-only | Agents | Hindsight optimum | Efficiency |")
    add("|---|---|---|---|---|")
    for x in sessions:
        add(
            f"| {x['name']} | {_inr(x['cost_eb_only_inr'])} | {_inr(x['cost_actual_inr'])} | "
            f"{_inr(x['cost_optimum_inr'])} | {_pct(x['efficiency'])} |"
        )
    add("")

    # ----------------------------------------------------------------- O3
    add("## O3 · Autonomy and speed")
    add("")
    add(
        "Latency is wall-clock time to clear one hourly slot: every agent's decision graph runs, "
        "households negotiate, the auction clears and grid safety checks the result. "
        "Forecasting happens once per session, before the first slot, and is reported "
        "separately."
    )
    add("")
    add("| Feeder | Slots | p50 | p95 | Max | Forecasting, whole session |")
    add("|---|---|---|---|---|---|")
    ten = o3["latency_ms_10_homes"]
    mean_forecast = sum(x["forecast_seconds"] for x in sessions) / max(len(sessions), 1)
    add(
        f"| 10 homes (suite) | {sum(x['slots'] for x in sessions)} | {ten['p50']:.0f} ms | "
        f"{ten['p95']:.0f} ms | {ten['max']:.0f} ms | "
        f"{mean_forecast:.1f} s per session |"
    )
    big = o3["latency_ms_scale"]
    add(
        f"| {o3['scale_households']} homes | {scale['slots']} | {big['p50']:.0f} ms | "
        f"{big['p95']:.0f} ms | {big['max']:.0f} ms | {scale['forecast_seconds']:.1f} s |"
    )
    add("")
    add(
        f"Autonomy: {_pct(o3['autonomy'], 0)} of planned slots cleared and were delivered with no "
        f"human input; {o3['failed_sessions']} sessions failed."
    )
    add("")

    # ----------------------------------------------------------------- O4
    add("## O4 · Grid safety")
    add("")
    add(
        "Every settled slot is re-checked twice: by the same linearised DistFlow the safety "
        "layer uses, and by a full AC power flow (pandapower, Newton–Raphson; "
        "`app.evaluation.ac_check`) on the same feeder and the same injections, with line "
        "reactance the linear model ignores. The injections are the safety layer's own model: "
        "the settled neighbour trades."
    )
    add("")
    add(
        "| Feeder | Slots AC-checked | Curtailments | Max line loading (linear / AC) | "
        "Lowest voltage (linear / AC) | Highest voltage (linear / AC) | "
        "Violations (linear / AC) |"
    )
    add("|---|---|---|---|---|---|---|")
    for label, group in (
        ("10 homes (suite)", sessions),
        (f"{o3['scale_households']} homes", [scale]),
    ):
        grids = [x["grid"] for x in group]
        add(
            f"| {label} | {sum(g['ac_slots_checked'] for g in grids)} | "
            f"{sum(g['curtailments'] for g in grids)} | "
            f"{max(g['max_linear_loading_pct'] for g in grids):.0f}% / "
            f"{max(g['max_ac_loading_pct'] for g in grids):.0f}% | "
            f"{min(g['min_linear_voltage_pu'] for g in grids):.3f} / "
            f"{min(g['min_ac_voltage_pu'] for g in grids):.3f} pu | "
            f"{max(g['max_linear_voltage_pu'] for g in grids):.3f} / "
            f"{max(g['max_ac_voltage_pu'] for g in grids):.3f} pu | "
            f"{sum(g['linear_thermal_violations'] + g['linear_voltage_violations'] for g in grids)}"
            f" / {sum(g['ac_thermal_violations'] + g['ac_voltage_violations'] for g in grids)} |"
        )
    add("")
    add(
        f"Largest gap between the linear and AC voltage at any bus: "
        f"{o4['max_ac_linear_voltage_gap_pu']:.4f} pu. Statutory band: 0.95–1.05 pu."
    )
    add("")

    # ----------------------------------------------------------------- O5 / O6
    add("## O5 · Renewable use and O6 · Economic benefit")
    add("")
    add(
        "Both are measured against the same counterfactual: the same hours, the same weather and "
        "families, with each home dealing only with the EB (its battery still doing "
        "self-consumption). Self-sufficiency = load met without the EB / total load. "
        "Self-consumption = local solar used locally / total solar."
    )
    add("")
    add(
        f"- EB export over the suite: {o5['eb_export_kwh']['eb_only']:,.0f} units EB-only, "
        f"{o5['eb_export_kwh']['with_p2p']:,.0f} with neighbours trading."
    )
    add(
        f"- Bill reduction is averaged over the {o6['net_consumer_household_sessions']} "
        "household-sessions that are net buyers on an EB-only bill (a percentage of a negative "
        "bill means nothing); net sellers' gains are in the community saving of "
        f"{_inr(o6['community_saving_inr'])} over the suite."
    )
    add("")

    # ----------------------------------------------------------------- limits
    add("## What these results do not show")
    add("")
    add(
        "- **Synthetic data.** Every session runs on the calibrated Chennai simulator "
        "([ADR-0007](adr/0007-calibrated-synthetic-chennai-data.md)), not metered homes."
    )
    add(
        "- **The grid model counts neighbour trades only.** The safety layer and both checks "
        "load the feeder with the settled P2P exchanges, not each home's whole net load; the "
        "EB's own supply is the distribution company's to plan."
    )
    add(
        "- **One suite.** Twelve sessions cover the seasons, weathers and what-ifs a user can set, "
        "but they are one seed. Results on other seeds will differ in the details."
    )
    add("")
    add("## Reproduce")
    add("")
    add("```")
    add("docker exec energy-backend python -m app.evaluation          # this report")
    add("docker compose --profile bench run --rm bench                 # the LSTM benchmark")
    add("```")
    add("")
    return "\n".join(lines)
