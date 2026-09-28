"""Orders and the depth curves built from them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Side(StrEnum):
    ASK = "ask"  # offering to sell surplus
    BID = "bid"  # offering to buy


@dataclass(frozen=True, slots=True)
class Order:
    household_id: str
    side: Side
    kwh: float
    limit_price: float

    def __post_init__(self) -> None:
        if self.kwh <= 0:
            msg = f"kwh must be positive, got {self.kwh}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DepthLevel:
    """One price level of an order book, with volume accumulated up to it —
    the shape the Market page's order-book ladder and depth chart both read
    directly."""

    price: float
    kwh: float
    cumulative_kwh: float


def ask_depth(asks: list[Order]) -> list[DepthLevel]:
    """Sell side, ascending by price — cheapest surplus first."""
    return _depth(asks, ascending=True)


def bid_depth(bids: list[Order]) -> list[DepthLevel]:
    """Buy side, descending by price — most eager buyer first."""
    return _depth(bids, ascending=False)


def _depth(orders: list[Order], *, ascending: bool) -> list[DepthLevel]:
    by_price: dict[float, float] = {}
    for order in orders:
        by_price[order.limit_price] = by_price.get(order.limit_price, 0.0) + order.kwh

    prices = sorted(by_price, reverse=not ascending)
    levels: list[DepthLevel] = []
    running = 0.0
    for price in prices:
        running += by_price[price]
        levels.append(DepthLevel(price=price, kwh=by_price[price], cumulative_kwh=running))
    return levels
