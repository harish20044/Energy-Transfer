"""An append-only, hash-chained settlement ledger.

Each entry embeds the hash of the entry before it, so altering any historical
entry changes its hash and breaks every link after it — tamper-evidence
without running an actual blockchain. `verify_chain` is what a dispute or an
audit calls to prove the history hasn't been edited.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    tick_index: int
    buyer_household_id: str
    seller_household_id: str
    kwh: float
    price_per_kwh: float
    total_amount: float
    prev_hash: str
    hash: str


def _compute_hash(
    *,
    sequence: int,
    tick_index: int,
    buyer_household_id: str,
    seller_household_id: str,
    kwh: float,
    price_per_kwh: float,
    total_amount: float,
    prev_hash: str,
) -> str:
    # Fixed field order and repr-based formatting (rather than str()) so a
    # float's exact representation is part of the hashed content — no
    # ambiguity between "5.4" and "5.40" silently producing the same hash.
    payload = "|".join(
        [
            str(sequence),
            str(tick_index),
            buyer_household_id,
            seller_household_id,
            repr(kwh),
            repr(price_per_kwh),
            repr(total_amount),
            prev_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append(
    chain: tuple[LedgerEntry, ...],
    *,
    tick_index: int,
    buyer_household_id: str,
    seller_household_id: str,
    kwh: float,
    price_per_kwh: float,
) -> tuple[LedgerEntry, ...]:
    """Return a new chain with one settled trade appended."""
    sequence = len(chain)
    prev_hash = chain[-1].hash if chain else GENESIS_HASH
    total_amount = round(kwh * price_per_kwh, 6)

    entry_hash = _compute_hash(
        sequence=sequence,
        tick_index=tick_index,
        buyer_household_id=buyer_household_id,
        seller_household_id=seller_household_id,
        kwh=kwh,
        price_per_kwh=price_per_kwh,
        total_amount=total_amount,
        prev_hash=prev_hash,
    )
    entry = LedgerEntry(
        sequence=sequence,
        tick_index=tick_index,
        buyer_household_id=buyer_household_id,
        seller_household_id=seller_household_id,
        kwh=kwh,
        price_per_kwh=price_per_kwh,
        total_amount=total_amount,
        prev_hash=prev_hash,
        hash=entry_hash,
    )
    return (*chain, entry)


def verify_chain(chain: tuple[LedgerEntry, ...]) -> bool:
    """True only if every entry's hash is genuinely derived from its own
    content and correctly links to the entry before it — false the moment
    any entry has been altered, reordered, or removed."""
    expected_prev_hash = GENESIS_HASH
    for index, entry in enumerate(chain):
        if entry.sequence != index or entry.prev_hash != expected_prev_hash:
            return False

        recomputed = _compute_hash(
            sequence=entry.sequence,
            tick_index=entry.tick_index,
            buyer_household_id=entry.buyer_household_id,
            seller_household_id=entry.seller_household_id,
            kwh=entry.kwh,
            price_per_kwh=entry.price_per_kwh,
            total_amount=entry.total_amount,
            prev_hash=entry.prev_hash,
        )
        if recomputed != entry.hash:
            return False

        expected_prev_hash = entry.hash
    return True


def balances(chain: tuple[LedgerEntry, ...]) -> dict[str, float]:
    """Net money position per household: positive means net received (sold
    more than bought), negative means net paid out."""
    result: dict[str, float] = {}
    for entry in chain:
        result[entry.seller_household_id] = (
            result.get(entry.seller_household_id, 0.0) + entry.total_amount
        )
        result[entry.buyer_household_id] = (
            result.get(entry.buyer_household_id, 0.0) - entry.total_amount
        )
    return result
