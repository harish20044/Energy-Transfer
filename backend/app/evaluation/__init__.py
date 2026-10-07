"""The evaluation harness: measures objectives O1-O7 (`docs/objectives.md`)
on a fixed, seeded suite of planning sessions, run in memory with the same
market, agents, forecaster and delivery code the app runs.

    docker exec energy-backend python -m app.evaluation

writes `docs/evaluation.md` (the O1-O7 table, with method notes) and
`docs/evaluation.json` (every number behind it).
"""
