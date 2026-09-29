"""Household agents: one autonomous trading agent per home.

Each agent is a LangGraph decision graph (`app.agents.household_agent`) that
every tick perceives its household's meter and battery, reads its own 4-hour
forecast, plans how much charge to hold back, prices its offer from what it
has learned about the market (`app.agents.memory`), and says what it's doing
and why in plain language (`app.agents.speech`). The decision is
deterministic and auditable; the market clamps it into the tariff band, so
no agent can ever leave its household worse off than trading with the grid.

The LLM sits beside that path, never in it (ADR-0005): `app.agents.advisor`
lets a household talk to its agent — ask why it sold at 2 pm, or tell it to
keep more charge for the evening — through a tool-calling LLM
(`app.agents.llm`) that reads the agent's real decision records.
"""

from __future__ import annotations
