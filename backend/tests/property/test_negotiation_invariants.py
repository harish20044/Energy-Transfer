"""The multi-round negotiation is a strict refinement of the single-shot
auction: it must never lose a match the old mechanism would have made, and
every price at every round must stay inside the tariff band — proven across
thousands of generated markets, not just the handful of examples in
tests/unit/test_negotiation.py.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.market.auction import clear_uniform_price
from app.domain.market.negotiation import negotiate
from app.domain.market.orderbook import Order, Side

pytestmark = pytest.mark.property

FIT, RETAIL = 3.0, 8.0

_kwh = st.floats(min_value=0.01, max_value=50.0, allow_nan=False)
_urgency = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_rounds = st.integers(min_value=1, max_value=8)


@st.composite
def _book(draw: st.DrawFn) -> tuple[list[Order], list[Order], dict[str, float]]:
    """Asks and bids with guaranteed-unique household ids per side — the
    precondition `negotiate` documents, and the one every real tick honours
    since a household nets to a single order."""
    n_asks = draw(st.integers(min_value=0, max_value=8))
    n_bids = draw(st.integers(min_value=0, max_value=8))
    asks = [
        Order(f"seller{i}", Side.ASK, draw(_kwh), FIT) for i in range(n_asks)
    ]
    bids = [
        Order(f"buyer{i}", Side.BID, draw(_kwh), RETAIL) for i in range(n_bids)
    ]
    urgency = {
        order.household_id: draw(_urgency) for order in (*asks, *bids)
    }
    return asks, bids, urgency


@given(book=_book(), rounds=_rounds)
def test_every_round_price_stays_inside_the_tariff_band(
    book: tuple[list[Order], list[Order], dict[str, float]], rounds: int
) -> None:
    asks, bids, urgency = book
    result = negotiate(
        asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL, rounds=rounds, urgency=urgency
    )

    for round_ in result.rounds:
        for offer in (*round_.asks, *round_.bids):
            assert FIT - 1e-9 <= offer.limit_price <= RETAIL + 1e-9
        for trade in round_.trades:
            assert FIT - 1e-9 <= trade.price_per_kwh <= RETAIL + 1e-9


@given(book=_book(), rounds=_rounds)
def test_total_matched_volume_matches_a_single_shot_auction_at_reservation_prices(
    book: tuple[list[Order], list[Order], dict[str, float]], rounds: int
) -> None:
    """The defining guarantee of this design: however many rounds run,
    negotiation matches exactly what the original reservation-price auction
    would have — it only changes when and at what price, never how much."""
    asks, bids, urgency = book
    negotiated = negotiate(
        asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL, rounds=rounds, urgency=urgency
    )
    single_shot = clear_uniform_price(asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL)

    assert negotiated.matched_kwh == pytest.approx(single_shot.matched_kwh, abs=1e-6)


@given(book=_book(), rounds=_rounds)
def test_matched_volume_never_exceeds_either_side(
    book: tuple[list[Order], list[Order], dict[str, float]], rounds: int
) -> None:
    asks, bids, urgency = book
    result = negotiate(
        asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL, rounds=rounds, urgency=urgency
    )

    assert result.matched_kwh <= sum(o.kwh for o in asks) + 1e-6
    assert result.matched_kwh <= sum(o.kwh for o in bids) + 1e-6


@given(book=_book(), rounds=_rounds)
def test_no_trade_has_zero_or_negative_quantity(
    book: tuple[list[Order], list[Order], dict[str, float]], rounds: int
) -> None:
    asks, bids, urgency = book
    result = negotiate(
        asks, bids, feed_in_tariff=FIT, retail_tariff=RETAIL, rounds=rounds, urgency=urgency
    )

    for trade in result.trades:
        assert trade.kwh > 0
