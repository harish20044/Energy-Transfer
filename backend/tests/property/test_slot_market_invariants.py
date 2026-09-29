"""Invariants of one ahead-market slot, for any orders at all:

- every neighbour trade is priced inside [feed-in, retail] (nobody is worse
  off than dealing with the EB — objective O6);
- nobody trades more than they offered;
- while the EB is up, every firm order is fully covered — by neighbours or
  by the EB — so no household is ever left short;
- optional orders never touch the EB.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.grid.network import default_feeder
from app.domain.market.orderbook import Side
from app.domain.market.slot_market import SlotOrder, clear_slot

pytestmark = pytest.mark.property

FIT, RETAIL = 3.61, 10.50
HOUSEHOLDS = [f"h{i}" for i in range(1, 11)]
NETWORK = default_feeder(HOUSEHOLDS)


@st.composite
def _orders(draw: st.DrawFn) -> list[SlotOrder]:
    orders: list[SlotOrder] = []
    for household in draw(st.lists(st.sampled_from(HOUSEHOLDS), unique=True, max_size=10)):
        side = draw(st.sampled_from([Side.ASK, Side.BID]))
        orders.append(
            SlotOrder(
                household_id=household,
                side=side,
                kwh=draw(st.floats(min_value=0.05, max_value=4.0)),
                limit_price=draw(st.floats(min_value=0.0, max_value=15.0)),
                firm=draw(st.booleans()),
                opening_price=draw(st.none() | st.floats(min_value=0.0, max_value=15.0)),
                urgency=draw(st.floats(min_value=0.0, max_value=1.0)),
            )
        )
    return orders


@settings(max_examples=150, deadline=None)
@given(orders=_orders())
def test_trades_stay_inside_the_band_and_within_what_was_offered(orders: list[SlotOrder]) -> None:
    clearing = clear_slot(
        0, orders, network=NETWORK, feed_in_tariff=FIT, retail_tariff=RETAIL, eb_available=True
    )
    for trade in clearing.safety.trades:
        assert FIT - 1e-9 <= trade.price_per_kwh <= RETAIL + 1e-9
    for order in orders:
        assert clearing.matched_kwh(order.household_id, order.side) <= order.kwh + 1e-9


@settings(max_examples=150, deadline=None)
@given(orders=_orders())
def test_every_firm_order_is_covered_while_the_eb_is_up(orders: list[SlotOrder]) -> None:
    clearing = clear_slot(
        0, orders, network=NETWORK, feed_in_tariff=FIT, retail_tariff=RETAIL, eb_available=True
    )
    assert clearing.unserved == ()
    for order in orders:
        via_eb = sum(
            f.kwh
            for f in clearing.eb_flows
            if f.household_id == order.household_id and f.side is order.side
        )
        matched = clearing.matched_kwh(order.household_id, order.side)
        if order.firm:
            assert matched + via_eb >= order.kwh - 1e-6
        else:
            assert via_eb == 0.0
