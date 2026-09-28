"""Uniform-price double auction clearing — deterministic cases.

The invariants that must hold for *any* input (price bounds, conservation)
are covered as Hypothesis property tests in tests/property/; this file is
worked examples that pin down the exact matching and pricing behaviour.
"""

from __future__ import annotations

import pytest

from app.domain.market.auction import clear_uniform_price
from app.domain.market.orderbook import Order, Side

pytestmark = pytest.mark.unit

FIT, RETAIL = 3.0, 8.0


def ask(household_id: str, kwh: float, price: float) -> Order:
    return Order(household_id=household_id, side=Side.ASK, kwh=kwh, limit_price=price)


def bid(household_id: str, kwh: float, price: float) -> Order:
    return Order(household_id=household_id, side=Side.BID, kwh=kwh, limit_price=price)


def test_no_crossing_clears_nothing() -> None:
    result = clear_uniform_price(
        [ask("seller", 5.0, 6.0)],
        [bid("buyer", 5.0, 4.0)],
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
    )

    assert result.clearing_price is None
    assert result.trades == ()
    assert result.matched_kwh == 0.0


def test_a_single_exact_match_clears_at_the_midpoint() -> None:
    result = clear_uniform_price(
        [ask("seller", 5.0, 4.0)],
        [bid("buyer", 5.0, 6.0)],
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
    )

    assert result.clearing_price == pytest.approx(5.0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.seller_household_id == "seller"
    assert trade.buyer_household_id == "buyer"
    assert trade.kwh == pytest.approx(5.0)
    assert trade.price_per_kwh == pytest.approx(5.0)


def test_every_matched_trade_settles_at_the_same_uniform_price() -> None:
    """The defining feature of a uniform-price (vs pay-as-bid) auction."""
    asks = [ask("s1", 2.0, 3.5), ask("s2", 2.0, 4.5)]
    bids = [bid("b1", 2.0, 7.0), bid("b2", 2.0, 5.0)]

    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    prices = {trade.price_per_kwh for trade in result.trades}
    assert len(prices) == 1


def test_a_larger_ask_partially_fills_against_a_smaller_bid() -> None:
    result = clear_uniform_price(
        [ask("seller", 5.0, 4.0)],
        [bid("buyer", 2.0, 6.0)],
        feed_in_tariff=FIT,
        retail_tariff=RETAIL,
    )

    assert len(result.trades) == 1
    assert result.trades[0].kwh == pytest.approx(2.0)
    assert result.matched_kwh == pytest.approx(2.0)


def test_cheapest_sellers_and_most_eager_buyers_are_matched_first() -> None:
    asks = [ask("expensive", 3.0, 5.0), ask("cheap", 3.0, 3.0)]
    bids = [bid("only_buyer", 3.0, 7.0)]

    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    assert len(result.trades) == 1
    assert result.trades[0].seller_household_id == "cheap"


def test_matched_kwh_never_exceeds_the_smaller_side() -> None:
    asks = [ask("s1", 10.0, 3.0)]
    bids = [bid("b1", 3.0, 8.0)]

    result = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    assert result.matched_kwh == pytest.approx(3.0)


def test_empty_books_clear_nothing() -> None:
    result = clear_uniform_price([], [], feed_in_tariff=FIT, retail_tariff=RETAIL)
    assert result.clearing_price is None
