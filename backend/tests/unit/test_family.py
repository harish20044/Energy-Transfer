"""Family generation and room occupancy: deterministic, age-appropriate room
assignment, and AC draw that only ever comes from an occupied room."""

from __future__ import annotations

import pytest

from app.simulator.family import (
    BEDROOMS,
    Role,
    generate_family,
    snapshot_occupancy,
)

pytestmark = pytest.mark.unit

SEED = 42


def test_family_generation_is_deterministic() -> None:
    first = generate_family("h1", member_count=4, seed=SEED)
    second = generate_family("h1", member_count=4, seed=SEED)
    assert first == second


def test_different_households_get_different_families() -> None:
    h1 = generate_family("h1", member_count=4, seed=SEED)
    h2 = generate_family("h2", member_count=4, seed=SEED)
    assert h1.members != h2.members


def test_every_household_has_exactly_one_couple() -> None:
    family = generate_family("h3", member_count=5, seed=SEED)
    parents = [m for m in family.members if m.role is Role.PARENT]
    assert len(parents) == 2
    assert all(m.room == 1 for m in parents)


def test_a_two_person_household_is_just_the_couple() -> None:
    family = generate_family("h4", member_count=2, seed=SEED)
    assert len(family.members) == 2
    assert family.occupied_bedrooms == 1  # only the shared bedroom is in use


def test_young_children_stay_with_the_parents() -> None:
    """A child under the own-room threshold has no bedroom of their own —
    they're wherever the parents are."""
    family = generate_family("h5", member_count=6, seed=SEED)
    for member in family.members:
        if member.role is Role.CHILD and member.age < 10:
            assert member.room is None


def test_older_children_get_their_own_room() -> None:
    family = generate_family("h6", member_count=6, seed=SEED)
    for member in family.members:
        if member.role is Role.CHILD and member.age >= 10:
            assert member.room is not None


def test_occupied_bedrooms_never_exceeds_the_house() -> None:
    for member_count in range(2, 9):
        family = generate_family("h7", member_count=member_count, seed=SEED)
        assert family.occupied_bedrooms <= BEDROOMS


def test_member_ages_are_never_negative_or_absurd() -> None:
    family = generate_family("h8", member_count=6, seed=SEED)
    for member in family.members:
        assert 0 < member.age <= 90


def test_a_parents_age_at_every_childs_birth_is_biologically_plausible() -> None:
    """The bug this guards against: a parent's age is derived from when they
    actually had each child, not sampled independently — so a household can
    never end up with, say, a 52-year-old parent and a newborn."""
    for household_id in (f"h{i}" for i in range(1, 11)):
        for member_count in range(2, 7):
            family = generate_family(household_id, member_count, seed=SEED)
            parent = next(m for m in family.members if m.role is Role.PARENT)
            for child in (m for m in family.members if m.role is Role.CHILD):
                age_at_birth = parent.age - child.age
                assert 15 <= age_at_birth <= 45


def test_a_weekday_working_adult_is_away_during_office_hours() -> None:
    family = generate_family("h1", member_count=4, seed=SEED)
    weekday_office_hour = 12.0
    snapshot = snapshot_occupancy(family, weekday_office_hour, is_weekend=False, demand_factor=1.0)

    parents = [m for m in family.members if m.role is Role.PARENT and m.age < 60]
    assert any(not snapshot.home_now[m.index] for m in parents)


def test_everyone_is_generally_home_on_a_weekend() -> None:
    family = generate_family("h1", member_count=4, seed=SEED)
    weekday_office_hour = 12.0
    weekend_snapshot = snapshot_occupancy(
        family, weekday_office_hour, is_weekend=True, demand_factor=1.0
    )

    assert all(weekend_snapshot.home_now.values())


def test_ac_intensity_is_zero_in_every_unoccupied_room() -> None:
    family = generate_family("h4", member_count=2, seed=SEED)  # couple: 3 empty bedrooms
    snapshot = snapshot_occupancy(family, hour=2.0, is_weekend=False, demand_factor=1.0)

    unoccupied = [room for room in snapshot.rooms if not room.occupied]
    assert len(unoccupied) == 3
    assert all(room.ac_intensity == 0.0 for room in unoccupied)


def test_ac_intensity_is_positive_overnight_in_an_occupied_room() -> None:
    family = generate_family("h4", member_count=2, seed=SEED)
    late_night = 1.0
    snapshot = snapshot_occupancy(family, late_night, is_weekend=False, demand_factor=1.0)

    occupied = [room for room in snapshot.rooms if room.occupied]
    assert len(occupied) == 1
    assert occupied[0].ac_intensity > 0.0


def test_a_higher_demand_factor_never_pushes_intensity_past_full_duty() -> None:
    family = generate_family("h4", member_count=2, seed=SEED)
    for hour in range(24):
        snapshot = snapshot_occupancy(family, float(hour), is_weekend=False, demand_factor=3.0)
        for room in snapshot.rooms:
            assert room.ac_intensity <= 1.0
