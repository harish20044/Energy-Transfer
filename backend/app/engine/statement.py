"""A household's money for the session, kept the way an EB bill is: what it
paid and what it earned as separate, positive figures — never one signed
"balance" — and against what the same hours would have come to dealing with
the EB alone (its battery still doing self-consumption, but no neighbours).

Two views:
- **planned**: what the cleared market committed to, on the forecast.
- **delivered**: what has actually happened in the hours delivered so far,
  forecast errors and all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.battery.schedule import project
from app.domain.settlement.delivery import PROTECTION_FLOOR_SOC, deliver
from app.engine.session import battery_for, eb_up
from app.models.household import Household
from app.models.session import SessionForecast, SessionHousehold, SessionPosition
from app.models.simulation import MeterReading, SimulationState, TradeRecord
from app.schemas.session import StatementOut


@dataclass(slots=True)
class _Tally:
    earned_p2p: float = 0.0
    paid_p2p: float = 0.0
    paid_eb: float = 0.0
    earned_eb: float = 0.0
    alone_paid: float = 0.0
    alone_earned: float = 0.0
    sold: float = 0.0
    bought: float = 0.0
    from_eb: float = 0.0
    to_eb: float = 0.0
    unserved: float = 0.0

    def statement(self, basis: str, hours: int) -> StatementOut:
        with_neighbours = self.paid_p2p - self.earned_p2p + self.paid_eb - self.earned_eb
        eb_only = self.alone_paid - self.alone_earned
        return StatementOut(
            basis=basis,  # type: ignore[arg-type]
            hours=hours,
            earned_from_neighbours_inr=self.earned_p2p,
            paid_to_neighbours_inr=self.paid_p2p,
            paid_to_eb_inr=self.paid_eb,
            earned_from_eb_inr=self.earned_eb,
            eb_only_paid_inr=self.alone_paid,
            eb_only_earned_inr=self.alone_earned,
            saved_vs_eb_only_inr=eb_only - with_neighbours,
            units_sold_to_neighbours=self.sold,
            units_bought_from_neighbours=self.bought,
            units_from_eb=self.from_eb,
            units_to_eb=self.to_eb,
            units_unserved=self.unserved,
        )


def _add_p2p(tally: _Tally, trades: Sequence[TradeRecord], household_id: str) -> None:
    for t in trades:
        if t.seller_household_id == household_id:
            tally.earned_p2p += t.kwh * t.price_per_kwh
            tally.sold += t.kwh
        elif t.buyer_household_id == household_id:
            tally.paid_p2p += t.kwh * t.price_per_kwh
            tally.bought += t.kwh


async def statements(
    db: AsyncSession, state: SimulationState, household: Household, *, tick_minutes: int
) -> tuple[StatementOut | None, StatementOut | None]:
    if state.status == "setup":
        return None, None
    setup = await db.get(SessionHousehold, household.id)
    if setup is None:
        return None, None
    positions = {
        p.slot: p
        for p in (
            await db.scalars(
                select(SessionPosition).where(SessionPosition.household_id == household.id)
            )
        ).all()
    }
    forecasts = sorted(
        (
            await db.scalars(
                select(SessionForecast).where(SessionForecast.household_id == household.id)
            )
        ).all(),
        key=lambda f: f.slot,
    )
    trades = (
        await db.scalars(
            select(TradeRecord).where(
                or_(
                    TradeRecord.buyer_household_id == household.id,
                    TradeRecord.seller_household_id == household.id,
                )
            )
        )
    ).all()

    # Planned: the cleared market, on the forecast.
    planned = _Tally()
    _add_p2p(planned, trades, household.id)
    for pos in positions.values():
        planned.paid_eb += pos.eb_bought_kwh * pos.retail_tariff
        planned.earned_eb += pos.eb_sold_kwh * pos.feed_in_tariff
        planned.from_eb += pos.eb_bought_kwh
        planned.to_eb += pos.eb_sold_kwh
        planned.unserved += pos.unserved_kwh
    battery = battery_for(household, setup.start_soc, setup.battery_capacity_kwh)
    alone = project(
        battery,
        [f.generation_p50 - f.consumption_p50 for f in forecasts],
        floor_kwh=[PROTECTION_FLOOR_SOC * battery.capacity_kwh] * len(forecasts),
    )
    for plan in alone:
        pos = positions[plan.slot]
        if pos.eb_available:
            planned.alone_paid += plan.short_kwh * pos.retail_tariff
            planned.alone_earned += plan.spill_kwh * pos.feed_in_tariff
    planned_statement = planned.statement("planned", len(positions))

    # Delivered: what the meters actually recorded, interval by interval.
    ticks_per_hour = 60 // tick_minutes
    hours_delivered = state.tick_index // ticks_per_hour
    if hours_delivered == 0:
        return planned_statement, None
    readings = sorted(
        (
            await db.scalars(select(MeterReading).where(MeterReading.household_id == household.id))
        ).all(),
        key=lambda r: r.tick_index,
    )
    delivered = _Tally()
    _add_p2p(delivered, [t for t in trades if t.tick_index < hours_delivered], household.id)
    replay = battery_for(household, setup.start_soc, setup.battery_capacity_kwh)
    power_cut = (state.what_ifs or {}).get("power_cut")
    duration_h = tick_minutes / 60.0
    for reading in readings:
        pos = positions[reading.tick_index // ticks_per_hour]
        imported, exported = max(0.0, reading.grid_kwh), max(0.0, -reading.grid_kwh)
        delivered.paid_eb += imported * pos.retail_tariff
        delivered.earned_eb += exported * pos.feed_in_tariff
        delivered.from_eb += imported
        delivered.to_eb += exported
        delivered.unserved += reading.unserved_kwh
        alone_tick = deliver(
            replay,
            generation_kw=reading.generation_kw,
            consumption_kw=reading.consumption_kw,
            contracted_export_kw=0.0,
            duration_h=duration_h,
            eb_available=eb_up(power_cut, state.start_hour + reading.tick_index * duration_h),
        )
        replay = alone_tick.battery
        delivered.alone_paid += alone_tick.eb_import_kwh * pos.retail_tariff
        delivered.alone_earned += alone_tick.eb_export_kwh * pos.feed_in_tariff
    return planned_statement, delivered.statement("delivered", hours_delivered)
