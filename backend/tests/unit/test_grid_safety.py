"""The safety layer's veto power: leaves a feasible allocation untouched,
curtails an infeasible one until it isn't."""

from __future__ import annotations

import pytest

from app.domain.grid import distflow, safety
from app.domain.grid.network import default_feeder
from app.domain.market.auction import Trade

pytestmark = pytest.mark.unit


def _feeder() -> object:
    return default_feeder([f"h{i}" for i in range(1, 11)])


def _within_limits(network: object, flow: distflow.FlowResult) -> bool:
    thermal_ok = all(
        abs(flow.line_flow_kw[line.id]) <= line.thermal_limit_kw for line in network.lines
    )
    voltage_ok = all(
        network.voltage_min_pu <= v <= network.voltage_max_pu for v in flow.bus_voltage_pu.values()
    )
    return thermal_ok and voltage_ok


def test_a_feasible_allocation_is_left_completely_untouched() -> None:
    network = _feeder()
    # 2 kWh each from h1, h4, h7, h10 to an outside buyer — well inside the
    # calibrated "normal" scenario.
    trades = tuple(
        Trade(buyer_household_id="h2", seller_household_id=seller, kwh=2.0, price_per_kwh=5.0)
        for seller in ("h1", "h4", "h7", "h10")
    )

    result = safety.enforce(network, trades)

    assert result.resolved is True
    assert result.curtailments == ()
    assert result.trades == trades
    assert _within_limits(network, result.flow)


def test_an_infeasible_allocation_is_curtailed_until_safe() -> None:
    network = _feeder()
    # 5 kWh each — the calibrated "heatwave" scenario that breaches voltage.
    trades = tuple(
        Trade(buyer_household_id="h2", seller_household_id=seller, kwh=5.0, price_per_kwh=5.0)
        for seller in ("h1", "h4", "h7", "h10")
    )

    result = safety.enforce(network, trades)

    assert result.resolved is True
    assert len(result.curtailments) > 0
    assert _within_limits(network, result.flow)
    # Something was actually cut, not just relabelled.
    total_before = sum(trade.kwh for trade in trades)
    total_after = sum(trade.kwh for trade in result.trades)
    assert total_after < total_before


def test_curtailment_never_touches_an_unrelated_lateral() -> None:
    """Only the overloaded lateral should lose anything."""
    network = _feeder()
    overloaded = tuple(
        Trade(buyer_household_id="h2", seller_household_id=seller, kwh=5.0, price_per_kwh=5.0)
        for seller in ("h1", "h4", "h7", "h10")
    )
    untouched = (
        Trade(buyer_household_id="h9", seller_household_id="h6", kwh=1.0, price_per_kwh=5.0),
    )

    result = safety.enforce(network, overloaded + untouched)

    remaining_h6_trade = next(t for t in result.trades if t.seller_household_id == "h6")
    assert remaining_h6_trade.kwh == pytest.approx(1.0)


def test_curtailment_reduces_the_largest_offending_trade_first() -> None:
    """A small trade sitting alongside much larger ones on the same
    overloaded lateral should survive untouched — the greedy "cut the
    biggest offender" rule exists specifically so a small trade isn't the
    one sacrificed for a problem it barely contributed to."""
    network = _feeder()
    trades = (
        Trade(buyer_household_id="h2", seller_household_id="h1", kwh=5.0, price_per_kwh=5.0),
        Trade(buyer_household_id="h2", seller_household_id="h4", kwh=0.1, price_per_kwh=5.0),
        Trade(buyer_household_id="h2", seller_household_id="h7", kwh=5.0, price_per_kwh=5.0),
        Trade(buyer_household_id="h2", seller_household_id="h10", kwh=5.0, price_per_kwh=5.0),
    )

    result = safety.enforce(network, trades)

    small_trade = next(t for t in result.trades if t.seller_household_id == "h4")
    assert small_trade.kwh == pytest.approx(0.1)


def test_no_trades_is_trivially_safe() -> None:
    network = _feeder()
    result = safety.enforce(network, ())

    assert result.resolved is True
    assert result.curtailments == ()
    assert result.trades == ()
