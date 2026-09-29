"""Persistence for the current planning session: each household's starting
conditions and what-ifs, its forecast, and its position in every hourly
slot once the ahead market has cleared.

Market records shared with the rest of the schema (`negotiation_offers`,
`trades`, `curtailments`, `ledger_entries`) key on the slot through their
`tick_index` column; `meter_readings.tick_index` counts 15-minute intervals
delivered since the session started.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SessionHousehold(Base):
    """A household's starting point and "what if" for the session."""

    __tablename__ = "session_households"

    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), primary_key=True)
    start_soc: Mapped[float] = mapped_column(Float)
    guests: Mapped[int] = mapped_column(Integer, default=0)
    away_from: Mapped[float | None] = mapped_column(Float, nullable=True)
    away_to: Mapped[float | None] = mapped_column(Float, nullable=True)
    work_from_home: Mapped[bool] = mapped_column(Boolean, default=False)
    panel_derate: Mapped[float] = mapped_column(Float, default=0.0)
    # The battery this household has for the session (0 = none) — the
    # household's own by default, or a what-if.
    battery_capacity_kwh: Mapped[float] = mapped_column(Float)


class SessionForecast(Base):
    """One household's forecast for one slot, as its agent saw it."""

    __tablename__ = "session_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[int] = mapped_column(Integer, index=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    day: Mapped[date] = mapped_column(Date)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    consumption_p10: Mapped[float] = mapped_column(Float)
    consumption_p50: Mapped[float] = mapped_column(Float)
    consumption_p90: Mapped[float] = mapped_column(Float)
    generation_p10: Mapped[float] = mapped_column(Float)
    generation_p50: Mapped[float] = mapped_column(Float)
    generation_p90: Mapped[float] = mapped_column(Float)


class SessionPosition(Base):
    """A household's contracted position for one slot after the market
    cleared: what it traded with neighbours and what the EB was scheduled
    to cover, at that slot's tariffs."""

    __tablename__ = "session_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[int] = mapped_column(Integer, index=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    p2p_sold_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    p2p_bought_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    eb_bought_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    eb_sold_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    unserved_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    retail_tariff: Mapped[float] = mapped_column(Float)
    feed_in_tariff: Mapped[float] = mapped_column(Float)
    eb_available: Mapped[bool] = mapped_column(Boolean, default=True)
