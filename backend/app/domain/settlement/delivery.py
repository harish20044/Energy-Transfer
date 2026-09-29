"""Delivering one metering interval against what a household contracted.

The ahead market fixed each household's neighbour trades for the hour; the
real weather and the real family then decide what actually happens. The
contract is always honoured on the wire — the household's battery absorbs
the difference first, and anything the battery can't absorb is settled
with the EB at its tariffs: extra imports at retail, extra exports at the
feed-in rate. That imbalance is exactly what a better forecast saves.

During an EB power cut there is nobody to settle with: surplus the battery
can't take is curtailed (the inverter backs the panels off) and a deficit it
can't cover is unserved — the lights go out.

Pure per ADR-0006.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.battery.model import Battery, charge, discharge

# Lithium batteries are kept above this to protect their life.
PROTECTION_FLOOR_SOC = 0.05
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class Delivery:
    battery: Battery
    battery_kwh: float  # + charged, - discharged, over the interval
    eb_import_kwh: float
    eb_export_kwh: float
    unserved_kwh: float
    curtailed_kwh: float


def deliver(
    battery: Battery,
    *,
    generation_kw: float,
    consumption_kw: float,
    contracted_export_kw: float,
    duration_h: float,
    eb_available: bool,
    floor_soc: float = PROTECTION_FLOOR_SOC,
) -> Delivery:
    """`contracted_export_kw` is the household's net neighbour contract for
    the interval: positive when it sold, negative when it bought."""
    surplus_kw = generation_kw - consumption_kw - contracted_export_kw
    eb_import = eb_export = unserved = curtailed = 0.0
    if surplus_kw > _EPSILON:
        battery, accepted_kw = charge(battery, surplus_kw, duration_h)
        battery_kwh = accepted_kw * duration_h
        left = (surplus_kw - accepted_kw) * duration_h
        if eb_available:
            eb_export = left
        else:
            curtailed = left
    elif surplus_kw < -_EPSILON:
        need_kw = -surplus_kw
        available_kw = max(0.0, battery.stored_kwh - floor_soc * battery.capacity_kwh) / duration_h
        battery, delivered_kw = discharge(battery, min(need_kw, available_kw), duration_h)
        battery_kwh = -delivered_kw * duration_h
        left = (need_kw - delivered_kw) * duration_h
        if eb_available:
            eb_import = left
        else:
            unserved = left
    else:
        battery_kwh = 0.0
    return Delivery(
        battery=battery,
        battery_kwh=battery_kwh,
        eb_import_kwh=max(0.0, eb_import),
        eb_export_kwh=max(0.0, eb_export),
        unserved_kwh=max(0.0, unserved),
        curtailed_kwh=max(0.0, curtailed),
    )
