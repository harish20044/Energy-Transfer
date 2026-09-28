"""Multi-round bilateral negotiation before a tick's auction settles.

Real bargaining, not decoration: every seller opens near the retail tariff —
the price most favourable to itself — and every buyer opens near the
feed-in tariff, then each concedes a fixed step toward its own reservation
price (the feed-in tariff for a seller, the retail tariff for a buyer) on
every round it goes unmatched. By the final round every remaining order has
conceded all the way to its reservation price — exactly the single fixed
price `app.domain.market.auction.clear_uniform_price` always used before —
so this is a strict refinement of the original mechanism: nothing that
would have matched under a single-shot reservation-price auction is ever
lost, but a pair willing to meet in the middle now matches earlier, at a
price that actually reflects how eager each side was, instead of every
trade in the system settling at the same constant midpoint regardless of
supply and demand.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.market.auction import Trade, clear_uniform_price
from app.domain.market.orderbook import Order, Side

_QUANTITY_EPSILON = 1e-9
DEFAULT_ROUNDS = 4


@dataclass(frozen=True, slots=True)
class NegotiationRound:
    """One round's offers and whatever matched at them."""

    round_index: int
    asks: tuple[Order, ...]
    bids: tuple[Order, ...]
    trades: tuple[Trade, ...]
    clearing_price: float | None


@dataclass(frozen=True, slots=True)
class NegotiationResult:
    rounds: tuple[NegotiationRound, ...]
    trades: tuple[Trade, ...]
    matched_kwh: float


def _price_at(
    round_index: int,
    *,
    total_rounds: int,
    opening: float,
    reservation: float,
    urgency: float,
) -> float:
    """Concession from `opening` (round 0) to `reservation` (the final
    round), shaped by `urgency` in `[0, 1]`.

    `urgency` is what makes two households negotiate differently rather
    than moving in lockstep: a household with nowhere left to put its
    surplus, or none left in the battery to draw on, concedes fast (a
    convex curve that drops most of the way in the first round or two); one
    with headroom to spare holds its opening price and concedes late. Either
    way the price still lands exactly on `reservation` by the final round —
    urgency changes *when* a household gives ground, never *how far*, so the
    reservation-price guarantee (and therefore individual rationality) is
    untouched by it.
    """
    if total_rounds <= 1:
        return reservation
    linear_fraction = round_index / (total_rounds - 1)
    # urgency 0 -> exponent 1.6 (patient: concedes late); urgency 1 ->
    # exponent 0.4 (eager: concedes early). x**p stays in [0, 1] for
    # x in [0, 1] and p > 0, so this can never overshoot past reservation.
    exponent = 1.6 - 1.2 * min(1.0, max(0.0, urgency))
    fraction = float(linear_fraction**exponent)
    return opening + (reservation - opening) * fraction


def negotiate(
    asks: list[Order],
    bids: list[Order],
    *,
    feed_in_tariff: float,
    retail_tariff: float,
    rounds: int = DEFAULT_ROUNDS,
    urgency: dict[str, float] | None = None,
) -> NegotiationResult:
    """Run up to `rounds` rounds of concession, clearing a uniform-price
    auction each round against whatever quantity is still unmatched.

    Every ask price stays in `[feed_in_tariff, retail_tariff]` by
    construction (it only ever moves from `retail_tariff` down to
    `feed_in_tariff`), and every bid price the mirror image — so every trade
    at every round is automatically inside the tariff band, the same
    individual-rationality guarantee the single-shot auction had.

    `urgency` is each household's concession speed in `[0, 1]` (see
    `_price_at`); a household missing from it concedes at the neutral,
    linear pace (`urgency=0.5`).

    Precondition: at most one ask and one bid per household — true of every
    order this system actually produces (a household nets to a single side
    and quantity per tick), and required here because remaining quantity is
    tracked per household id, not per order.
    """
    urgency = urgency or {}
    remaining_ask_kwh = {order.household_id: order.kwh for order in asks}
    remaining_bid_kwh = {order.household_id: order.kwh for order in bids}
    ask_limit_price = {order.household_id: order.limit_price for order in asks}
    bid_limit_price = {order.household_id: order.limit_price for order in bids}

    negotiation_rounds: list[NegotiationRound] = []
    all_trades: list[Trade] = []

    for round_index in range(rounds):
        if not remaining_ask_kwh or not remaining_bid_kwh:
            break

        round_asks = tuple(
            Order(
                household_id,
                Side.ASK,
                kwh,
                _price_at(
                    round_index,
                    total_rounds=rounds,
                    opening=retail_tariff,
                    reservation=ask_limit_price[household_id],
                    urgency=urgency.get(household_id, 0.5),
                ),
            )
            for household_id, kwh in remaining_ask_kwh.items()
            if kwh > _QUANTITY_EPSILON
        )
        round_bids = tuple(
            Order(
                household_id,
                Side.BID,
                kwh,
                _price_at(
                    round_index,
                    total_rounds=rounds,
                    opening=feed_in_tariff,
                    reservation=bid_limit_price[household_id],
                    urgency=urgency.get(household_id, 0.5),
                ),
            )
            for household_id, kwh in remaining_bid_kwh.items()
            if kwh > _QUANTITY_EPSILON
        )

        result = clear_uniform_price(
            list(round_asks),
            list(round_bids),
            feed_in_tariff=feed_in_tariff,
            retail_tariff=retail_tariff,
        )
        round_trades = tuple(replace(trade, round_index=round_index) for trade in result.trades)

        for trade in round_trades:
            remaining_ask_kwh[trade.seller_household_id] -= trade.kwh
            remaining_bid_kwh[trade.buyer_household_id] -= trade.kwh
        remaining_ask_kwh = {
            hid: kwh for hid, kwh in remaining_ask_kwh.items() if kwh > _QUANTITY_EPSILON
        }
        remaining_bid_kwh = {
            hid: kwh for hid, kwh in remaining_bid_kwh.items() if kwh > _QUANTITY_EPSILON
        }

        negotiation_rounds.append(
            NegotiationRound(
                round_index=round_index,
                asks=round_asks,
                bids=round_bids,
                trades=round_trades,
                clearing_price=result.clearing_price,
            )
        )
        all_trades.extend(round_trades)

    trades = tuple(all_trades)
    return NegotiationResult(
        rounds=tuple(negotiation_rounds),
        trades=trades,
        matched_kwh=sum(trade.kwh for trade in trades),
    )
