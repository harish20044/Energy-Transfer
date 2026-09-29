"""Wire contracts for a household's agent: what it has learned, and talking
to it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentMemoryOut(BaseModel):
    """What the agent has learned about the market across every session."""

    household_id: str
    sell_margin: float
    buy_margin: float
    # Its own price forecast: the clearing price it has learned for each
    # hour of the day (null where it hasn't traded or watched a trade yet).
    price_by_hour: list[float | None]
    trades: int
    units_sold: float
    units_bought: float
    savings_inr: float
    graph_nodes: list[str]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class ChatOut(BaseModel):
    reply: str
    provider: str
    tools_used: list[str]
