"""The evaluation harness: the hindsight optimum matches cases worked out by
hand, the AC check agrees with the linear model where it should, a real
session runs end to end with its invariants intact, and the report renders
every objective."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.domain.battery.model import Battery
from app.domain.grid.network import SUBSTATION_BUS, Line, Network, default_feeder
from app.domain.market.auction import Trade
from app.engine.market_run import SessionMarket
from app.evaluation import __main__ as cli
from app.evaluation.metrics import linear_violations, net_injection, session_metrics, summarise
from app.evaluation.optimum import VOLL_INR_PER_KWH, community_cost, solve_optimum
from app.evaluation.report import render_markdown
from app.evaluation.runner import (
    HouseholdRun,
    Ledger,
    SessionRun,
    SessionSpec,
    run_session,
    scaled_households,
    seed_households,
)
from app.evaluation.sequences import fit_scaler, history_columns, raw_inputs, scale
from app.evaluation.suite import SUITE, mixed
from app.forecasting.features import FEATURE_COLUMNS
from app.simulator.scenarios import Scenario

pytestmark = pytest.mark.unit

_NO_BATTERY = Battery(capacity_kwh=0.01, soc=0.0, max_charge_kw=0.0, max_discharge_kw=0.0)


def _toy_run(*, network: Network | None = None, eb_up: bool = True) -> SessionRun:
    """One hour, two homes, no batteries: h1 makes 4 kW and uses 1, h2 uses
    2 and makes none. EB-only, h1 exports 3 units and h2 imports 2."""
    alone_h1 = Ledger(earned_eb=12.0, eb_export_kwh=3.0) if eb_up else Ledger(curtailed_kwh=3.0)
    alone_h2 = Ledger(paid_eb=20.0, eb_import_kwh=2.0) if eb_up else Ledger(unserved_kwh=2.0)
    return SessionRun(
        spec=SessionSpec("toy", date(2026, 5, 15), 10, 1, Scenario.AUTO),
        network=network or default_feeder(["h1", "h2"]),
        tick_minutes=15,
        retail=(10.0,),
        feed_in=(4.0,),
        eb=(eb_up,),
        eb_by_interval=[eb_up] * 4,
        households={
            "h1": HouseholdRun(
                "h1", _NO_BATTERY, consumption_kw=[1.0] * 4, generation_kw=[4.0] * 4, alone=alone_h1
            ),
            "h2": HouseholdRun(
                "h2", _NO_BATTERY, consumption_kw=[2.0] * 4, generation_kw=[0.0] * 4, alone=alone_h2
            ),
        },
        slots=[],
        slot_seconds=[],
        forecast_seconds=0.0,
        memories={},
    )


# --- the hindsight optimum ------------------------------------------------------


def test_the_optimum_sends_surplus_to_the_neighbour_first() -> None:
    run = _toy_run()
    assert community_cost(run, "alone") == pytest.approx(20.0 - 12.0)
    optimum = solve_optimum(run)
    # h1 covers h2's 2 units and exports the 1 left over: earns ₹4.
    assert optimum.cost_inr == pytest.approx(-4.0, abs=1e-6)
    assert optimum.p2p_kwh == pytest.approx(2.0, abs=1e-6)
    assert optimum.eb_import_kwh == pytest.approx(0.0, abs=1e-6)


def test_the_optimum_respects_the_feeders_thermal_limits() -> None:
    tight = Network(
        lines=(
            Line(f"{SUBSTATION_BUS}->h1", SUBSTATION_BUS, "h1", 0.0015, thermal_limit_kw=1.0),
            Line(f"{SUBSTATION_BUS}->h2", SUBSTATION_BUS, "h2", 0.0015, thermal_limit_kw=1.0),
        )
    )
    optimum = solve_optimum(_toy_run(network=tight))
    # Only 1 kW can cross: h2 imports the other unit, h1 exports 2.
    assert optimum.p2p_kwh == pytest.approx(1.0, abs=1e-6)
    assert optimum.cost_inr == pytest.approx(10.0 - 8.0, abs=1e-6)


def test_during_a_power_cut_the_optimum_serves_load_from_the_neighbour() -> None:
    run = _toy_run(eb_up=False)
    assert community_cost(run, "alone") == pytest.approx(2.0 * VOLL_INR_PER_KWH)
    optimum = solve_optimum(run)
    assert optimum.unserved_kwh == pytest.approx(0.0, abs=1e-6)
    assert optimum.cost_inr == pytest.approx(0.0, abs=1e-6)


# --- the grid checks ------------------------------------------------------------


def test_net_injection_counts_both_sides_of_every_trade() -> None:
    trades = [Trade("h2", "h1", 2.0, 7.0), Trade("h3", "h1", 1.0, 7.0)]
    assert net_injection(trades) == {"h1": 3.0, "h2": -2.0, "h3": -1.0}


def test_the_linear_check_flags_an_overloaded_line() -> None:
    network = default_feeder([f"h{i}" for i in range(1, 11)])
    assert linear_violations(network, {"h1": 2.0, "h2": -2.0})["thermal"] == 0
    assert linear_violations(network, {"h1": 25.0, "h2": -25.0})["thermal"] > 0


def test_ac_power_flow_agrees_with_the_linear_model_at_light_load() -> None:
    pytest.importorskip("pandapower")
    from app.evaluation.ac_check import ac_check

    network = default_feeder([f"h{i}" for i in range(1, 11)])
    light = {"h1": 2.0, "h4": -2.0}
    ac = ac_check(network, light)
    linear = linear_violations(network, light)
    assert ac.converged
    assert ac.thermal_violations == ac.voltage_violations == 0
    assert ac.min_voltage_pu == pytest.approx(linear["min_voltage_pu"], abs=1e-3)
    heavy = ac_check(network, {"h1": 8.0, "h4": 8.0, "h7": 8.0, "h10": -24.0})
    assert heavy.thermal_violations > 0


# --- a real session, end to end -------------------------------------------------

_SHORT = SessionSpec("short", date(2026, 5, 15), 10, 4, Scenario.AUTO, what_ifs=mixed())


@pytest.fixture(scope="module")
def short_run() -> SessionRun:
    return run_session(_SHORT, seed_households(), memories={}, seed=42)


def test_a_session_run_is_deterministic(short_run: SessionRun) -> None:
    again = run_session(_SHORT, seed_households(), memories={}, seed=42)
    for hid, home in short_run.households.items():
        assert again.households[hid].actual.bill == pytest.approx(home.actual.bill)
        assert again.households[hid].alone.bill == pytest.approx(home.alone.bill)


def test_neighbour_trades_balance_and_every_slot_is_timed(short_run: SessionRun) -> None:
    sold = sum(h.actual.p2p_sold_kwh for h in short_run.households.values())
    bought = sum(h.actual.p2p_bought_kwh for h in short_run.households.values())
    assert sold == pytest.approx(bought)
    assert sold > 0  # three homes have no panels at noon in May
    assert len(short_run.slot_seconds) == len(short_run.slots) == _SHORT.horizon_hours
    assert short_run.intervals == _SHORT.horizon_hours * 4


def test_session_metrics_hold_their_invariants(short_run: SessionRun) -> None:
    metrics = session_metrics(short_run, with_ac=False)
    # The agents' own operation is feasible for the optimum, so it can't cost more.
    assert metrics["cost_optimum_inr"] <= metrics["cost_actual_inr"] + 1e-6
    assert metrics["decisions_explained"] == metrics["decisions"] == 10 * _SHORT.horizon_hours
    assert metrics["trades_explained"] == metrics["trades"]
    assert metrics["grid"]["linear_thermal_violations"] == 0
    assert metrics["grid"]["linear_voltage_violations"] == 0
    assert len(metrics["household_bills"]) == 10


def test_the_summary_and_report_cover_every_objective(short_run: SessionRun) -> None:
    metrics = session_metrics(short_run, with_ac=False)
    summary = summarise([metrics], metrics)
    assert set(summary) == {"O2", "O3", "O4", "O5", "O6", "O7"}
    forecast = _fake_forecast()
    summary["O1"] = {"met": False, **forecast["targets"]}
    markdown = render_markdown(
        {
            "generated_utc": "2026-10-07T00:00:00+00:00",
            "runtime_seconds": 1.0,
            "seed": 42,
            "forecast": forecast,
            "sessions": [metrics],
            "scale": metrics,
            "scale_run": False,
            "failures": [{"session": "broken", "error": "RuntimeError()"}],
            "summary": summary,
        }
    )
    for objective in ("O1", "O2", "O3", "O4", "O5", "O6", "O7"):
        assert f"**{objective}**" in markdown
    assert "broken" in markdown


def _fake_forecast() -> dict[str, Any]:
    score = {
        "pinball": 0.1,
        "nmae_p50": 0.3,
        "p10_p90_coverage": 0.8,
        "below_p10": 0.1,
        "below_p90": 0.9,
    }
    by_target = {"consumption_kw": score, "generation_kw": score}
    target = {"nmae_improvement": 0.3, "pinball_skill": 0.5, "calibrated": True, "met": True}
    return {
        "test_rows": 10,
        "test_days": 1,
        "scores": {"lightgbm_calibrated": by_target, "seasonal_naive": by_target},
        "targets": {"consumption_kw": target, "generation_kw": target},
        "lstm": None,
        "met": True,
    }


def test_the_cli_writes_the_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "evaluate_forecaster", _fake_forecast)
    monkeypatch.setattr(cli, "SUITE", (_SHORT,))
    cli.main(["--out", str(tmp_path), "--no-scale", "--no-ac"])
    assert "Results at a glance" in (tmp_path / "evaluation.md").read_text(encoding="utf-8")
    assert (tmp_path / "evaluation.json").exists()


# --- the suite and the scale feeder ---------------------------------------------


def test_the_suite_covers_seasons_weathers_and_what_ifs() -> None:
    assert len(SUITE) == 12
    assert {s.scenario for s in SUITE} == set(Scenario)
    assert any(s.power_cut for s in SUITE)
    assert any(s.peak_surcharge_pct for s in SUITE)
    assert len({s.sim_date.month for s in SUITE}) >= 8


def test_the_mixed_preset_repeats_every_ten_homes() -> None:
    what_ifs = {w.household_id: w for w in mixed(20)}
    assert what_ifs["h3"].panel_derate == what_ifs["h13"].panel_derate == 1.0
    assert what_ifs["h12"].battery_capacity_kwh == 15
    assert "h1" not in what_ifs


def test_a_scaled_feeder_keeps_the_seed_design() -> None:
    homes = scaled_households(25)
    assert [h.id for h in homes[:2]] == ["h1", "h2"]
    assert len({h.solar_capacity_kwp for h in homes}) == 1


def test_a_market_needs_households() -> None:
    with pytest.raises(ValueError, match="at least one"):
        SessionMarket({}, network=default_feeder(["h1"]), names={}, memories={})


# --- LSTM inputs (no PyTorch needed) --------------------------------------------


def test_sequence_inputs_read_forward_in_time() -> None:
    hours = 3
    row: dict[str, float] = dict.fromkeys(FEATURE_COLUMNS, 1.0)
    row |= {"consumption_kw": 2.0, "generation_kw": 0.5}
    for back in range(1, hours + 1):
        row[f"hist_consumption_{back}"] = float(back)
        row[f"hist_generation_{back}"] = float(10 * back)
    frame = pd.DataFrame([row, row])
    inputs = raw_inputs(frame, hours)
    assert history_columns("consumption", hours) == [
        "hist_consumption_3",
        "hist_consumption_2",
        "hist_consumption_1",
    ]
    assert inputs.sequence.shape == (2, hours, 2)
    assert inputs.sequence[0, :, 0].tolist() == [3.0, 2.0, 1.0]  # oldest first
    assert inputs.static.shape == (2, len(FEATURE_COLUMNS))
    scaled = scale(inputs, fit_scaler(inputs))
    assert np.allclose(scaled.static, 0.0)  # constant features: centred, not divided by 0


def test_the_least_possible_export_never_curtails_solar_while_the_eb_is_up() -> None:
    """h1's 3 spare units: 2 cover h2, and with no battery the last one has
    nowhere to go but the EB — throwing solar away is not allowed."""
    floor = solve_optimum(_toy_run(), minimise_export=True)
    assert floor.eb_export_kwh == pytest.approx(1.0, abs=1e-6)


def test_the_auction_never_beats_the_best_matching_of_its_own_orders(
    short_run: SessionRun,
) -> None:
    from app.evaluation.allocative import slot_welfare

    welfare = [slot_welfare(cleared, short_run.network) for cleared in short_run.slots]
    for w in welfare:
        assert w.realised_inr <= w.optimal_inr + 1e-6
    optimal = sum(w.optimal_inr for w in welfare)
    assert optimal > 0
    assert sum(w.realised_inr for w in welfare) / optimal > 0.9
