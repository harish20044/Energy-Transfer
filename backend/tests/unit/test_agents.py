"""The household agents: each strategy fires in the situation it exists for,
never breaks its owner's reserve, commits cautiously under uncertainty, and
learns from the market."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from app.agents.household_agent import GRAPH_NODES, compiled_graph, decide_slot
from app.agents.memory import SURPRISE_PERSISTENCE, AgentMemory, TickFeedback, carry_surprise, learn
from app.agents.types import SessionContext, SlotObservation, Strategy
from app.domain.battery.model import Battery
from app.domain.market.orderbook import Side
from app.forecasting.predict import HourForecast

pytestmark = pytest.mark.unit

FIT, RETAIL = 3.61, 10.50


def _hour(slot: int, *, load: float, sun: float, spread: float = 0.2) -> HourForecast:
    return HourForecast(
        slot=slot,
        day=date(2026, 5, 15),
        hour_of_day=(14 + slot) % 24,
        consumption_p10=max(0.0, load - spread),
        consumption_p50=load,
        consumption_p90=load + spread,
        generation_p10=max(0.0, sun - spread),
        generation_p50=sun,
        generation_p90=sun + spread,
    )


def _context(
    hours: list[tuple[float, float]],
    *,
    soc: float,
    reserve: float = 0.4,
    capacity: float = 10.0,
    eb: list[bool] | None = None,
    memory: AgentMemory | None = None,
) -> SessionContext:
    n = len(hours)
    return SessionContext(
        household_id="h1",
        display_name="House 1",
        battery_start=Battery(
            capacity_kwh=capacity, soc=soc, max_charge_kw=3.0, max_discharge_kw=3.0
        ),
        reserve=reserve,
        forecast=tuple(_hour(i, load=load, sun=sun) for i, (load, sun) in enumerate(hours)),
        retail=(RETAIL,) * n,
        feed_in=(FIT,) * n,
        eb_available=tuple(eb) if eb else (True,) * n,
        memory=memory or AgentMemory(),
    )


def _decide(ctx: SessionContext, slot: int = 0, *, price_surprise: float = 0.0) -> object:
    return decide_slot(
        SlotObservation(
            context=ctx,
            slot=slot,
            committed_kwh=(0.0,) * len(ctx.forecast),
            price_surprise=price_surprise,
        )
    )


def _no_panels(load: float, spread: float) -> SessionContext:
    """A house with no panels and an empty battery: everything it uses, it buys."""
    ctx = _context([(load, 0.0)], soc=0.05)
    hour = HourForecast(
        slot=0,
        day=date(2026, 5, 15),
        hour_of_day=14,
        consumption_p10=load - spread,
        consumption_p50=load,
        consumption_p90=load + spread,
        generation_p10=0.0,
        generation_p50=0.0,
        generation_p90=0.0,
    )
    return replace(ctx, forecast=(hour,))


def _believes(price: float, hour: int = 14) -> AgentMemory:
    prices: list[float | None] = [None] * 24
    prices[hour] = price
    return AgentMemory(price_by_hour=tuple(prices))


def test_the_decision_graph_has_the_documented_nodes() -> None:
    assert GRAPH_NODES == ("perceive", "project", "value", "order", "speak")
    assert set(GRAPH_NODES) <= set(compiled_graph().get_graph().nodes)


def test_a_full_battery_with_sun_to_spare_sells_its_surplus_firmly() -> None:
    decision = _decide(_context([(0.5, 4.0), (0.5, 4.0)], soc=1.0))
    assert decision.strategy is Strategy.SELL_SURPLUS
    order = decision.orders[0]
    assert order.side is Side.ASK and order.firm
    assert order.limit_price == pytest.approx(FIT)


def test_the_newsvendor_commits_less_when_the_market_pays_little_more_than_export() -> None:
    """At a learned price near the feed-in rate, under-selling costs little
    and over-selling (buying the gap at retail) costs a lot — so the agent
    commits a low quantile of its surplus; at a good price, a higher one."""
    cheap = [None] * 24
    cheap[14] = 4.2
    dear = [None] * 24
    dear[14] = 9.5
    low = _decide(_context([(0.5, 4.0)], soc=1.0, memory=AgentMemory(price_by_hour=tuple(cheap))))
    high = _decide(_context([(0.5, 4.0)], soc=1.0, memory=AgentMemory(price_by_hour=tuple(dear))))
    assert low.risk_quantile < 0.5 < high.risk_quantile
    assert low.orders[0].kwh < low.spill_kwh < high.orders[0].kwh + 1e-9


def test_an_empty_battery_at_night_buys_its_shortfall_firmly() -> None:
    decision = _decide(_context([(3.0, 0.0), (3.0, 0.0)], soc=0.05))
    assert decision.strategy is Strategy.BUY_SHORTFALL
    assert decision.orders[0].side is Side.BID and decision.orders[0].firm
    assert decision.orders[0].kwh >= decision.short_kwh


def test_a_stale_price_belief_never_buys_past_the_forecasts_p90() -> None:
    """Regression: an agent that learned (in another neighbourhood) that noon
    energy goes for the feed-in rate sees no cost in over-buying, so the
    newsvendor pushes it to its very top quantile. It must stop at the P90
    the forecast is calibrated for — not extrapolate a Gaussian tail to two
    or three times the house's need — and the EB backs only the expected
    shortfall, never the hedge."""
    ctx = replace(_no_panels(1.6, 0.8), memory=_believes(FIT))
    decision = _decide(ctx)
    assert decision.strategy is Strategy.BUY_SHORTFALL
    order = decision.orders[0]
    assert decision.risk_quantile == pytest.approx(0.9)
    # No panels, so the need's P90 is the load's P90.
    assert order.kwh == pytest.approx(1.6 + 0.8, rel=1e-4)
    assert order.firm and order.backed_kwh == pytest.approx(decision.short_kwh)


def test_todays_market_corrects_a_stale_price_belief() -> None:
    """Once the first hour clears near ₹7.4, well above the stale ₹3.61
    belief, the next hour's estimate moves up and the hedge all but
    disappears: at that price over-buying costs about as much as it saves."""
    ctx = replace(_no_panels(1.6, 0.8), memory=_believes(FIT))
    stale = _decide(ctx)
    surprise = carry_surprise(0.0, believed=FIT, market_prices=(7.45, 7.37))
    corrected = _decide(ctx, price_surprise=surprise)
    assert corrected.expected_price == pytest.approx(FIT + surprise)
    assert corrected.risk_quantile < 0.6
    stale_hedge = stale.orders[0].kwh - stale.short_kwh
    corrected_hedge = corrected.orders[0].kwh - corrected.short_kwh
    assert 0.0 <= corrected_hedge < 0.2 * stale_hedge
    assert any("clearing higher" in reason for reason in corrected.reasons)


def test_a_price_surprise_fades_hour_by_hour() -> None:
    first = carry_surprise(0.0, believed=4.0, market_prices=(7.0, 8.0))
    assert first == pytest.approx(SURPRISE_PERSISTENCE * 3.5)
    assert carry_surprise(first, believed=4.0, market_prices=()) == pytest.approx(
        SURPRISE_PERSISTENCE * first
    )


def test_a_battery_with_room_buys_cheap_energy_to_store_for_tonight() -> None:
    decision = _decide(_context([(0.5, 0.5), (4.0, 0.0), (4.0, 0.0), (4.0, 0.0)], soc=0.3))
    assert decision.strategy is Strategy.BUY_TO_STORE
    order = decision.orders[0]
    assert not order.firm  # only from neighbours, never the EB at retail
    assert FIT < order.limit_price < RETAIL


def test_spare_stored_charge_is_offered_but_never_below_the_reserve() -> None:
    decision = _decide(_context([(0.5, 0.5), (0.5, 0.5)], soc=0.9, reserve=0.4))
    assert decision.strategy is Strategy.SELL_STORED
    order = decision.orders[0]
    assert not order.firm
    assert order.kwh <= (0.9 - 0.4) * 10.0 + 1e-6


def test_a_high_reserve_keeps_the_charge_home() -> None:
    decision = _decide(_context([(0.5, 0.5), (0.5, 0.5)], soc=0.9, reserve=0.9))
    assert decision.strategy is not Strategy.SELL_STORED


def test_before_a_power_cut_the_agent_charges_up_firmly() -> None:
    ctx = _context([(0.5, 0.5), (3.0, 0.0), (3.0, 0.0)], soc=0.2, eb=[True, False, False])
    decision = _decide(ctx)
    assert decision.strategy is Strategy.PREPARE_OUTAGE
    assert decision.orders[0].firm and decision.orders[0].side is Side.BID


def test_during_a_power_cut_a_seller_commits_very_cautiously() -> None:
    up = _decide(_context([(0.5, 4.0)], soc=1.0))
    down = _decide(_context([(0.5, 4.0)], soc=1.0, eb=[False]))
    assert down.risk_quantile < up.risk_quantile


def test_the_agent_explains_itself() -> None:
    decision = _decide(_context([(0.5, 4.0), (0.5, 4.0)], soc=1.0))
    assert "offering" in decision.message
    assert "₹" in decision.message
    assert any("P10–P90" in reason for reason in decision.reasons)  # noqa: RUF001


def test_a_seller_that_sold_everything_raises_its_margin() -> None:
    memory = AgentMemory(sell_margin=0.2)
    learned = learn(
        memory,
        TickFeedback(
            hour=14,
            side="sell",
            requested_kwh=1.0,
            matched_kwh=1.0,
            own_avg_price=7.0,
            market_prices=(7.0,),
            floor_or_ceiling=FIT,
            feed_in_tariff=FIT,
            retail_tariff=RETAIL,
        ),
    )
    assert learned.sell_margin > memory.sell_margin
    assert learned.price_by_hour[14] == pytest.approx(7.0)
    assert learned.savings_inr == pytest.approx(7.0 - FIT)


def test_an_undercut_seller_lowers_its_margin() -> None:
    memory = AgentMemory(sell_margin=0.6)
    learned = learn(
        memory,
        TickFeedback(
            hour=14,
            side="sell",
            requested_kwh=1.0,
            matched_kwh=0.0,
            own_avg_price=None,
            market_prices=(4.0,),
            floor_or_ceiling=FIT,
            feed_in_tariff=FIT,
            retail_tariff=RETAIL,
        ),
    )
    assert learned.sell_margin < memory.sell_margin


def test_a_buyer_that_got_everything_bids_lower_next_time() -> None:
    memory = AgentMemory(buy_margin=0.1)
    learned = learn(
        memory,
        TickFeedback(
            hour=20,
            side="buy",
            requested_kwh=1.0,
            matched_kwh=1.0,
            own_avg_price=6.0,
            market_prices=(6.0,),
            floor_or_ceiling=RETAIL,
            feed_in_tariff=FIT,
            retail_tariff=RETAIL,
        ),
    )
    assert learned.buy_margin > memory.buy_margin
    assert learned.savings_inr == pytest.approx(RETAIL - 6.0)


def test_the_learned_price_is_the_agents_own_forecast() -> None:
    memory = AgentMemory()
    assert memory.expected_price(9, feed_in_tariff=FIT, retail_tariff=RETAIL) == pytest.approx(
        (FIT + RETAIL) / 2
    )
