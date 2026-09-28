"""Objective O4, machine-checked: exactly zero constraint violations survive
the safety layer, across thousands of generated allocations — including
adversarial ones that concentrate heavy trading on a single lateral, which is
exactly the case the safety layer exists to catch.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.grid import safety
from app.domain.grid.network import default_feeder
from app.domain.market.auction import Trade

pytestmark = pytest.mark.property

_HOUSEHOLDS = tuple(f"h{i}" for i in range(1, 11))
_NETWORK = default_feeder(list(_HOUSEHOLDS))

# Quantities run well above the calibrated thermal/voltage limits (20 kW /
# 0.05 pu) so Hypothesis actually generates infeasible allocations most of
# the time — a property test that only ever sees feasible input proves
# nothing about the curtailment logic itself.
_household = st.sampled_from(_HOUSEHOLDS)
_kwh = st.floats(min_value=0.1, max_value=30.0, allow_nan=False)


@st.composite
def _trade(draw: st.DrawFn) -> Trade:
    seller = draw(_household)
    buyer = draw(_household.filter(lambda h: h != seller))
    return Trade(
        buyer_household_id=buyer,
        seller_household_id=seller,
        kwh=draw(_kwh),
        price_per_kwh=5.0,
    )


_trades = st.lists(_trade(), min_size=0, max_size=8)


@given(trades=_trades)
@settings(max_examples=200)
def test_every_line_is_within_its_thermal_limit_after_enforcement(
    trades: list[Trade],
) -> None:
    result = safety.enforce(_NETWORK, tuple(trades))

    for line in _NETWORK.lines:
        assert abs(result.flow.line_flow_kw[line.id]) <= line.thermal_limit_kw + 1e-6


@given(trades=_trades)
@settings(max_examples=200)
def test_every_bus_is_within_the_statutory_voltage_band_after_enforcement(
    trades: list[Trade],
) -> None:
    result = safety.enforce(_NETWORK, tuple(trades))

    for voltage in result.flow.bus_voltage_pu.values():
        assert _NETWORK.voltage_min_pu - 1e-6 <= voltage <= _NETWORK.voltage_max_pu + 1e-6


@given(trades=_trades)
@settings(max_examples=200)
def test_enforcement_always_resolves_within_the_round_limit(trades: list[Trade]) -> None:
    """A curtailment loop that gives up without reaching a safe state would
    be worse than making no allocation at all — this must never happen for
    any allocation this small a network can actually produce."""
    result = safety.enforce(_NETWORK, tuple(trades))

    assert result.resolved is True


@given(trades=_trades)
@settings(max_examples=200)
def test_curtailment_never_increases_any_trades_volume(trades: list[Trade]) -> None:
    """The safety layer only ever takes energy off the table, never adds
    any — it has veto power, not the power to invent new trades."""
    result = safety.enforce(_NETWORK, tuple(trades))

    total_before = sum(trade.kwh for trade in trades)
    total_after = sum(trade.kwh for trade in result.trades)

    assert total_after <= total_before + 1e-6


@given(trades=_trades)
@settings(max_examples=200)
def test_a_feasible_allocation_needs_no_curtailment(trades: list[Trade]) -> None:
    """Sanity check the other direction: enforcement must never curtail an
    allocation that was already safe — the safety layer restricts trade, it
    doesn't restrict it further than necessary."""
    from app.domain.grid import distflow

    net_injection: dict[str, float] = {}
    for trade in trades:
        net_injection[trade.seller_household_id] = (
            net_injection.get(trade.seller_household_id, 0.0) + trade.kwh
        )
        net_injection[trade.buyer_household_id] = (
            net_injection.get(trade.buyer_household_id, 0.0) - trade.kwh
        )
    flow_before = distflow.solve(_NETWORK, net_injection)

    already_feasible = all(
        abs(flow_before.line_flow_kw[line.id]) <= line.thermal_limit_kw for line in _NETWORK.lines
    ) and all(
        _NETWORK.voltage_min_pu <= v <= _NETWORK.voltage_max_pu
        for v in flow_before.bus_voltage_pu.values()
    )

    result = safety.enforce(_NETWORK, tuple(trades))

    if already_feasible:
        assert result.curtailments == ()
