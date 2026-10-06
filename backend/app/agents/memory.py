"""What an agent remembers between ticks, and how it learns from the market.

Pricing adapts with a Zero-Intelligence-Plus style rule (Cliff, 1997,
"Minimal-intelligence agents for bargaining behaviours in market-based
environments"; Preist & van Tol, 1998) — the classic adaptive trader for
continuous double auctions. Each agent keeps a *profit margin* on each side:
a seller opens at `floor x (1 + margin)`, a buyer at `ceiling x (1 - margin)`.
After every tick it compares what happened with what it asked for and moves
the margin toward a target price with a Widrow-Hoff update:

- sold everything -> it could probably have asked for more: aim a little
  above the price it got;
- a rival seller traded while it didn't -> it was undercut: aim a little
  below the cheapest price that cleared;
- (the mirror image for buyers).

It also keeps a running average of the price the market actually clears at
for each hour of the day — its own learned price forecast — which it uses to
decide how much to commit and when stored charge is worth selling.

That average is learned across sessions, so it can be stale: prices learned
in a neighbourhood where every home floods the feeder at noon say nothing
about one where three homes have no panels. Within a session the agent also
watches the market tape: how far the last hour that traded cleared above or
below its belief (`carry_surprise`). That surprise carries into the next
hour's estimate and fades by `SURPRISE_PERSISTENCE` each hour — electricity
prices are strongly persistent hour to hour, so the market's level right now
is the best single correction to a belief formed elsewhere.

Pure: no I/O, no clock, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

_LEARNING_RATE = 0.3
_PRICE_STEP = 0.05  # aim this fraction above/below the reference price
_MAX_MARGIN = 0.8
_PRICE_EMA_WEIGHT = 0.3
DEFAULT_MARGIN = 0.35
HOURS = 24
# Fraction of an hour's price surprise still expected the next hour.
SURPRISE_PERSISTENCE = 0.8


@dataclass(frozen=True, slots=True)
class AgentMemory:
    sell_margin: float = DEFAULT_MARGIN
    buy_margin: float = DEFAULT_MARGIN
    # Learned clearing price by hour of day; None until first observed.
    price_by_hour: tuple[float | None, ...] = (None,) * HOURS
    trades: int = 0
    kwh_sold: float = 0.0
    kwh_bought: float = 0.0
    # Money saved against dealing with the utility instead: selling above
    # the feed-in tariff, or buying below the retail tariff.
    savings_inr: float = 0.0

    def expected_price(self, hour: int, *, feed_in_tariff: float, retail_tariff: float) -> float:
        """The agent's own price forecast for this hour: what it has seen the
        market clear at, or the middle of the band if it hasn't seen yet."""
        learned = self.price_by_hour[hour % HOURS]
        return learned if learned is not None else (feed_in_tariff + retail_tariff) / 2.0


@dataclass(frozen=True, slots=True)
class TickFeedback:
    """What an agent observes about the tick it just took part in."""

    hour: int
    side: str  # "sell" | "buy" | "idle"
    requested_kwh: float
    matched_kwh: float
    own_avg_price: float | None
    # Every price the market cleared at this tick, any household.
    market_prices: tuple[float, ...]
    floor_or_ceiling: float
    feed_in_tariff: float
    retail_tariff: float


def carry_surprise(previous: float, *, believed: float, market_prices: tuple[float, ...]) -> float:
    """The price surprise to carry into the next hour: how far the market
    cleared above (+) or below (-) `believed` — the agent's own hour-of-day
    price for the hour just cleared — faded by one hour. An hour with no
    trades says nothing new, so the previous surprise just fades."""
    if not market_prices:
        return SURPRISE_PERSISTENCE * previous
    observed = sum(market_prices) / len(market_prices)
    return SURPRISE_PERSISTENCE * (observed - believed)


def _toward(current: float, target: float) -> float:
    updated = current + _LEARNING_RATE * (target - current)
    return min(_MAX_MARGIN, max(0.0, updated))


def learn(memory: AgentMemory, feedback: TickFeedback) -> AgentMemory:
    """The memory after one tick's feedback."""
    prices = list(memory.price_by_hour)
    if feedback.market_prices:
        observed = sum(feedback.market_prices) / len(feedback.market_prices)
        previous = prices[feedback.hour]
        prices[feedback.hour] = (
            observed
            if previous is None
            else (1 - _PRICE_EMA_WEIGHT) * previous + _PRICE_EMA_WEIGHT * observed
        )

    sell_margin, buy_margin = memory.sell_margin, memory.buy_margin
    fully_matched = (
        feedback.requested_kwh > 0 and feedback.matched_kwh >= 0.999 * feedback.requested_kwh
    )
    limit = feedback.floor_or_ceiling

    if feedback.side == "sell" and limit > 0:
        if fully_matched and feedback.own_avg_price is not None:
            target = feedback.own_avg_price * (1 + _PRICE_STEP) / limit - 1
            sell_margin = _toward(sell_margin, target)
        elif feedback.market_prices:
            target = min(feedback.market_prices) * (1 - _PRICE_STEP) / limit - 1
            sell_margin = _toward(sell_margin, target)
    elif feedback.side == "buy" and limit > 0:
        if fully_matched and feedback.own_avg_price is not None:
            target = 1 - feedback.own_avg_price * (1 - _PRICE_STEP) / limit
            buy_margin = _toward(buy_margin, target)
        elif feedback.market_prices:
            target = 1 - max(feedback.market_prices) * (1 + _PRICE_STEP) / limit
            buy_margin = _toward(buy_margin, target)

    savings = memory.savings_inr
    kwh_sold, kwh_bought = memory.kwh_sold, memory.kwh_bought
    if feedback.matched_kwh > 0 and feedback.own_avg_price is not None:
        if feedback.side == "sell":
            kwh_sold += feedback.matched_kwh
            savings += (feedback.own_avg_price - feedback.feed_in_tariff) * feedback.matched_kwh
        elif feedback.side == "buy":
            kwh_bought += feedback.matched_kwh
            savings += (feedback.retail_tariff - feedback.own_avg_price) * feedback.matched_kwh

    return replace(
        memory,
        sell_margin=sell_margin,
        buy_margin=buy_margin,
        price_by_hour=tuple(prices),
        trades=memory.trades + (1 if feedback.matched_kwh > 0 else 0),
        kwh_sold=kwh_sold,
        kwh_bought=kwh_bought,
        savings_inr=savings,
    )
