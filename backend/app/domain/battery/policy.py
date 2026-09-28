"""Turns a household's net power position into a battery action and a market
order — the piece that makes the "evening reserve" setting a real control
rather than a decoration on a settings page.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.battery.model import Battery, charge, discharge


class BatteryAction(StrEnum):
    CHARGING = "charging"
    DISCHARGING = "discharging"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class PositionPlan:
    """What a household does with one tick's net generation/load, before any
    market order is placed."""

    battery: Battery
    battery_action: BatteryAction
    battery_kw: float
    # Positive = surplus available to sell; negative = shortfall to buy.
    # Zero after the battery has taken its share either way.
    net_for_market_kw: float


def plan_position(
    battery: Battery,
    net_generation_kw: float,
    *,
    duration_h: float,
    evening_reserve: float,
    is_evening: bool,
) -> PositionPlan:
    """Decide what the battery does this tick, given raw net generation.

    `net_generation_kw` is generation minus load — positive means surplus,
    negative means shortfall. `evening_reserve` is the minimum state of charge
    the household wants held back once evening arrives (the dashboard's
    "Evening reserve" setting); it only constrains *discharging*, never
    charging, so a household always tops up when it has genuine surplus.
    """
    if net_generation_kw > 0:
        new_battery, accepted_kw = charge(battery, net_generation_kw, duration_h)
        remaining_surplus_kw = net_generation_kw - accepted_kw
        action = BatteryAction.CHARGING if accepted_kw > 0 else BatteryAction.IDLE
        return PositionPlan(
            battery=new_battery,
            battery_action=action,
            battery_kw=accepted_kw,
            net_for_market_kw=remaining_surplus_kw,
        )

    if net_generation_kw < 0:
        shortfall_kw = -net_generation_kw

        # In the evening, never discharge below the reserve floor — the whole
        # point of the setting is to keep that energy for later in the
        # household's own evening peak rather than sell or spend it now.
        if is_evening:
            reserve_kwh = evening_reserve * battery.capacity_kwh
            available_kwh = max(0.0, battery.stored_kwh - reserve_kwh)
            available_kw = available_kwh / duration_h if duration_h > 0 else 0.0
            requestable_kw = min(shortfall_kw, available_kw)
        else:
            requestable_kw = shortfall_kw

        new_battery, delivered_kw = discharge(battery, requestable_kw, duration_h)
        remaining_shortfall_kw = shortfall_kw - delivered_kw
        action = BatteryAction.DISCHARGING if delivered_kw > 0 else BatteryAction.IDLE
        return PositionPlan(
            battery=new_battery,
            battery_action=action,
            battery_kw=delivered_kw,
            net_for_market_kw=-remaining_shortfall_kw,
        )

    return PositionPlan(
        battery=battery,
        battery_action=BatteryAction.IDLE,
        battery_kw=0.0,
        net_for_market_kw=0.0,
    )


def reservation_price(
    *, net_for_market_kw: float, feed_in_tariff: float, retail_tariff: float
) -> float:
    """The worst price at which trading still beats the utility.

    A seller never asks below the feed-in tariff; a buyer never bids above the
    retail tariff. This is what makes objective O6 (nobody worse off than not
    trading) a structural property of every order rather than a hope about
    where the market happens to clear.
    """
    return feed_in_tariff if net_for_market_kw > 0 else retail_tariff
