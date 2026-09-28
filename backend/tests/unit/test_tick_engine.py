"""The pure tick orchestration: net positions become orders, the auction
clears, safety curtails, and the ledger grows by exactly the settled trades."""

from __future__ import annotations

import pytest

from app.domain.battery.model import Battery
from app.domain.battery.policy import BatteryAction
from app.domain.engine.tick import HouseholdTickInput, run_tick
from app.domain.grid.network import default_feeder
from app.domain.ledger.hashchain import verify_chain

pytestmark = pytest.mark.unit


def _battery(soc: float = 0.5) -> Battery:
    return Battery(capacity_kwh=10.0, soc=soc, max_charge_kw=5.0, max_discharge_kw=5.0)


def _network() -> object:
    return default_feeder([f"h{i}" for i in range(1, 11)])


def test_a_surplus_household_sells_to_a_shortfall_household() -> None:
    inputs = (
        HouseholdTickInput(
            household_id="h1",
            consumption_kw=0.5,
            generation_kw=3.0,  # 2.5 kW surplus, battery already full
            battery=_battery(soc=1.0),
            evening_reserve=0.4,
        ),
        HouseholdTickInput(
            household_id="h2",
            consumption_kw=2.0,
            generation_kw=0.0,  # 2.0 kW shortfall, battery already empty
            battery=_battery(soc=0.0),
            evening_reserve=0.4,
        ),
    )

    result = run_tick(
        tick_index=0,
        inputs=inputs,
        network=_network(),
        ledger_chain=(),
        duration_h=0.25,
        feed_in_tariff=3.0,
        retail_tariff=8.0,
        is_evening=False,
    )

    assert result.auction.clearing_price is not None
    assert 3.0 <= result.auction.clearing_price <= 8.0
    assert len(result.safety.trades) == 1
    assert len(result.new_ledger_entries) == 1
    assert verify_chain(result.new_ledger_entries)

    seller_outcome = next(o for o in result.household_outcomes if o.household_id == "h1")
    buyer_outcome = next(o for o in result.household_outcomes if o.household_id == "h2")
    assert seller_outcome.battery_action is BatteryAction.IDLE  # already full
    assert buyer_outcome.battery_action is BatteryAction.IDLE  # already empty


def test_an_unmatched_surplus_settles_with_the_grid() -> None:
    """A lone seller with nobody to buy from exports to the grid instead —
    the market clearing nothing is not an error."""
    inputs = (
        HouseholdTickInput(
            household_id="h1",
            consumption_kw=0.0,
            generation_kw=2.0,
            battery=_battery(soc=1.0),
            evening_reserve=0.4,
        ),
    )

    result = run_tick(
        tick_index=0,
        inputs=inputs,
        network=_network(),
        ledger_chain=(),
        duration_h=0.25,
        feed_in_tariff=3.0,
        retail_tariff=8.0,
        is_evening=False,
    )

    assert result.auction.trades == ()
    assert result.new_ledger_entries == ()
    outcome = result.household_outcomes[0]
    assert outcome.grid_kwh == pytest.approx(-2.0 * 0.25)


def test_ledger_chain_accumulates_across_successive_ticks() -> None:
    inputs = (
        HouseholdTickInput("h1", 0.5, 3.0, _battery(soc=1.0), 0.4),
        HouseholdTickInput("h2", 2.0, 0.0, _battery(soc=0.0), 0.4),
    )
    network = _network()

    first = run_tick(
        tick_index=0,
        inputs=inputs,
        network=network,
        ledger_chain=(),
        duration_h=0.25,
        feed_in_tariff=3.0,
        retail_tariff=8.0,
        is_evening=False,
    )
    chain_after_first = first.new_ledger_entries

    second = run_tick(
        tick_index=1,
        inputs=inputs,
        network=network,
        ledger_chain=chain_after_first,
        duration_h=0.25,
        feed_in_tariff=3.0,
        retail_tariff=8.0,
        is_evening=False,
    )
    full_chain = chain_after_first + second.new_ledger_entries

    assert len(full_chain) == 2
    assert verify_chain(full_chain)
    assert full_chain[1].sequence == 1
    assert full_chain[1].prev_hash == full_chain[0].hash


def test_no_households_is_trivially_a_no_op_tick() -> None:
    result = run_tick(
        tick_index=0,
        inputs=(),
        network=_network(),
        ledger_chain=(),
        duration_h=0.25,
        feed_in_tariff=3.0,
        retail_tariff=8.0,
        is_evening=False,
    )

    assert result.auction.trades == ()
    assert result.household_outcomes == ()
