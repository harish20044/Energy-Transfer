"""The database-backed simulation runner: loads state, calls the pure
`app.domain.engine.tick.run_tick`, and persists the result — plus the
background loop that advances it on an accelerated clock while playing."""
