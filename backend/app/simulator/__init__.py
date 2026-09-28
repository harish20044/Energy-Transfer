"""Synthetic environment generation: what each household's meter would have
read. Deliberately separate from `app.domain` (ADR-0006) — this package is
allowed randomness and a notion of simulated time, because it stands in for
the physical world the domain layer reacts to, not for a trading decision."""
