"""Clearing a session's hourly slots in time order: every agent decides,
the slot clears, and each agent carries its contracts, its price surprise
and what it learned into the next hour.

Pure computation, no database: `app.engine.session.plan_session` persists
what this produces, and `app.evaluation` runs it directly to measure it.
Both therefore exercise the very same market.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from app.agents.household_agent import decide_slots
from app.agents.memory import AgentMemory, TickFeedback, carry_surprise, learn
from app.agents.speech import outcome_message
from app.agents.types import SessionContext, SlotDecision, SlotObservation
from app.domain.grid.network import Network
from app.domain.market.orderbook import Side
from app.domain.market.slot_market import SlotClearing, clear_slot


@dataclass(frozen=True, slots=True)
class HouseholdSlot:
    """One household's part in one cleared slot."""

    decision: SlotDecision
    sold_kwh: float  # to neighbours
    bought_kwh: float  # from neighbours
    eb_bought_kwh: float
    eb_sold_kwh: float
    unserved_kwh: float
    outcome: str  # what the agent says happened


@dataclass(frozen=True, slots=True)
class ClearedSlot:
    slot: int
    clearing: SlotClearing
    households: dict[str, HouseholdSlot]


class SessionMarket:
    """Clears a session's slots one at a time — `clear_next` once per hour,
    in order — so a caller can persist, inspect or time each one."""

    def __init__(
        self,
        contexts: Mapping[str, SessionContext],
        *,
        network: Network,
        names: Mapping[str, str],
        memories: Mapping[str, AgentMemory],
    ) -> None:
        if not contexts:
            msg = "a session needs at least one household"
            raise ValueError(msg)
        first = next(iter(contexts.values()))
        self.horizon = len(first.forecast)
        self._feed_in = first.feed_in
        self._retail = first.retail
        self._eb = first.eb_available
        self._contexts = dict(contexts)
        self._network = network
        self._names = dict(names)
        self.memories: dict[str, AgentMemory] = dict(memories)
        self._committed = {hid: [0.0] * self.horizon for hid in contexts}
        self._surprise = dict.fromkeys(contexts, 0.0)
        self._next_slot = 0

    @property
    def done(self) -> bool:
        return self._next_slot >= self.horizon

    def _memory(self, household_id: str) -> AgentMemory:
        return self.memories.get(household_id, AgentMemory())

    def clear_next(self) -> ClearedSlot:
        if self.done:
            msg = "every slot of the session has already cleared"
            raise RuntimeError(msg)
        slot = self._next_slot
        self._next_slot += 1
        fit, retail, eb_up = self._feed_in[slot], self._retail[slot], self._eb[slot]

        decisions = dict(
            zip(
                self._contexts,
                decide_slots(
                    [
                        SlotObservation(
                            context=replace(ctx, memory=self._memory(hid)),
                            slot=slot,
                            committed_kwh=tuple(self._committed[hid]),
                            price_surprise=self._surprise[hid],
                        )
                        for hid, ctx in self._contexts.items()
                    ]
                ),
                strict=True,
            )
        )
        clearing = clear_slot(
            slot,
            [order for d in decisions.values() for order in d.orders],
            network=self._network,
            feed_in_tariff=fit,
            retail_tariff=retail,
            eb_available=eb_up,
        )

        market_prices = tuple(t.price_per_kwh for t in clearing.safety.trades)
        households: dict[str, HouseholdSlot] = {}
        for hid, decision in decisions.items():
            sold = clearing.matched_kwh(hid, Side.ASK)
            bought = clearing.matched_kwh(hid, Side.BID)
            self._committed[hid][slot] += sold - bought
            eb_bought = sum(
                f.kwh for f in clearing.eb_flows if f.household_id == hid and f.side is Side.BID
            )
            eb_sold = sum(
                f.kwh for f in clearing.eb_flows if f.household_id == hid and f.side is Side.ASK
            )
            unserved = sum(kwh for who, kwh in clearing.unserved if who == hid)
            own_trades = [
                t
                for t in clearing.safety.trades
                if hid in (t.buyer_household_id, t.seller_household_id)
            ]
            matched = sold + bought
            avg_price = (
                sum(t.kwh * t.price_per_kwh for t in own_trades) / matched if matched > 0 else None
            )
            outcome = outcome_message(
                decision,
                trades=[
                    (
                        self._names[
                            t.buyer_household_id
                            if t.seller_household_id == hid
                            else t.seller_household_id
                        ],
                        t.kwh,
                        t.price_per_kwh,
                        t.round_index,
                    )
                    for t in own_trades
                ],
                eb_kwh=eb_bought + eb_sold,
                eb_price=retail if eb_bought else (fit if eb_sold else None),
                unserved_kwh=unserved,
            )
            households[hid] = HouseholdSlot(
                decision=decision,
                sold_kwh=sold,
                bought_kwh=bought,
                eb_bought_kwh=eb_bought,
                eb_sold_kwh=eb_sold,
                unserved_kwh=unserved,
                outcome=outcome,
            )
            # The market tape is public: every agent sees how this hour
            # cleared against its own belief, whether it traded or not.
            self._surprise[hid] = carry_surprise(
                self._surprise[hid],
                believed=self._memory(hid).expected_price(
                    decision.hour_of_day, feed_in_tariff=fit, retail_tariff=retail
                ),
                market_prices=market_prices,
            )
            if decision.orders and decision.limit_price is not None:
                self.memories[hid] = learn(
                    self._memory(hid),
                    TickFeedback(
                        hour=decision.hour_of_day,
                        side=decision.side,
                        requested_kwh=decision.quantity_kwh,
                        matched_kwh=matched,
                        own_avg_price=avg_price,
                        market_prices=market_prices,
                        floor_or_ceiling=decision.limit_price,
                        feed_in_tariff=fit,
                        retail_tariff=retail,
                    ),
                )
        return ClearedSlot(slot=slot, clearing=clearing, households=households)
