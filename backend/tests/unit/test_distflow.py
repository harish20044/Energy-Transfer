"""Linearized power flow: the two calibrated scenarios that anchor the
network constants (see app/domain/grid/network.py), plus basic conservation
checks."""

from __future__ import annotations

import pytest

from app.domain.grid import distflow
from app.domain.grid.network import SUBSTATION_BUS, default_feeder

pytestmark = pytest.mark.unit


def _feeder() -> object:
    return default_feeder([f"h{i}" for i in range(1, 11)])


def test_substation_voltage_is_always_the_reference() -> None:
    network = _feeder()
    flow = distflow.solve(network, {})

    assert flow.bus_voltage_pu[SUBSTATION_BUS] == 1.0


def test_zero_injection_everywhere_gives_zero_flow_and_nominal_voltage() -> None:
    network = _feeder()
    flow = distflow.solve(network, {})

    assert all(value == 0.0 for value in flow.line_flow_kw.values())
    assert all(value == pytest.approx(1.0) for value in flow.bus_voltage_pu.values())


def test_a_net_exporter_reverses_flow_toward_the_substation() -> None:
    """Positive net injection (surplus) must show up as negative line flow —
    the reverse-power-flow signature of local solar exceeding local load."""
    network = _feeder()
    flow = distflow.solve(network, {"h1": 3.0})

    line = network.line_to("h1")
    assert flow.line_flow_kw[line.id] < 0


def test_a_net_exporter_raises_its_own_voltage_above_nominal() -> None:
    network = _feeder()
    flow = distflow.solve(network, {"h1": 3.0})

    assert flow.bus_voltage_pu["h1"] > 1.0


def test_a_net_importer_lowers_its_own_voltage_below_nominal() -> None:
    network = _feeder()
    flow = distflow.solve(network, {"h1": -3.0})

    assert flow.bus_voltage_pu["h1"] < 1.0


def test_unrelated_laterals_are_unaffected() -> None:
    """A surge on one lateral must not move voltages on a different one —
    the whole reason curtailment can target just the offending subtree."""
    network = _feeder()
    flow = distflow.solve(network, {"h1": 5.0})

    lateral_two_root = network.children_of(SUBSTATION_BUS)[1]
    assert flow.bus_voltage_pu[lateral_two_root] == pytest.approx(1.0)


def test_normal_trading_scenario_stays_within_statutory_limits() -> None:
    """2 kW export from each of four houses on one lateral — an ordinary
    trading tick, calibrated to sit comfortably inside both limits."""
    network = _feeder()
    injections = {"h1": 2.0, "h4": 2.0, "h7": 2.0, "h10": 2.0}

    flow = distflow.solve(network, injections)

    assert all(abs(kw) <= 20.0 for kw in flow.line_flow_kw.values())
    assert all(0.95 <= v <= 1.05 for v in flow.bus_voltage_pu.values())


def test_stress_scenario_breaches_the_voltage_band() -> None:
    """5 kW export from each of four houses on one lateral — the calibrated
    'heatwave' stress case the safety layer must catch."""
    network = _feeder()
    injections = {"h1": 5.0, "h4": 5.0, "h7": 5.0, "h10": 5.0}

    flow = distflow.solve(network, injections)

    assert any(v > 1.05 for v in flow.bus_voltage_pu.values())
