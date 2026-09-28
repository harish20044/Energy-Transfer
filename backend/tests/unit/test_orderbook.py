"""Order book depth curves."""

from __future__ import annotations

import pytest

from app.domain.market.orderbook import Order, Side, ask_depth, bid_depth

pytestmark = pytest.mark.unit


def test_zero_or_negative_kwh_is_rejected() -> None:
    with pytest.raises(ValueError, match="kwh must be positive"):
        Order(household_id="h1", side=Side.ASK, kwh=0.0, limit_price=5.0)


def test_ask_depth_is_ascending_by_price() -> None:
    asks = [
        Order(household_id="h1", side=Side.ASK, kwh=2.0, limit_price=6.0),
        Order(household_id="h2", side=Side.ASK, kwh=1.0, limit_price=3.0),
    ]
    depth = ask_depth(asks)

    assert [level.price for level in depth] == [3.0, 6.0]


def test_bid_depth_is_descending_by_price() -> None:
    bids = [
        Order(household_id="h1", side=Side.BID, kwh=2.0, limit_price=6.0),
        Order(household_id="h2", side=Side.BID, kwh=1.0, limit_price=3.0),
    ]
    depth = bid_depth(bids)

    assert [level.price for level in depth] == [6.0, 3.0]


def test_cumulative_volume_accumulates_monotonically() -> None:
    asks = [
        Order(household_id="h1", side=Side.ASK, kwh=1.0, limit_price=3.0),
        Order(household_id="h2", side=Side.ASK, kwh=2.0, limit_price=4.0),
        Order(household_id="h3", side=Side.ASK, kwh=1.5, limit_price=5.0),
    ]
    depth = ask_depth(asks)

    cumulative = [level.cumulative_kwh for level in depth]
    assert cumulative == sorted(cumulative)
    assert cumulative[-1] == pytest.approx(4.5)


def test_same_price_orders_merge_into_one_level() -> None:
    asks = [
        Order(household_id="h1", side=Side.ASK, kwh=1.0, limit_price=5.0),
        Order(household_id="h2", side=Side.ASK, kwh=2.0, limit_price=5.0),
    ]
    depth = ask_depth(asks)

    assert len(depth) == 1
    assert depth[0].kwh == pytest.approx(3.0)


def test_empty_book_has_no_depth() -> None:
    assert ask_depth([]) == []
    assert bid_depth([]) == []
