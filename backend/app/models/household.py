"""The Household table: one row per house on the feeder.

`id` deliberately doubles as the household's bus id in the domain layer's
`Network` (see `app.domain.grid.network.default_feeder`), so a household row
never needs translating before it can be plugged into the pure market/grid
engine — there is exactly one identifier for "this house", not two kept in
sync by hand.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

DEFAULT_BATTERY_CAPACITY_KWH = 10.0
DEFAULT_BATTERY_MAX_CHARGE_KW = 3.0
DEFAULT_BATTERY_MAX_DISCHARGE_KW = 3.0
DEFAULT_EVENING_RESERVE = 0.4


class Household(Base):
    """A house on the feeder — the unit every login, meter reading, order and
    trade is ultimately scoped to."""

    __tablename__ = "households"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    member_count: Mapped[int] = mapped_column(Integer, default=4)

    solar_capacity_kwp: Mapped[float] = mapped_column(Float, default=4.0)
    battery_capacity_kwh: Mapped[float] = mapped_column(
        Float, default=DEFAULT_BATTERY_CAPACITY_KWH
    )
    battery_max_charge_kw: Mapped[float] = mapped_column(
        Float, default=DEFAULT_BATTERY_MAX_CHARGE_KW
    )
    battery_max_discharge_kw: Mapped[float] = mapped_column(
        Float, default=DEFAULT_BATTERY_MAX_DISCHARGE_KW
    )

    # The one setting a household actually controls from the dashboard — read
    # by app.domain.battery.policy.plan_position on every tick, not baked in.
    evening_reserve: Mapped[float] = mapped_column(Float, default=DEFAULT_EVENING_RESERVE)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
