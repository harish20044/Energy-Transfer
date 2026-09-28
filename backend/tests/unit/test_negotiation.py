"""Multi-round negotiation: opens away from the reservation price, concedes
toward it, and never loses a match the old single-shot auction would have made."""

from __future__ import annotations

import pytest

from app.domain.market.negotiation import negotiate
from app.domain.market.orderbook import Order, Side

pytestmark = pytest.mark.unit

FEED_IN = 3.0
RETAIL = 8.0


def test_round_zero_opens_at_the_most_favourable_price_for_each_side() -> None:
    asks = [Order("h1", Side.ASK, 2.0, FEED_IN)]
    bids = [Order("h2", Side.BID, 2.0, RETAIL)]

    result = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=4)

    first_round = result.rounds[0]
    assert first_round.asks[0].limit_price == pytest.approx(RETAIL)
    assert first_round.bids[0].limit_price == pytest.approx(FEED_IN)
    assert first_round.trades == ()  # opening offers can never cross


def test_everything_eventually_matches_by_the_final_round() -> None:
    """The final round's prices are exactly the old reservation prices, so
    anything that could ever match, matches by then."""
    asks = [Order("h1", Side.ASK, 2.0, FEED_IN)]
    bids = [Order("h2", Side.BID, 2.0, RETAIL)]

    result = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=4)

    assert result.matched_kwh == pytest.approx(2.0)


def test_every_trade_at_every_round_stays_inside_the_tariff_band() -> None:
    asks = [Order(f"seller{i}", Side.ASK, 1.5, FEED_IN) for i in range(5)]
    bids = [Order(f"buyer{i}", Side.BID, 1.5, RETAIL) for i in range(5)]

    result = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=5)

    assert result.matched_kwh > 0
    for trade in result.trades:
        assert FEED_IN <= trade.price_per_kwh <= RETAIL


def test_an_urgent_seller_concedes_faster_than_a_patient_one() -> None:
    """Two sellers, same reservation price, different urgency: at an early
    round the urgent one has already moved much closer to its floor."""
    asks = [
        Order("patient", Side.ASK, 1.0, FEED_IN),
        Order("urgent", Side.ASK, 1.0, FEED_IN),
    ]
    bids = [Order("buyer", Side.BID, 0.01, RETAIL)]  # tiny bid: nothing matches, rounds run fully

    result = negotiate(
        asks,
        bids,
        feed_in_tariff=FEED_IN,
        retail_tariff=RETAIL,
        rounds=6,
        urgency={"patient": 0.0, "urgent": 1.0},
    )

    early_round = result.rounds[2]
    patient_price = next(a for a in early_round.asks if a.household_id == "patient").limit_price
    urgent_price = next(a for a in early_round.asks if a.household_id == "urgent").limit_price
    assert urgent_price < patient_price  # closer to its floor already


def test_a_one_sided_book_matches_nothing() -> None:
    asks = [Order("h1", Side.ASK, 2.0, FEED_IN)]

    result = negotiate(asks, [], feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=4)

    assert result.trades == ()
    assert result.matched_kwh == 0.0


def test_matched_volume_is_independent_of_round_count() -> None:
    """More rounds change *when* and *at what price* things match, never
    *how much* ends up matched in total."""
    asks = [Order("h1", Side.ASK, 3.0, FEED_IN)]
    bids = [Order("h2", Side.BID, 2.0, RETAIL)]

    few_rounds = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=2)
    many_rounds = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=10)

    assert few_rounds.matched_kwh == pytest.approx(many_rounds.matched_kwh)
    assert few_rounds.matched_kwh == pytest.approx(2.0)  # the smaller side, fully cleared


def test_a_single_round_behaves_like_the_original_single_shot_auction() -> None:
    asks = [Order("h1", Side.ASK, 2.0, FEED_IN)]
    bids = [Order("h2", Side.BID, 2.0, RETAIL)]

    result = negotiate(asks, bids, feed_in_tariff=FEED_IN, retail_tariff=RETAIL, rounds=1)

    assert len(result.rounds) == 1
    assert result.rounds[0].asks[0].limit_price == pytest.approx(FEED_IN)
    assert result.rounds[0].bids[0].limit_price == pytest.approx(RETAIL)
    assert result.matched_kwh == pytest.approx(2.0)
