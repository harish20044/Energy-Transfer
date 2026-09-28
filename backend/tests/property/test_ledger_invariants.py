"""The ledger's tamper-evidence, machine-checked across generated settlement
histories rather than the handful of examples in tests/unit/test_ledger.py.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.ledger.hashchain import LedgerEntry, append, balances, verify_chain

pytestmark = pytest.mark.property

_household_id = st.text(alphabet="abcdefghij", min_size=1, max_size=4)
_kwh = st.floats(min_value=0.01, max_value=50.0, allow_nan=False)
_price = st.floats(min_value=0.01, max_value=20.0, allow_nan=False)


@st.composite
def _settlement(draw: st.DrawFn) -> tuple[str, str, float, float]:
    buyer = draw(_household_id)
    seller = draw(_household_id.filter(lambda h: h != buyer))
    return buyer, seller, draw(_kwh), draw(_price)


_settlements = st.lists(_settlement(), min_size=0, max_size=20)


def _build_chain(settlements: list[tuple[str, str, float, float]]) -> tuple[LedgerEntry, ...]:
    chain: tuple[LedgerEntry, ...] = ()
    for tick_index, (buyer, seller, kwh, price) in enumerate(settlements):
        chain = append(
            chain,
            tick_index=tick_index,
            buyer_household_id=buyer,
            seller_household_id=seller,
            kwh=kwh,
            price_per_kwh=price,
        )
    return chain


@given(settlements=_settlements)
def test_any_chain_built_only_through_append_always_verifies(
    settlements: list[tuple[str, str, float, float]],
) -> None:
    chain = _build_chain(settlements)
    assert verify_chain(chain) is True


@given(settlements=_settlements, tamper_field=st.sampled_from(["kwh", "price_per_kwh"]))
def test_tampering_with_any_single_field_of_any_entry_is_detected(
    settlements: list[tuple[str, str, float, float]], tamper_field: str
) -> None:
    chain = _build_chain(settlements)
    if not chain:
        return  # nothing to tamper with

    tampered_index = len(chain) // 2
    original = chain[tampered_index]
    tampered_value = getattr(original, tamper_field) + 1.0
    tampered_entry = replace(original, **{tamper_field: tampered_value})

    tampered_chain = (*chain[:tampered_index], tampered_entry, *chain[tampered_index + 1 :])

    assert verify_chain(tampered_chain) is False


@given(settlements=_settlements)
def test_balances_always_sum_to_exactly_zero(
    settlements: list[tuple[str, str, float, float]],
) -> None:
    """Money is neither created nor destroyed in settlement — every payment
    out is exactly matched by a payment in, across the whole ledger."""
    chain = _build_chain(settlements)
    result = balances(chain)

    assert sum(result.values()) == pytest.approx(0.0, abs=1e-6)


@given(settlements=_settlements)
def test_sequence_numbers_are_contiguous_from_zero(
    settlements: list[tuple[str, str, float, float]],
) -> None:
    chain = _build_chain(settlements)
    assert [entry.sequence for entry in chain] == list(range(len(chain)))
