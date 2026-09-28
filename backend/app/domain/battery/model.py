"""Battery state and physics.

Pure per ADR-0006: no clock, no I/O, no randomness. A tick calls
`charge`/`discharge` with an explicit duration and gets back a *new*
:class:`Battery` — nothing here mutates in place, so the same call replayed
with the same inputs always produces the same result.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Battery:
    """One household's storage.

    `soc` is state of charge as a fraction of `capacity_kwh` (0.0-1.0), not an
    absolute energy amount — this keeps the reserve policy in
    `battery.policy` unit-agnostic across households with different battery
    sizes.
    """

    capacity_kwh: float
    soc: float
    max_charge_kw: float
    max_discharge_kw: float
    # Round-trip efficiency is charged against the *stored* side: 1 kWh drawn
    # from the grid/solar to charge the battery yields less than 1 kWh back
    # out. Typical lithium-ion round-trip efficiency is 90-95%.
    round_trip_efficiency: float = 0.92

    def __post_init__(self) -> None:
        if not 0.0 <= self.soc <= 1.0:
            msg = f"soc must be in [0, 1], got {self.soc}"
            raise ValueError(msg)
        if self.capacity_kwh <= 0:
            msg = f"capacity_kwh must be positive, got {self.capacity_kwh}"
            raise ValueError(msg)

    @property
    def stored_kwh(self) -> float:
        return self.soc * self.capacity_kwh

    @property
    def headroom_kwh(self) -> float:
        """Energy that can still be *added* before the battery is full."""
        return (1.0 - self.soc) * self.capacity_kwh


def charge(battery: Battery, available_kw: float, duration_h: float) -> tuple[Battery, float]:
    """Charge for `duration_h` at up to `available_kw`, clamped by the
    battery's own charge-rate and remaining headroom.

    Returns the new battery state and the power actually accepted — which the
    caller needs, because "how much did the battery actually take" is what
    determines how much surplus is left over to sell.
    """
    if available_kw <= 0 or duration_h <= 0:
        return battery, 0.0

    accepted_kw = min(available_kw, battery.max_charge_kw)
    energy_in_kwh = accepted_kw * duration_h
    # Efficiency loss happens going *into* storage: less ends up stored than
    # was drawn from the source.
    stored_gain_kwh = min(energy_in_kwh * battery.round_trip_efficiency, battery.headroom_kwh)

    # Re-derive the accepted power from what actually fit, so a battery near
    # full never appears to have accepted more than its headroom allowed.
    actual_energy_in_kwh = stored_gain_kwh / battery.round_trip_efficiency
    actual_kw = actual_energy_in_kwh / duration_h

    new_soc = battery.soc + stored_gain_kwh / battery.capacity_kwh
    return _with_soc(battery, new_soc), actual_kw


def discharge(battery: Battery, requested_kw: float, duration_h: float) -> tuple[Battery, float]:
    """Discharge for `duration_h` at up to `requested_kw`, clamped by the
    battery's own discharge-rate and remaining stored energy.

    Returns the new battery state and the power actually delivered.
    """
    if requested_kw <= 0 or duration_h <= 0:
        return battery, 0.0

    deliverable_kw = min(requested_kw, battery.max_discharge_kw)
    requested_energy_kwh = deliverable_kw * duration_h
    delivered_energy_kwh = min(requested_energy_kwh, battery.stored_kwh)

    actual_kw = delivered_energy_kwh / duration_h
    new_soc = battery.soc - delivered_energy_kwh / battery.capacity_kwh
    return _with_soc(battery, new_soc), actual_kw


def _with_soc(battery: Battery, soc: float) -> Battery:
    """Clamp to [0, 1] before constructing — floating-point drift from many
    small charge/discharge calls could otherwise push soc a hair outside the
    valid range and trip the dataclass's own validation."""
    clamped = min(1.0, max(0.0, soc))
    return Battery(
        capacity_kwh=battery.capacity_kwh,
        soc=clamped,
        max_charge_kw=battery.max_charge_kw,
        max_discharge_kw=battery.max_discharge_kw,
        round_trip_efficiency=battery.round_trip_efficiency,
    )
