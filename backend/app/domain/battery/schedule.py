"""Projecting a battery across the hours ahead.

Given a household's expected hourly net position (generation minus load,
already adjusted for anything it has contracted to sell or buy), walk its
battery forward: surplus charges it, deficits drain it down to a floor. What
the battery can't absorb is the household's *spill* (energy it must sell or
export) and what it can't cover is its *shortfall* (energy it must buy) —
exactly the quantities an agent takes to market.

Pure per ADR-0006.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.battery.model import Battery, charge, discharge

SLOT_HOURS = 1.0
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class SlotPlan:
    slot: int
    net_kwh: float  # expected net position this hour; + surplus, - deficit
    charge_kwh: float  # energy drawn into the battery (before conversion loss)
    discharge_kwh: float
    spill_kwh: float  # surplus the battery can't take: to sell or export
    short_kwh: float  # deficit the battery can't cover: to buy
    stored_start_kwh: float
    stored_end_kwh: float


def project(
    battery: Battery,
    net_kwh: Sequence[float],
    *,
    floor_kwh: Sequence[float],
) -> tuple[SlotPlan, ...]:
    """The battery's path over `len(net_kwh)` one-hour slots. `floor_kwh`
    is the least energy the household keeps in storage for itself in each
    slot (battery protection, or charge held for an outage)."""
    plans: list[SlotPlan] = []
    working = battery
    for slot, net in enumerate(net_kwh):
        start = working.stored_kwh
        charged = discharged = spill = short = 0.0
        if net > _EPSILON:
            working, accepted_kw = charge(working, net / SLOT_HOURS, SLOT_HOURS)
            charged = accepted_kw * SLOT_HOURS
            spill = net - charged
        elif net < -_EPSILON:
            available = max(0.0, working.stored_kwh - floor_kwh[slot])
            working, delivered_kw = discharge(
                working, min(-net, available) / SLOT_HOURS, SLOT_HOURS
            )
            discharged = delivered_kw * SLOT_HOURS
            short = -net - discharged
        plans.append(
            SlotPlan(
                slot=slot,
                net_kwh=net,
                charge_kwh=charged,
                discharge_kwh=discharged,
                spill_kwh=max(0.0, spill),
                short_kwh=max(0.0, short),
                stored_start_kwh=start,
                stored_end_kwh=working.stored_kwh,
            )
        )
    return tuple(plans)


def spare_storage_kwh(
    plans: Sequence[SlotPlan],
    slot: int,
    *,
    sale_floor_kwh: float,
    max_discharge_kwh: float,
) -> float:
    """Stored energy the household could sell in `slot` without leaving
    itself short later. Removing energy now lowers every later slot's
    storage until the battery next fills up (a later spill refills it), so
    the limit is the lowest storage level between now and then, less the
    floor the owner never sells below — and the battery's discharge rate."""
    lowest = float("inf")
    for plan in plans[slot:]:
        lowest = min(lowest, plan.stored_end_kwh)
        if plan.slot > slot and plan.spill_kwh > _EPSILON:
            break
    if lowest == float("inf"):
        return 0.0
    rate_left = max(0.0, max_discharge_kwh - plans[slot].discharge_kwh)
    return max(0.0, min(lowest - sale_floor_kwh, rate_left))


def storable_kwh(
    plans: Sequence[SlotPlan], slot: int, *, capacity_kwh: float, max_charge_kwh: float
) -> float:
    """Extra energy the household could buy in `slot` to store for later.
    Worth doing only up to the shortfall it would otherwise face later in
    the horizon, and limited by the charge rate and by headroom: the extra
    raises storage in every slot until that shortfall arrives, so it must
    fit under the battery's capacity the whole way there."""
    here = plans[slot]
    if here.short_kwh > _EPSILON or here.spill_kwh > _EPSILON:
        return 0.0
    later_need = sum(p.short_kwh for p in plans[slot + 1 :])
    if later_need <= _EPSILON:
        return 0.0
    headroom = float("inf")
    for plan in plans[slot:]:
        if plan.slot > slot and plan.short_kwh > _EPSILON:
            break
        headroom = min(headroom, capacity_kwh - plan.stored_end_kwh)
    rate_left = max(0.0, max_charge_kwh - here.charge_kwh)
    return max(0.0, min(later_need, rate_left, headroom))
