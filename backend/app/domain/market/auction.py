"""Uniform-price double auction clearing.

The core of the market. Deliberately separate from grid safety: this module
only knows about economics (who wants to trade with whom, at what price) —
whether the feeder can physically carry the result is `domain.grid.safety`'s
job, applied afterward.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.market.orderbook import Order

_QUANTITY_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Trade:
    buyer_household_id: str
    seller_household_id: str
    kwh: float
    price_per_kwh: float


@dataclass(frozen=True, slots=True)
class AuctionResult:
    clearing_price: float | None  # None when no ask and bid crossed this tick
    trades: tuple[Trade, ...]
    matched_kwh: float


def clear_uniform_price(
    asks: list[Order],
    bids: list[Order],
    *,
    feed_in_tariff: float,
    retail_tariff: float,
) -> AuctionResult:
    """Clear a uniform-price double auction.

    Asks are sorted ascending, bids descending, and matched wherever an ask's
    price sits at or below a bid's price — the standard double-auction
    crossing rule. Every matched kWh settles at the *same* clearing price
    rather than at each pair's own bid/ask (that would be pay-as-bid); this
    is what makes "the market price" a single, quotable number rather than a
    range.

    The clearing price is bounded to ``[feed_in_tariff, retail_tariff]`` by
    construction, not by clamping after the fact: a caller using
    ``battery.policy.reservation_price`` never produces an ask below the
    feed-in tariff or a bid above the retail tariff, so any crossing price is
    already inside that band. That is what turns objective O6 — no
    participant ends up worse off than dealing with the utility directly —
    into a structural guarantee instead of an empirical observation.
    """
    sorted_asks = sorted(asks, key=lambda order: order.limit_price)
    sorted_bids = sorted(bids, key=lambda order: order.limit_price, reverse=True)

    ask_remaining = [order.kwh for order in sorted_asks]
    bid_remaining = [order.kwh for order in sorted_bids]

    raw_trades: list[tuple[str, str, float]] = []
    ask_index = bid_index = 0
    last_ask_price: float | None = None
    last_bid_price: float | None = None

    while ask_index < len(sorted_asks) and bid_index < len(sorted_bids):
        ask, bid = sorted_asks[ask_index], sorted_bids[bid_index]
        if ask.limit_price > bid.limit_price:
            break  # no ask left can satisfy any remaining bid

        traded_kwh = min(ask_remaining[ask_index], bid_remaining[bid_index])
        if traded_kwh > _QUANTITY_EPSILON:
            raw_trades.append((bid.household_id, ask.household_id, traded_kwh))
            last_ask_price, last_bid_price = ask.limit_price, bid.limit_price

        ask_remaining[ask_index] -= traded_kwh
        bid_remaining[bid_index] -= traded_kwh
        if ask_remaining[ask_index] <= _QUANTITY_EPSILON:
            ask_index += 1
        if bid_remaining[bid_index] <= _QUANTITY_EPSILON:
            bid_index += 1

    if not raw_trades or last_ask_price is None or last_bid_price is None:
        return AuctionResult(clearing_price=None, trades=(), matched_kwh=0.0)

    # Split-the-difference at the margin. Guaranteed inside the tariff band:
    # last_ask_price >= feed_in_tariff and last_bid_price <= retail_tariff
    # hold for every order the caller constructs via reservation_price(), so
    # their average does too — the max/min below is a defensive floor/ceiling
    # for callers that don't go through that helper, not the source of truth.
    clearing_price = (last_ask_price + last_bid_price) / 2
    clearing_price = max(feed_in_tariff, min(retail_tariff, clearing_price))

    trades = tuple(
        Trade(
            buyer_household_id=buyer_id,
            seller_household_id=seller_id,
            kwh=kwh,
            price_per_kwh=clearing_price,
        )
        for buyer_id, seller_id, kwh in raw_trades
    )
    matched_kwh = sum(trade.kwh for trade in trades)

    return AuctionResult(clearing_price=clearing_price, trades=trades, matched_kwh=matched_kwh)
