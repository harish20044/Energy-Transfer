"""Battery charge/discharge physics."""

from __future__ import annotations

import pytest

from app.domain.battery.model import Battery, charge, discharge

pytestmark = pytest.mark.unit


def _battery(soc: float = 0.5) -> Battery:
    return Battery(capacity_kwh=10.0, soc=soc, max_charge_kw=5.0, max_discharge_kw=5.0)


def test_soc_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="soc must be in"):
        Battery(capacity_kwh=10.0, soc=1.5, max_charge_kw=5.0, max_discharge_kw=5.0)


def test_nonpositive_capacity_is_rejected() -> None:
    with pytest.raises(ValueError, match="capacity_kwh must be positive"):
        Battery(capacity_kwh=0.0, soc=0.5, max_charge_kw=5.0, max_discharge_kw=5.0)


def test_charge_increases_soc() -> None:
    battery = _battery(soc=0.5)
    new_battery, accepted_kw = charge(battery, available_kw=2.0, duration_h=1.0)

    assert new_battery.soc > battery.soc
    assert accepted_kw > 0


def test_charge_is_clamped_by_max_charge_rate() -> None:
    battery = _battery(soc=0.1)
    _new_battery, accepted_kw = charge(battery, available_kw=100.0, duration_h=1.0)

    assert accepted_kw == pytest.approx(battery.max_charge_kw)


def test_charge_stops_at_full() -> None:
    battery = _battery(soc=0.99)
    new_battery, _accepted_kw = charge(battery, available_kw=5.0, duration_h=1.0)

    assert new_battery.soc <= 1.0


def test_round_trip_efficiency_loses_energy() -> None:
    """A perfectly efficient battery would store exactly what it drew; a real
    one stores less, and that loss must show up as reduced sellable surplus
    later, not disappear silently."""
    battery = Battery(
        capacity_kwh=10.0,
        soc=0.0,
        max_charge_kw=5.0,
        max_discharge_kw=5.0,
        round_trip_efficiency=0.9,
    )
    new_battery, accepted_kw = charge(battery, available_kw=2.0, duration_h=1.0)

    stored_kwh = new_battery.stored_kwh
    drawn_kwh = accepted_kw * 1.0
    assert stored_kwh < drawn_kwh
    assert stored_kwh == pytest.approx(drawn_kwh * 0.9)


def test_discharge_decreases_soc() -> None:
    battery = _battery(soc=0.5)
    new_battery, delivered_kw = discharge(battery, requested_kw=2.0, duration_h=1.0)

    assert new_battery.soc < battery.soc
    assert delivered_kw > 0


def test_discharge_is_clamped_by_max_discharge_rate() -> None:
    battery = _battery(soc=1.0)
    _new_battery, delivered_kw = discharge(battery, requested_kw=100.0, duration_h=1.0)

    assert delivered_kw == pytest.approx(battery.max_discharge_kw)


def test_discharge_cannot_go_below_empty() -> None:
    battery = _battery(soc=0.05)
    new_battery, _delivered_kw = discharge(battery, requested_kw=5.0, duration_h=1.0)

    assert new_battery.soc >= 0.0


def test_zero_or_negative_power_is_a_no_op() -> None:
    battery = _battery()
    unchanged, accepted = charge(battery, available_kw=0.0, duration_h=1.0)
    assert unchanged == battery
    assert accepted == 0.0

    unchanged2, delivered = discharge(battery, requested_kw=-1.0, duration_h=1.0)
    assert unchanged2 == battery
    assert delivered == 0.0
