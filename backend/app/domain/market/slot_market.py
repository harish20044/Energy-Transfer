"""Clearing one hourly delivery slot of an ahead market: households trade
with each other first, and the EB — the utility, the provider — stands
behind every one of them.

1. Every household's agent submits at most one ask and one bid for the
   slot. Each order is either **firm** (energy the household must sell or
   must buy — its forecast surplus or shortfall) or **optional** (an
   opportunity: selling stored charge it doesn't need, or buying cheap
   neighbour energy to store for later).
2. Households negotiate in rounds (`app.domain.market.negotiation`) — the
   same concession mechanism as before, inside the tariff band.
3. Grid safety curtails trades the feeder can't carry.
4. Whatever **firm** quantity is left, the EB takes: it sells to a buyer at
   the slot's retail tariff and buys from a seller at the feed-in tariff —
   so every household always gets the electricity it needs, and neighbours
   are simply the cheaper option when they have some to spare. Optional
   orders never fall back to the EB (buying at retail to store would be a
   loss). During an EB power cut there is no fallback at all: unmatched
   firm demand is unserved and unmatched firm surplus has nowhere to go.

Pure per ADR-0006.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.grid.network import Network
from app.domain.grid.safety import SafetyResult, enforce
from app.domain.market.negotiation import DEFAULT_ROUNDS, NegotiationResult, negotiate
from app.domain.market.orderbook import Order, Side

_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class SlotOrder:
    household_id: str
    side: Side
    kwh: float
    limit_price: float  # floor for an ask, ceiling for a bid
    firm: bool
    opening_price: float | None = None
    urgency: float = 0.5


@dataclass(frozen=True, slots=True)
class EbFlow:
    """A household's scheduled exchange with the EB for the slot."""

    household_id: str
    side: Side  # BID: the household buys from the EB; ASK: it sells to the EB
    kwh: float
    price: float


@dataclass(frozen=True, slots=True)
class SlotClearing:
    slot: int
    feed_in_tariff: float
    retail_tariff: float
    eb_available: bool
    negotiation: NegotiationResult
    safety: SafetyResult
    eb_flows: tuple[EbFlow, ...]
    # Firm quantities nobody could take because the EB was down.
    unserved: tuple[tuple[str, float], ...]
    stranded: tuple[tuple[str, float], ...]

    def matched_kwh(self, household_id: str, side: Side) -> float:
        trades = self.safety.trades
        if side is Side.ASK:
            return sum(t.kwh for t in trades if t.seller_household_id == household_id)
        return sum(t.kwh for t in trades if t.buyer_household_id == household_id)


def clear_slot(
    slot: int,
    orders: list[SlotOrder],
    *,
    network: Network,
    feed_in_tariff: float,
    retail_tariff: float,
    eb_available: bool,
    rounds: int = DEFAULT_ROUNDS,
) -> SlotClearing:
    for order in orders:
        if order.kwh <= 0:
            msg = f"order quantity must be positive, got {order.kwh} for {order.household_id}"
            raise ValueError(msg)
    seen: set[tuple[str, Side]] = set()
    for order in orders:
        key = (order.household_id, order.side)
        if key in seen:
            msg = f"{order.household_id} has more than one {order.side.value} in slot {slot}"
            raise ValueError(msg)
        seen.add(key)

    def clamp(price: float) -> float:
        return min(retail_tariff, max(feed_in_tariff, price))

    asks = [
        Order(o.household_id, Side.ASK, o.kwh, clamp(o.limit_price))
        for o in orders
        if o.side is Side.ASK
    ]
    bids = [
        Order(o.household_id, Side.BID, o.kwh, clamp(o.limit_price))
        for o in orders
        if o.side is Side.BID
    ]
    negotiation = negotiate(
        asks,
        bids,
        feed_in_tariff=feed_in_tariff,
        retail_tariff=retail_tariff,
        rounds=rounds,
        urgency={o.household_id: o.urgency for o in orders},
        opening={o.household_id: o.opening_price for o in orders if o.opening_price is not None},
    )
    safety = enforce(network, negotiation.trades)

    flows: list[EbFlow] = []
    unserved: list[tuple[str, float]] = []
    stranded: list[tuple[str, float]] = []
    for order in orders:
        if not order.firm:
            continue
        if order.side is Side.BID:
            matched = sum(
                t.kwh for t in safety.trades if t.buyer_household_id == order.household_id
            )
        else:
            matched = sum(
                t.kwh for t in safety.trades if t.seller_household_id == order.household_id
            )
        left = order.kwh - matched
        if left <= _EPSILON:
            continue
        if eb_available:
            price = retail_tariff if order.side is Side.BID else feed_in_tariff
            flows.append(EbFlow(order.household_id, order.side, left, price))
        elif order.side is Side.BID:
            unserved.append((order.household_id, left))
        else:
            stranded.append((order.household_id, left))

    return SlotClearing(
        slot=slot,
        feed_in_tariff=feed_in_tariff,
        retail_tariff=retail_tariff,
        eb_available=eb_available,
        negotiation=negotiation,
        safety=safety,
        eb_flows=tuple(flows),
        unserved=tuple(unserved),
        stranded=tuple(stranded),
    )
