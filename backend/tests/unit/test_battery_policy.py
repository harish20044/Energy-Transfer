"""Turning net generation into a battery action and a market position —
including the evening-reserve setting that must be a real behavioural
control, not a decoration."""

from __future__ import annotations

import pytest

from app.domain.battery.model import Battery
from app.domain.battery.policy import BatteryAction, plan_position, reservation_price

pytestmark = pytest.mark.unit


def _battery(soc: float) -> Battery:
    return Battery(capacity_kwh=10.0, soc=soc, max_charge_kw=5.0, max_discharge_kw=5.0)


def test_surplus_charges_the_battery_first() -> None:
    plan = plan_position(
        _battery(soc=0.3),
        net_generation_kw=2.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.battery_action is BatteryAction.CHARGING
    assert plan.battery.soc > 0.3


def test_surplus_beyond_battery_headroom_goes_to_market() -> None:
    plan = plan_position(
        _battery(soc=0.99),  # almost full, tiny headroom
        net_generation_kw=5.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.net_for_market_kw > 0
    assert plan.net_for_market_kw < 5.0  # some of it did still charge the sliver of headroom


def test_shortfall_discharges_the_battery_first() -> None:
    """A shortfall well within the battery's reach is fully covered by it —
    and if there's still charge to spare above the reserve floor once that's
    done, the household doesn't just stop there, it sells the rest (see
    test_spare_charge_after_covering_a_shortfall_is_sold)."""
    plan = plan_position(
        _battery(soc=0.8),
        net_generation_kw=-2.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.battery_action is BatteryAction.DISCHARGING
    assert plan.battery.soc < 0.8
    assert plan.net_for_market_kw >= 0  # shortfall fully met, nothing left to buy


def test_evening_reserve_blocks_discharge_below_the_floor() -> None:
    """The setting a user actually controls from the dashboard: once it is
    evening, the battery must not be drained past the configured reserve."""
    battery = _battery(soc=0.45)  # just above a 0.4 reserve
    plan = plan_position(
        battery, net_generation_kw=-3.0, duration_h=1.0, evening_reserve=0.4, is_evening=True
    )

    assert plan.battery.soc >= 0.4 - 1e-9
    # Only a little energy was available above the reserve, so most of the
    # shortfall had to be met by buying from the market instead.
    assert plan.net_for_market_kw < 0


def test_evening_reserve_does_not_apply_outside_the_evening() -> None:
    """The same low SoC, but daytime — the household may discharge freely."""
    battery = _battery(soc=0.45)
    plan = plan_position(
        battery, net_generation_kw=-3.0, duration_h=1.0, evening_reserve=0.4, is_evening=False
    )

    assert plan.battery.soc < 0.4  # reserve was not enforced
    assert plan.net_for_market_kw == pytest.approx(0.0)  # shortfall fully met by the battery


def test_evening_reserve_never_blocks_charging() -> None:
    """The reserve is a floor on discharging, never a ceiling on charging —
    a household should always accept genuine surplus."""
    plan = plan_position(
        _battery(soc=0.3),
        net_generation_kw=2.0,
        duration_h=1.0,
        evening_reserve=0.9,  # a high reserve
        is_evening=True,
    )

    assert plan.battery_action is BatteryAction.CHARGING


def test_a_balanced_position_at_the_reserve_floor_is_truly_idle() -> None:
    """Nothing to cover and nothing spare above the reserve floor — this is
    the one case that's genuinely idle, not just an empty real-time position
    (see test_a_balanced_household_with_spare_charge_sells_it for the case
    where there's charge to spare)."""
    plan = plan_position(
        _battery(soc=0.4),
        net_generation_kw=0.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.battery_action is BatteryAction.IDLE
    assert plan.battery_kw == 0.0
    assert plan.net_for_market_kw == 0.0


def test_a_balanced_household_with_spare_charge_sells_it() -> None:
    """The core of arbitrage: a household with nothing to buy or cover, but
    real charge sitting above its own reserve floor, doesn't just sit on it —
    it's a real, spare asset, so it's offered to the market."""
    plan = plan_position(
        _battery(soc=0.5),  # 10% above a 0.4 reserve on a 10 kWh battery = 1 kWh spare
        net_generation_kw=0.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.battery_action is BatteryAction.DISCHARGING
    assert plan.net_for_market_kw == pytest.approx(1.0)
    assert plan.battery.soc == pytest.approx(0.4)  # sold down to the reserve floor, not past it


def test_spare_charge_after_covering_a_shortfall_is_sold() -> None:
    """A household whose battery covers its own shortfall with room to spare
    doesn't stop there — the remaining headroom above reserve is sold too,
    in the same tick, as one combined discharge."""
    plan = plan_position(
        _battery(soc=0.8),
        net_generation_kw=-2.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    # 0.8 -> 0.4 is 4 kWh of headroom; 2 kW for 1h covers the shortfall,
    # leaving 2 kWh (2 kW for the remaining hour) to sell.
    assert plan.net_for_market_kw == pytest.approx(2.0)
    assert plan.battery.soc == pytest.approx(0.4)


def test_arbitrage_never_sells_below_the_reserve_floor() -> None:
    battery = _battery(soc=0.42)  # only a sliver above a 0.4 reserve
    plan = plan_position(
        battery, net_generation_kw=0.0, duration_h=1.0, evening_reserve=0.4, is_evening=False
    )

    assert plan.battery.soc >= 0.4 - 1e-9
    assert plan.net_for_market_kw == pytest.approx(0.2)  # only the sliver, not more


def test_arbitrage_respects_the_max_discharge_rate() -> None:
    """A battery with plenty of spare energy still can't discharge faster
    than its physical rate limit."""
    battery = Battery(capacity_kwh=10.0, soc=0.9, max_charge_kw=5.0, max_discharge_kw=2.0)
    plan = plan_position(
        battery, net_generation_kw=0.0, duration_h=1.0, evening_reserve=0.4, is_evening=False
    )

    assert plan.net_for_market_kw <= 2.0 + 1e-9


def test_a_battery_already_charging_never_also_arbitrages() -> None:
    """A single inverter can't charge and discharge in the same tick — a
    household mid-charge from real surplus never also sells stored energy
    alongside it, no matter how much spare charge it's sitting on."""
    plan = plan_position(
        _battery(soc=0.5),  # well above the reserve floor already
        net_generation_kw=1.0,
        duration_h=1.0,
        evening_reserve=0.4,
        is_evening=False,
    )

    assert plan.battery_action is BatteryAction.CHARGING
    assert plan.net_for_market_kw == pytest.approx(0.0)


def test_reservation_price_floors_a_sale_at_the_feed_in_tariff() -> None:
    price = reservation_price(net_for_market_kw=2.0, feed_in_tariff=3.0, retail_tariff=8.0)
    assert price == 3.0


def test_reservation_price_ceilings_a_purchase_at_the_retail_tariff() -> None:
    price = reservation_price(net_for_market_kw=-2.0, feed_in_tariff=3.0, retail_tariff=8.0)
    assert price == 8.0
