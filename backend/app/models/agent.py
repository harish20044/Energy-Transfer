"""Persistence for the household agents: what each one has learned, and every
decision it made in the current planning session with its reasons and
outcome."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AgentMemoryRecord(Base):
    """One row per household agent. Deliberately *not* wiped when a new
    session starts: an agent keeps what it has learned about the market from
    one session to the next, the way a real one would."""

    __tablename__ = "agent_memory"

    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), primary_key=True)
    sell_margin: Mapped[float] = mapped_column(Float)
    buy_margin: Mapped[float] = mapped_column(Float)
    # 24 learned clearing prices by hour of day; null where never observed.
    price_by_hour: Mapped[list[Any]] = mapped_column(JSON)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    kwh_sold: Mapped[float] = mapped_column(Float, default=0.0)
    kwh_bought: Mapped[float] = mapped_column(Float, default=0.0)
    savings_inr: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AgentDecisionRecord(Base):
    """One agent's decision for one hourly slot of the session — the
    auditable record of what it offered, why, and how it turned out."""

    __tablename__ = "agent_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot: Mapped[int] = mapped_column(Integer, index=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    hour_of_day: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))
    firm: Mapped[bool] = mapped_column(default=False)
    quantity_kwh: Mapped[float] = mapped_column(Float)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_quantile: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_price: Mapped[float] = mapped_column(Float)
    spill_kwh: Mapped[float] = mapped_column(Float)
    short_kwh: Mapped[float] = mapped_column(Float)
    stored_kwh: Mapped[float] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text, default="")
    reasons: Mapped[list[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
