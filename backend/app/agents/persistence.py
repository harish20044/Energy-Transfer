"""Loading and saving what each agent has learned."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory import HOURS, AgentMemory
from app.models.agent import AgentMemoryRecord


def from_record(record: AgentMemoryRecord) -> AgentMemory:
    prices = tuple(float(p) if p is not None else None for p in record.price_by_hour)
    return AgentMemory(
        sell_margin=record.sell_margin,
        buy_margin=record.buy_margin,
        price_by_hour=prices if len(prices) == HOURS else (None,) * HOURS,
        trades=record.trades,
        kwh_sold=record.kwh_sold,
        kwh_bought=record.kwh_bought,
        savings_inr=record.savings_inr,
    )


async def load_memories(session: AsyncSession) -> dict[str, AgentMemory]:
    records = (await session.scalars(select(AgentMemoryRecord))).all()
    return {record.household_id: from_record(record) for record in records}


async def save_memory(session: AsyncSession, household_id: str, memory: AgentMemory) -> None:
    record = await session.get(AgentMemoryRecord, household_id)
    if record is None:
        record = AgentMemoryRecord(household_id=household_id)
        session.add(record)
    record.sell_margin = memory.sell_margin
    record.buy_margin = memory.buy_margin
    record.price_by_hour = list(memory.price_by_hour)
    record.trades = memory.trades
    record.kwh_sold = memory.kwh_sold
    record.kwh_bought = memory.kwh_bought
    record.savings_inr = memory.savings_inr
    record.updated_at = datetime.now(UTC)
