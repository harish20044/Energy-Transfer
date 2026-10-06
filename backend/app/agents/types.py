"""What an agent knows and decides during a planning session — shared by the
decision graph, its speech, and the session engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.agents.memory import AgentMemory
from app.domain.battery.model import Battery
from app.domain.market.slot_market import SlotOrder
from app.forecasting.predict import HourForecast


class Strategy(StrEnum):
    SELL_SURPLUS = "sell-surplus"  # firm: forecast surplus the battery can't hold
    SELL_STORED = "sell-stored"  # optional: stored charge not needed later
    BUY_SHORTFALL = "buy-shortfall"  # firm: forecast deficit the battery can't cover
    BUY_TO_STORE = "buy-to-store"  # optional: cheap neighbour energy for later
    PREPARE_OUTAGE = "prepare-outage"  # firm: charge up before an EB power cut
    SELF_SUFFICIENT = "self-sufficient"  # the battery covers this hour; nothing to trade
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class SessionContext:
    """Everything fixed about one household for the whole session."""

    household_id: str
    display_name: str
    battery_start: Battery
    # The owner's floor: the agent never sells stored charge below this.
    reserve: float
    forecast: tuple[HourForecast, ...]  # one per slot
    retail: tuple[float, ...]  # per-slot EB tariffs (peak surcharge applied)
    feed_in: tuple[float, ...]
    eb_available: tuple[bool, ...]  # False during an EB power cut
    memory: AgentMemory


@dataclass(frozen=True, slots=True)
class SlotObservation:
    context: SessionContext
    slot: int
    # Neighbour contracts so far, per slot: + sold, - bought (kWh).
    committed_kwh: tuple[float, ...]
    # How far this session's market is running above (+) or below (-) the
    # agent's learned hour-of-day prices, ₹/kWh (`app.agents.memory.carry_surprise`).
    price_surprise: float = 0.0


@dataclass(frozen=True, slots=True)
class SlotDecision:
    household_id: str
    slot: int
    hour_of_day: int
    strategy: Strategy
    orders: tuple[SlotOrder, ...]
    expected_net_kwh: float  # forecast P50 net position after contracts
    spill_kwh: float
    short_kwh: float
    spare_kwh: float
    storable_kwh: float
    stored_kwh: float  # expected battery energy at the start of the slot
    charge_kwh: float  # expected charging from the household's own surplus this slot
    # Hour of day the battery is next expected to be full (spilling), if it is.
    full_by_hour: int | None
    risk_quantile: float | None  # the forecast quantile it committed at
    expected_price: float
    message: str
    reasons: tuple[str, ...]

    @property
    def side(self) -> str:
        if not self.orders:
            return "idle"
        return "sell" if self.orders[0].side.value == "ask" else "buy"

    @property
    def quantity_kwh(self) -> float:
        return sum(order.kwh for order in self.orders)

    @property
    def limit_price(self) -> float | None:
        return self.orders[0].limit_price if self.orders else None

    @property
    def opening_price(self) -> float | None:
        return self.orders[0].opening_price if self.orders else None
