"""The pure pieces of a planning session: projecting a battery across the
hours ahead, clearing one hourly slot with the EB standing behind every
household, and delivering an interval against its contract."""

from __future__ import annotations

import pytest

from app.domain.battery.model import Battery
from app.domain.battery.schedule import project, spare_storage_kwh, storable_kwh
from app.domain.grid.network import default_feeder
from app.domain.market.orderbook import Side
from app.domain.market.slot_market import SlotOrder, clear_slot
from app.domain.settlement.delivery import deliver

pytestmark = pytest.mark.unit

FIT, RETAIL = 3.61, 10.50
NETWORK = default_feeder([f"h{i}" for i in range(1, 11)])


def _battery(soc: float, capacity: float = 10.0) -> Battery:
    return Battery(capacity_kwh=capacity, soc=soc, max_charge_kw=3.0, max_discharge_kw=3.0)


# --- battery projection ------------------------------------------------------


def test_surplus_charges_then_spills_once_full() -> None:
    plans = project(_battery(0.9), [2.0, 2.0], floor_kwh=[0.5, 0.5])
    assert plans[0].charge_kwh > 0
    assert plans[0].spill_kwh > 0  # only ~1 kWh of headroom
    assert plans[1].spill_kwh == pytest.approx(2.0)


def test_deficit_drains_to_the_floor_then_falls_short() -> None:
    plans = project(_battery(0.3), [-2.0, -2.0], floor_kwh=[0.5, 0.5])
    assert plans[0].discharge_kwh == pytest.approx(2.0)
    assert plans[1].short_kwh == pytest.approx(1.5)  # 3 kWh stored, floor 0.5
    assert plans[1].stored_end_kwh == pytest.approx(0.5)


def test_spare_storage_leaves_enough_for_later_needs() -> None:
    battery = _battery(0.8)  # 8 kWh
    plans = project(battery, [0.0, -2.0, -2.0], floor_kwh=[0.5] * 3)
    spare = spare_storage_kwh(plans, 0, sale_floor_kwh=4.0, max_discharge_kwh=3.0)
    # 8 - 4 needed later = 4 at the lowest point, less the 4 kWh floor.
    assert spare == pytest.approx(0.0)
    spare_low_floor = spare_storage_kwh(plans, 0, sale_floor_kwh=1.0, max_discharge_kwh=3.0)
    assert spare_low_floor == pytest.approx(3.0)


def test_storable_only_up_to_a_later_shortfall_and_the_headroom() -> None:
    battery = _battery(0.5)
    plans = project(battery, [0.0, -8.0], floor_kwh=[0.5, 0.5])
    need_later = plans[1].short_kwh
    assert need_later > 0
    storable = storable_kwh(plans, 0, capacity_kwh=10.0, max_charge_kwh=3.0)
    assert 0 < storable <= min(3.0, need_later)
    assert (
        storable_kwh(
            project(battery, [0.0, 0.0], floor_kwh=[0.5, 0.5]),
            0,
            capacity_kwh=10.0,
            max_charge_kwh=3.0,
        )
        == 0.0
    )


# --- slot market ---------------------------------------------------------------


def test_neighbours_trade_inside_the_band() -> None:
    clearing = clear_slot(
        0,
        [
            SlotOrder("h1", Side.ASK, 2.0, FIT, firm=True),
            SlotOrder("h2", Side.BID, 1.5, RETAIL, firm=True),
        ],
        network=NETWORK,
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
        eb_available=True,
    )
    assert clearing.matched_kwh("h2", Side.BID) == pytest.approx(1.5)
    assert all(FIT <= t.price_per_kwh <= RETAIL for t in clearing.safety.trades)


def test_the_eb_takes_firm_leftovers_at_its_tariffs() -> None:
    clearing = clear_slot(
        0,
        [
            SlotOrder("h1", Side.ASK, 2.0, FIT, firm=True),
            SlotOrder("h2", Side.BID, 0.5, RETAIL, firm=True),
            SlotOrder("h3", Side.BID, 5.0, RETAIL, firm=True),
        ],
        network=NETWORK,
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
        eb_available=True,
    )
    bought_from_eb = sum(f.kwh for f in clearing.eb_flows if f.side is Side.BID)
    assert bought_from_eb == pytest.approx(5.5 - 2.0)
    assert all(f.price == RETAIL for f in clearing.eb_flows if f.side is Side.BID)


def test_optional_orders_never_fall_back_to_the_eb() -> None:
    clearing = clear_slot(
        0,
        [
            SlotOrder("h1", Side.BID, 3.0, 9.0, firm=False),  # buy-to-store
            SlotOrder("h2", Side.ASK, 2.0, 6.0, firm=False),  # spare stored charge
        ],
        network=NETWORK,
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
        eb_available=True,
    )
    assert clearing.eb_flows == ()


def test_during_a_power_cut_firm_demand_goes_unserved() -> None:
    clearing = clear_slot(
        0,
        [SlotOrder("h1", Side.BID, 2.0, RETAIL, firm=True)],
        network=NETWORK,
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
        eb_available=False,
    )
    assert clearing.eb_flows == ()
    assert clearing.unserved == (("h1", 2.0),)


def test_limits_outside_the_band_are_clamped() -> None:
    clearing = clear_slot(
        0,
        [
            SlotOrder("h1", Side.ASK, 1.0, 1.0, firm=True),  # below feed-in
            SlotOrder("h2", Side.BID, 1.0, 50.0, firm=True),  # above retail
        ],
        network=NETWORK,
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
        eb_available=True,
    )
    assert all(FIT <= t.price_per_kwh <= RETAIL for t in clearing.safety.trades)


def test_a_household_may_not_place_two_orders_on_one_side() -> None:
    with pytest.raises(ValueError, match="more than one"):
        clear_slot(
            0,
            [
                SlotOrder("h1", Side.BID, 1.0, RETAIL, firm=True),
                SlotOrder("h1", Side.BID, 1.0, 9.0, firm=False),
            ],
            network=NETWORK,
            feed_in_tariff=FIT,
            retail_tariff=RETAIL,
            eb_available=True,
        )


def test_zero_quantity_orders_are_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        clear_slot(
            0,
            [SlotOrder("h1", Side.BID, 0.0, RETAIL, firm=True)],
            network=NETWORK,
            feed_in_tariff=FIT,
            retail_tariff=RETAIL,
            eb_available=True,
        )


# --- delivery --------------------------------------------------------------------


def test_a_seller_short_of_its_contract_covers_it_from_the_battery_then_the_eb() -> None:
    delivery = deliver(
        _battery(0.06),  # almost empty
        generation_kw=1.0,
        consumption_kw=0.5,
        contracted_export_kw=2.0,
        duration_h=1.0,
        eb_available=True,
    )
    assert delivery.eb_import_kwh == pytest.approx(1.5 - 0.1, abs=0.01)
    assert delivery.battery.soc == pytest.approx(0.05)


def test_a_buyer_with_more_than_it_needs_stores_then_exports() -> None:
    delivery = deliver(
        _battery(0.99),
        generation_kw=0.0,
        consumption_kw=0.5,
        contracted_export_kw=-2.0,  # bought 2 kWh
        duration_h=1.0,
        eb_available=True,
    )
    assert delivery.battery_kwh > 0
    assert delivery.eb_export_kwh > 1.0


def test_a_power_cut_turns_shortfall_into_unserved_load_and_surplus_into_curtailment() -> None:
    short = deliver(
        _battery(0.05),
        generation_kw=0.0,
        consumption_kw=1.0,
        contracted_export_kw=0.0,
        duration_h=0.25,
        eb_available=False,
    )
    assert short.unserved_kwh == pytest.approx(0.25)
    assert short.eb_import_kwh == 0.0
    spill = deliver(
        _battery(1.0),
        generation_kw=3.0,
        consumption_kw=0.5,
        contracted_export_kw=0.0,
        duration_h=0.25,
        eb_available=False,
    )
    assert spill.curtailed_kwh == pytest.approx(0.625)
    assert spill.eb_export_kwh == 0.0
