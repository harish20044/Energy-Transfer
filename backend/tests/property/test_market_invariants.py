"""Objective O6, machine-checked: no participant is ever worse off than
dealing with the utility directly, across thousands of generated markets —
not just the handful of hand-picked examples in tests/unit/test_auction.py.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.market.auction import clear_uniform_price
from app.domain.market.orderbook import Order, Side

pytestmark = pytest.mark.property

FIT, RETAIL = 3.0, 8.0

# Prices are generated already respecting reservation_price()'s floor/ceiling
# — asks never below the feed-in tariff, bids never above the retail tariff —
# because that is the actual constraint every real order in this system is
# built under. Generating raw unconstrained prices would test a market this
# system never produces.
_ask_price = st.floats(min_value=FIT, max_value=RETAIL, allow_nan=False)
_bid_price = st.floats(min_value=FIT, max_value=RETAIL, allow_nan=False)
_kwh = st.floats(min_value=0.01, max_value=50.0, allow_nan=False)
_household_id = st.text(alphabet="abcdefghij", min_size=1, max_size=4)


@st.composite
def _order(draw: st.DrawFn, side: Side) -> Order:
    price = draw(_ask_price if side is Side.ASK else _bid_price)
    return Order(household_id=draw(_household_id), side=side, kwh=draw(_kwh), limit_price=price)


_asks = st.lists(_order(Side.ASK), min_size=0, max_size=15)
_bids = st.lists(_order(Side.BID), min_size=0, max_size=15)


@given(asks=_asks, bids=_bids)
def test_clearing_price_always_sits_inside_the_tariff_band(
    asks: list[Order], bids: list[Order]
) -> None:
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    if result.clearing_price is not None:
        assert FIT <= result.clearing_price <= RETAIL


@given(asks=_asks, bids=_bids)
def test_every_trade_leaves_the_seller_at_or_above_the_feed_in_tariff(
    asks: list[Order], bids: list[Order]
) -> None:
    """Individual rationality, seller side: selling to a neighbour is never
    worse than exporting to the utility."""
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    for trade in result.trades:
        assert trade.price_per_kwh >= FIT - 1e-9


@given(asks=_asks, bids=_bids)
def test_every_trade_leaves_the_buyer_at_or_below_the_retail_tariff(
    asks: list[Order], bids: list[Order]
) -> None:
    """Individual rationality, buyer side: buying from a neighbour is never
    worse than importing from the utility."""
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    for trade in result.trades:
        assert trade.price_per_kwh <= RETAIL + 1e-9


@given(asks=_asks, bids=_bids)
def test_matched_volume_never_exceeds_either_side(asks: list[Order], bids: list[Order]) -> None:
    """Energy is conserved: the market can never match more than either side
    actually offered."""
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    total_ask_kwh = sum(order.kwh for order in asks)
    total_bid_kwh = sum(order.kwh for order in bids)

    assert result.matched_kwh <= total_ask_kwh + 1e-6
    assert result.matched_kwh <= total_bid_kwh + 1e-6


@given(asks=_asks, bids=_bids)
def test_every_trade_settles_at_the_same_price(asks: list[Order], bids: list[Order]) -> None:
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    prices = {trade.price_per_kwh for trade in result.trades}
    assert len(prices) <= 1


@given(asks=_asks, bids=_bids)
def test_no_trade_has_zero_or_negative_quantity(asks: list[Order], bids: list[Order]) -> None:
    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    for trade in result.trades:
        assert trade.kwh > 0
