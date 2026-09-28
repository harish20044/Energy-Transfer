"""The hash-chained settlement ledger — append, verify, tamper detection."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.ledger.hashchain import GENESIS_HASH, append, balances, verify_chain

pytestmark = pytest.mark.unit


def test_empty_chain_verifies() -> None:
    assert verify_chain(()) is True


def test_first_entry_chains_to_genesis() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=2.0,
        price_per_kwh=5.0,
    )

    assert chain[0].prev_hash == GENESIS_HASH
    assert chain[0].sequence == 0
    assert verify_chain(chain) is True


def test_successive_entries_link_by_hash() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=1.0,
        price_per_kwh=5.0,
    )
    chain = append(
        chain,
        tick_index=1,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=2.0,
        price_per_kwh=5.5,
    )

    assert chain[1].prev_hash == chain[0].hash
    assert chain[1].sequence == 1
    assert verify_chain(chain) is True


def test_total_amount_is_kwh_times_price() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=3.0,
        price_per_kwh=5.4,
    )

    assert chain[0].total_amount == pytest.approx(16.2)


def test_tampering_with_an_entry_breaks_verification() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=2.0,
        price_per_kwh=5.0,
    )
    chain = append(
        chain,
        tick_index=1,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=1.0,
        price_per_kwh=5.0,
    )
    assert verify_chain(chain) is True

    tampered = (replace(chain[0], kwh=999.0), chain[1])

    assert verify_chain(tampered) is False


def test_reordering_entries_breaks_verification() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=1.0,
        price_per_kwh=5.0,
    )
    chain = append(
        chain,
        tick_index=1,
        buyer_household_id="b2",
        seller_household_id="s2",
        kwh=2.0,
        price_per_kwh=6.0,
    )

    reordered = (chain[1], chain[0])

    assert verify_chain(reordered) is False


def test_deleting_an_entry_breaks_verification() -> None:
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=1.0,
        price_per_kwh=5.0,
    )
    chain = append(
        chain,
        tick_index=1,
        buyer_household_id="b",
        seller_household_id="s",
        kwh=2.0,
        price_per_kwh=5.0,
    )

    truncated = (chain[1],)  # first entry removed, second left dangling

    assert verify_chain(truncated) is False


def test_balances_are_zero_sum() -> None:
    """Every rupee a buyer pays is exactly the rupee a seller receives — money
    can neither appear nor vanish in settlement."""
    chain = append(
        (),
        tick_index=0,
        buyer_household_id="b1",
        seller_household_id="s1",
        kwh=2.0,
        price_per_kwh=5.0,
    )
    chain = append(
        chain,
        tick_index=1,
        buyer_household_id="b2",
        seller_household_id="s1",
        kwh=1.0,
        price_per_kwh=5.0,
    )

    result = balances(chain)

    assert sum(result.values()) == pytest.approx(0.0)
    assert result["s1"] == pytest.approx(15.0)
    assert result["b1"] == pytest.approx(-10.0)
    assert result["b2"] == pytest.approx(-5.0)
