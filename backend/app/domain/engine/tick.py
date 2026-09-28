"""One simulation tick, start to finish: every household's net position
becomes an order, the auction clears, grid safety curtails until feasible,
and the settled trades are appended to the ledger.

Pure orchestration over the other domain modules — no I/O, no clock, no
randomness (ADR-0006). Everything time-dependent or stochastic (what a
household's meter actually reads this tick) is computed by the caller
(`app.simulator`) and handed in as plain numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.battery.model import Battery
from app.domain.battery.policy import BatteryAction, plan_position, reservation_price
from app.domain.grid.network import Network
from app.domain.grid.safety import SafetyResult, enforce
from app.domain.ledger.hashchain import LedgerEntry, append
from app.domain.market.negotiation import DEFAULT_ROUNDS, NegotiationResult, negotiate
from app.domain.market.orderbook import Order, Side

_QUANTITY_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class HouseholdTickInput:
    household_id: str
    consumption_kw: float
    generation_kw: float
    battery: Battery
    evening_reserve: float


@dataclass(frozen=True, slots=True)
class HouseholdTickOutcome:
    household_id: str
    consumption_kw: float
    generation_kw: float
    battery_action: BatteryAction
    battery: Battery
    # Unmatched position settled directly with the grid, outside the P2P
    # market this tick: positive = imported from the grid, negative =
    # exported to it.
    grid_kwh: float


@dataclass(frozen=True, slots=True)
class TickResult:
    tick_index: int
    negotiation: NegotiationResult
    safety: SafetyResult
    new_ledger_entries: tuple[LedgerEntry, ...]
    household_outcomes: tuple[HouseholdTickOutcome, ...]


def _urgency_for(net_for_market_kw: float, battery: Battery) -> float:
    """How fast this household concedes toward its reservation price: a
    seller sitting on a nearly-full battery has nowhere left to put more
    surplus, so it's eager to sell now rather than risk curtailing next
    tick; a buyer close to empty is eager to buy now rather than risk
    breaching its own reserve. Both read directly off the battery state
    already decided this tick — no separate notion of "urgency" is stored
    anywhere."""
    return battery.soc if net_for_market_kw > 0 else 1.0 - battery.soc


def run_tick(
    tick_index: int,
    inputs: tuple[HouseholdTickInput, ...],
    *,
    network: Network,
    ledger_chain: tuple[LedgerEntry, ...],
    duration_h: float,
    feed_in_tariff: float,
    retail_tariff: float,
    is_evening: bool,
    negotiation_rounds: int = DEFAULT_ROUNDS,
) -> TickResult:
    """Run one tick for every household in `inputs` at once — they all share
    the same feeder and negotiate against each other before a single
    settlement clears."""
    asks: list[Order] = []
    bids: list[Order] = []
    plans: dict[str, tuple[BatteryAction, Battery, float]] = {}
    urgency: dict[str, float] = {}

    for household in inputs:
        net_generation_kw = household.generation_kw - household.consumption_kw
        plan = plan_position(
            household.battery,
            net_generation_kw,
            duration_h=duration_h,
            evening_reserve=household.evening_reserve,
            is_evening=is_evening,
        )
        plans[household.household_id] = (plan.battery_action, plan.battery, plan.net_for_market_kw)

        kwh = abs(plan.net_for_market_kw) * duration_h
        if kwh <= _QUANTITY_EPSILON:
            continue
        price = reservation_price(
            net_for_market_kw=plan.net_for_market_kw,
            feed_in_tariff=feed_in_tariff,
            retail_tariff=retail_tariff,
        )
        urgency[household.household_id] = _urgency_for(plan.net_for_market_kw, plan.battery)
        if plan.net_for_market_kw > 0:
            asks.append(Order(household.household_id, Side.ASK, kwh, price))
        else:
            bids.append(Order(household.household_id, Side.BID, kwh, price))

    negotiation = negotiate(
        asks,
        bids,
        feed_in_tariff=feed_in_tariff,
        retail_tariff=retail_tariff,
        rounds=negotiation_rounds,
        urgency=urgency,
    )
    safety = enforce(network, negotiation.trades)

    new_chain = ledger_chain
    for trade in safety.trades:
        new_chain = append(
            new_chain,
            tick_index=tick_index,
            buyer_household_id=trade.buyer_household_id,
            seller_household_id=trade.seller_household_id,
            kwh=trade.kwh,
            price_per_kwh=trade.price_per_kwh,
        )
    new_entries = new_chain[len(ledger_chain) :]

    matched_sell_kwh: dict[str, float] = {}
    matched_buy_kwh: dict[str, float] = {}
    for trade in safety.trades:
        matched_sell_kwh[trade.seller_household_id] = (
            matched_sell_kwh.get(trade.seller_household_id, 0.0) + trade.kwh
        )
        matched_buy_kwh[trade.buyer_household_id] = (
            matched_buy_kwh.get(trade.buyer_household_id, 0.0) + trade.kwh
        )

    outcomes = []
    for household in inputs:
        battery_action, battery, net_for_market_kw = plans[household.household_id]
        requested_kwh = abs(net_for_market_kw) * duration_h
        if net_for_market_kw > _QUANTITY_EPSILON:
            matched = matched_sell_kwh.get(household.household_id, 0.0)
            grid_kwh = -(requested_kwh - matched)
        elif net_for_market_kw < -_QUANTITY_EPSILON:
            matched = matched_buy_kwh.get(household.household_id, 0.0)
            grid_kwh = requested_kwh - matched
        else:
            grid_kwh = 0.0

        outcomes.append(
            HouseholdTickOutcome(
                household_id=household.household_id,
                consumption_kw=household.consumption_kw,
                generation_kw=household.generation_kw,
                battery_action=battery_action,
                battery=battery,
                grid_kwh=grid_kwh,
            )
        )

    return TickResult(
        tick_index=tick_index,
        negotiation=negotiation,
        safety=safety,
        new_ledger_entries=new_entries,
        household_outcomes=tuple(outcomes),
    )
