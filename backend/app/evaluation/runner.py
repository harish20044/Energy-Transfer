"""Run one planning session end to end, in memory: prepare every household
(warm-start battery, forecast), clear every slot with the shared
`SessionMarket`, deliver every 15-minute interval against what the simulated
weather and families actually do — and, beside it, replay the same hours
with the EB alone (each battery still doing self-consumption, no
neighbours), the counterfactual every saving is measured against.

No database: households are plain (transient) ORM objects, built from the
same seed table the app's database is filled from.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.agents.memory import AgentMemory
from app.domain.battery.model import Battery
from app.domain.grid.network import Network, default_feeder
from app.domain.settlement.delivery import Delivery, deliver
from app.engine.market_run import ClearedSlot, SessionMarket
from app.engine.session import (
    eb_up,
    household_order,
    prepare_household,
    reading_at,
    session_tariffs,
)
from app.models.household import DEFAULT_EVENING_RESERVE, Household
from app.schemas.session import HouseholdWhatIf
from app.scripts.seed_households import HOUSEHOLDS
from app.simulator.scenarios import Scenario

DEFAULT_RETAIL_INR = 10.50
DEFAULT_FEED_IN_INR = 3.61
# Repeating pattern for synthetic feeders larger than the ten seeded homes.
_SCALE_MEMBER_COUNTS = (4, 3, 5, 2, 6, 4, 3, 5, 2, 4)


@dataclass(frozen=True, slots=True)
class SessionSpec:
    """One evaluation session: what a user would set on the plan page."""

    name: str
    sim_date: date
    start_hour: int
    horizon_hours: int
    scenario: Scenario
    what_ifs: tuple[HouseholdWhatIf, ...] = ()
    # EB power cut as clock hours from midnight of `sim_date`, [start, end).
    power_cut: tuple[int, int] | None = None
    peak_surcharge_pct: float = 0.0
    retail_tariff: float = DEFAULT_RETAIL_INR
    feed_in_tariff: float = DEFAULT_FEED_IN_INR

    @property
    def power_cut_dict(self) -> dict[str, int] | None:
        if self.power_cut is None:
            return None
        return {"start_hour": self.power_cut[0], "end_hour": self.power_cut[1]}


@dataclass(slots=True)
class Ledger:
    """One household's energy and money over a run: kWh and ₹, always
    positive figures, the way the app's statements keep them."""

    paid_eb: float = 0.0
    earned_eb: float = 0.0
    paid_p2p: float = 0.0
    earned_p2p: float = 0.0
    eb_import_kwh: float = 0.0
    eb_export_kwh: float = 0.0
    p2p_bought_kwh: float = 0.0
    p2p_sold_kwh: float = 0.0
    unserved_kwh: float = 0.0
    curtailed_kwh: float = 0.0

    @property
    def bill(self) -> float:
        """Net cost of the hours: what was paid less what was earned."""
        return self.paid_eb + self.paid_p2p - self.earned_eb - self.earned_p2p


@dataclass(slots=True)
class HouseholdRun:
    household_id: str
    start_battery: Battery
    consumption_kw: list[float] = field(default_factory=list)  # per interval
    generation_kw: list[float] = field(default_factory=list)
    actual: Ledger = field(default_factory=Ledger)
    alone: Ledger = field(default_factory=Ledger)  # EB only
    actual_end_kwh: float = 0.0
    alone_end_kwh: float = 0.0


@dataclass(slots=True)
class SessionRun:
    spec: SessionSpec
    network: Network
    tick_minutes: int
    retail: tuple[float, ...]
    feed_in: tuple[float, ...]
    eb: tuple[bool, ...]  # per slot
    eb_by_interval: list[bool]
    households: dict[str, HouseholdRun]
    slots: list[ClearedSlot]
    slot_seconds: list[float]  # wall-clock: every agent decides, then the slot clears
    forecast_seconds: float
    memories: dict[str, AgentMemory]

    @property
    def intervals(self) -> int:
        return len(self.eb_by_interval)

    @property
    def interval_hours(self) -> float:
        return self.tick_minutes / 60.0


def seed_households() -> list[Household]:
    """The ten demo homes, exactly as `app.scripts.seed_households` puts
    them in the database."""
    return [
        _household(
            h.id,
            h.display_name,
            h.member_count,
            solar_capacity_kwp=h.solar_capacity_kwp,
            battery_capacity_kwh=h.battery_capacity_kwh,
            battery_max_charge_kw=h.battery_max_charge_kw,
            battery_max_discharge_kw=h.battery_max_discharge_kw,
        )
        for h in HOUSEHOLDS
    ]


def scaled_households(count: int) -> list[Household]:
    """A larger feeder of the same design (for the O3 scale test): `count`
    homes h1..hN, family sizes repeating the seed pattern."""
    template = HOUSEHOLDS[0]
    return [
        _household(
            f"h{i}",
            f"House {i}",
            _SCALE_MEMBER_COUNTS[(i - 1) % len(_SCALE_MEMBER_COUNTS)],
            solar_capacity_kwp=template.solar_capacity_kwp,
            battery_capacity_kwh=template.battery_capacity_kwh,
            battery_max_charge_kw=template.battery_max_charge_kw,
            battery_max_discharge_kw=template.battery_max_discharge_kw,
        )
        for i in range(1, count + 1)
    ]


def _household(
    household_id: str,
    display_name: str,
    member_count: int,
    *,
    solar_capacity_kwp: float,
    battery_capacity_kwh: float,
    battery_max_charge_kw: float,
    battery_max_discharge_kw: float,
) -> Household:
    return Household(
        id=household_id,
        display_name=display_name,
        member_count=member_count,
        solar_capacity_kwp=solar_capacity_kwp,
        battery_capacity_kwh=battery_capacity_kwh,
        battery_max_charge_kw=battery_max_charge_kw,
        battery_max_discharge_kw=battery_max_discharge_kw,
        evening_reserve=DEFAULT_EVENING_RESERVE,
        battery_soc=0.5,
    )


def run_session(
    spec: SessionSpec,
    households: Sequence[Household],
    *,
    memories: dict[str, AgentMemory],
    seed: int,
    tick_minutes: int = 15,
) -> SessionRun:
    ordered = sorted(households, key=lambda h: household_order(h.id))
    horizon = spec.horizon_hours
    power_cut = spec.power_cut_dict
    retail, feed_in, eb = session_tariffs(
        start_hour=spec.start_hour,
        horizon=horizon,
        retail_tariff=spec.retail_tariff,
        feed_in_tariff=spec.feed_in_tariff,
        peak_surcharge_pct=spec.peak_surcharge_pct,
        power_cut=power_cut,
    )
    what_ifs = {w.household_id: w for w in spec.what_ifs}

    started = time.perf_counter()
    prepared = {
        h.id: prepare_household(
            h,
            what_ifs.get(h.id) or HouseholdWhatIf(household_id=h.id),
            sim_date=spec.sim_date,
            start_hour=spec.start_hour,
            scenario=spec.scenario,
            retail=retail,
            feed_in=feed_in,
            eb=eb,
            seed=seed,
            tick_minutes=tick_minutes,
            memory=memories.get(h.id, AgentMemory()),
        )
        for h in ordered
    }
    forecast_seconds = time.perf_counter() - started

    network = default_feeder([h.id for h in ordered])
    market = SessionMarket(
        {hid: p.context for hid, p in prepared.items()},
        network=network,
        names={h.id: h.display_name for h in ordered},
        memories=memories,
    )
    slots: list[ClearedSlot] = []
    slot_seconds: list[float] = []
    while not market.done:
        started = time.perf_counter()
        slots.append(market.clear_next())
        slot_seconds.append(time.perf_counter() - started)

    runs = {
        h.id: HouseholdRun(household_id=h.id, start_battery=prepared[h.id].context.battery_start)
        for h in ordered
    }
    for cleared in slots:
        for hid, run in runs.items():
            _book_p2p(run.actual, cleared, hid)

    duration_h = tick_minutes / 60.0
    ticks_per_hour = 60 // tick_minutes
    eb_by_interval: list[bool] = []
    batteries = {h.id: prepared[h.id].context.battery_start for h in ordered}
    alone = dict(batteries)
    for tick in range(horizon * ticks_per_hour):
        slot = tick // ticks_per_hour
        clock_minutes = spec.start_hour * 60 + tick * tick_minutes
        available = eb_up(power_cut, clock_minutes / 60.0)
        eb_by_interval.append(available)
        for h in ordered:
            run = runs[h.id]
            part = slots[slot].households[h.id]
            consumption, generation = reading_at(
                h,
                clock_minutes,
                sim_date=spec.sim_date,
                scenario=spec.scenario,
                override=prepared[h.id].override,
                seed=seed,
                tick_minutes=tick_minutes,
            )
            run.consumption_kw.append(consumption)
            run.generation_kw.append(generation)
            # A one-hour slot's kWh is its average kW.
            contracted_kw = part.sold_kwh - part.bought_kwh
            actual = deliver(
                batteries[h.id],
                generation_kw=generation,
                consumption_kw=consumption,
                contracted_export_kw=contracted_kw,
                duration_h=duration_h,
                eb_available=available,
            )
            batteries[h.id] = actual.battery
            _book_delivery(run.actual, actual, retail[slot], feed_in[slot])
            replay = deliver(
                alone[h.id],
                generation_kw=generation,
                consumption_kw=consumption,
                contracted_export_kw=0.0,
                duration_h=duration_h,
                eb_available=available,
            )
            alone[h.id] = replay.battery
            _book_delivery(run.alone, replay, retail[slot], feed_in[slot])
    for hid, run in runs.items():
        run.actual_end_kwh = batteries[hid].stored_kwh
        run.alone_end_kwh = alone[hid].stored_kwh

    return SessionRun(
        spec=spec,
        network=network,
        tick_minutes=tick_minutes,
        retail=retail,
        feed_in=feed_in,
        eb=eb,
        eb_by_interval=eb_by_interval,
        households=runs,
        slots=slots,
        slot_seconds=slot_seconds,
        forecast_seconds=forecast_seconds,
        memories=market.memories,
    )


def _book_p2p(ledger: Ledger, cleared: ClearedSlot, household_id: str) -> None:
    for trade in cleared.clearing.safety.trades:
        if trade.seller_household_id == household_id:
            ledger.earned_p2p += trade.kwh * trade.price_per_kwh
            ledger.p2p_sold_kwh += trade.kwh
        elif trade.buyer_household_id == household_id:
            ledger.paid_p2p += trade.kwh * trade.price_per_kwh
            ledger.p2p_bought_kwh += trade.kwh


def _book_delivery(ledger: Ledger, delivery: Delivery, retail: float, feed_in: float) -> None:
    ledger.paid_eb += delivery.eb_import_kwh * retail
    ledger.earned_eb += delivery.eb_export_kwh * feed_in
    ledger.eb_import_kwh += delivery.eb_import_kwh
    ledger.eb_export_kwh += delivery.eb_export_kwh
    ledger.unserved_kwh += delivery.unserved_kwh
    ledger.curtailed_kwh += delivery.curtailed_kwh
