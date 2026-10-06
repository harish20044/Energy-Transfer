"""A household's own agent: what it has learned, and a conversation with it.

Scoped to the caller's own household through its JWT, like everything under
`/households/me`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.agents.advisor import ToolContext, converse
from app.agents.household_agent import GRAPH_NODES
from app.agents.llm import get_provider
from app.agents.memory import AgentMemory
from app.agents.persistence import from_record
from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.models.agent import AgentMemoryRecord
from app.models.household import Household
from app.schemas.agent import AgentMemoryOut, ChatIn, ChatOut

router = APIRouter(prefix="/agents", tags=["agents"])


async def _own_household(current_user: CurrentUserDep, db: DbDep) -> Household:
    if current_user.household_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This account is not linked to a household",
        )
    household = await db.get(Household, current_user.household_id)
    if household is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    return household


@router.get("/me", response_model=AgentMemoryOut)
async def read_own_agent(current_user: CurrentUserDep, db: DbDep) -> AgentMemoryOut:
    household = await _own_household(current_user, db)
    record = await db.get(AgentMemoryRecord, household.id)
    memory = from_record(record) if record else AgentMemory()
    return AgentMemoryOut(
        household_id=household.id,
        sell_margin=memory.sell_margin,
        buy_margin=memory.buy_margin,
        price_by_hour=list(memory.price_by_hour),
        trades=memory.trades,
        units_sold=memory.kwh_sold,
        units_bought=memory.kwh_bought,
        savings_inr=memory.savings_inr,
        graph_nodes=list(GRAPH_NODES),
    )


@router.post("/me/chat", response_model=ChatOut)
async def chat(
    body: ChatIn, current_user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> ChatOut:
    """Ask the household's agent anything about its plan, its trades or the
    family's electricity — or tell it to keep more charge in reserve."""
    household = await _own_household(current_user, db)
    configured = get_provider(settings)
    reply, tools_used, provider = await converse(
        ToolContext(db=db, user=current_user, household=household, settings=settings),
        configured,
        [turn.model_dump() for turn in body.history],
        body.message,
    )
    # After a fallback the stub answered, not the configured model.
    model = configured.model if provider == configured.name else ""
    return ChatOut(reply=reply, provider=provider, model=model, tools_used=tools_used)
