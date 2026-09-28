"""Persistence for the running simulation: one row per tick's clock state,
one row per household per tick for meter readings, and one row per settled
trade, curtailment and ledger entry.

These mirror the domain layer's frozen dataclasses (`app.domain.market.auction.Trade`,
`app.domain.grid.safety.Curtailment`, `app.domain.ledger.hashchain.LedgerEntry`)
field-for-field. Kept as distinct ORM classes rather than reusing those names
so an import site is never ambiguous about which one — a pure in-memory
value versus a persisted row — it is holding.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SIMULATION_STATE_SINGLETON_ID = 1


class SimulationState(Base):
    """The shared simulation clock — one row, all households on one feeder
    watch the same clock and trade in the same ticks."""

    __tablename__ = "simulation_state"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, default=SIMULATION_STATE_SINGLETON_ID
    )
    tick_index: Mapped[int] = mapped_column(Integer, default=0)
    running: Mapped[bool] = mapped_column(Boolean, default=False)
    scenario: Mapped[str] = mapped_column(String(20), default="clear")
    # Real seconds between ticks while running — this is what "accelerated
    # clock" means in practice: a 15-minute simulated tick every few real
    # seconds instead of every 15 real minutes.
    seconds_per_tick: Mapped[float] = mapped_column(Float, default=2.0)
    # Set from application code (app.engine.runner), not a server-side
    # `onupdate` — a server-computed value on UPDATE would mark this column
    # expired and force a synchronous reload the moment it's read after
    # commit, which breaks under the async driver (MissingGreenlet).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class MeterReading(Base):
    """One household's generation, consumption and battery state for one tick."""

    __tablename__ = "meter_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_index: Mapped[int] = mapped_column(Integer, index=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    consumption_kw: Mapped[float] = mapped_column(Float)
    generation_kw: Mapped[float] = mapped_column(Float)
    battery_soc: Mapped[float] = mapped_column(Float)
    battery_action: Mapped[str] = mapped_column(String(20))
    # Unmatched position settled directly with the grid, outside the P2P
    # market: positive = imported from the grid, negative = exported to it.
    grid_kwh: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeRecord(Base):
    """One matched, safety-approved trade from one tick's negotiation."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_index: Mapped[int] = mapped_column(Integer, index=True)
    # Which negotiation round this pair actually crossed at — 0 means they
    # matched immediately; a household whose battery is nearly full or empty
    # concedes faster and tends to match in an earlier round than one with
    # headroom to be patient. See app.domain.market.negotiation.
    round_index: Mapped[int] = mapped_column(Integer)
    buyer_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    seller_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    kwh: Mapped[float] = mapped_column(Float)
    price_per_kwh: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NegotiationOfferRecord(Base):
    """One household's ask or bid at one round of one tick's negotiation —
    the raw material for replaying "watch them negotiate" in the UI."""

    __tablename__ = "negotiation_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_index: Mapped[int] = mapped_column(Integer, index=True)
    round_index: Mapped[int] = mapped_column(Integer)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))  # "ask" or "bid"
    price: Mapped[float] = mapped_column(Float)
    kwh: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CurtailmentRecord(Base):
    """One trade the grid safety layer had to cut back, and why."""

    __tablename__ = "curtailments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_index: Mapped[int] = mapped_column(Integer, index=True)
    buyer_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    seller_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    curtailed_kwh: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LedgerEntryRecord(Base):
    """One link in the hash-chained settlement ledger.

    `sequence` is the primary key and must exactly match its position in the
    chain (`app.domain.ledger.hashchain.append` derives it from `len(chain)`),
    since the hash of every entry depends on the sequence number of the one
    before it.
    """

    __tablename__ = "ledger_entries"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    tick_index: Mapped[int] = mapped_column(Integer, index=True)
    buyer_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    seller_household_id: Mapped[str] = mapped_column(ForeignKey("households.id"), index=True)
    kwh: Mapped[float] = mapped_column(Float)
    price_per_kwh: Mapped[float] = mapped_column(Float)
    total_amount: Mapped[float] = mapped_column(Float)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
