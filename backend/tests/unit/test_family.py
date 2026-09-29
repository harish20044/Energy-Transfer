"""Family composition and daily routines: deterministic, demographically
plausible, and time-of-day aware — who's home, away or asleep depends on
the hour, the weekday and the family's own what-ifs."""

from __future__ import annotations

from datetime import date

import pytest

from app.simulator.family import (
    BEDROOMS,
    HouseholdOverride,
    MemberDay,
    Occupation,
    Role,
    Status,
    generate_family,
    member_days,
    status_at,
    with_guests,
)

pytestmark = pytest.mark.unit

SEED = 42
WEEKDAY = date(2026, 5, 13)  # a Wednesday
SUNDAY = date(2026, 5, 17)


def test_family_generation_is_deterministic() -> None:
    assert generate_family("h1", 4, SEED) == generate_family("h1", 4, SEED)


def test_different_households_get_different_families() -> None:
    assert generate_family("h1", 4, SEED).members != generate_family("h2", 4, SEED).members


def test_every_household_has_exactly_one_couple_in_room_one() -> None:
    for member_count in range(2, 7):
        family = generate_family("h3", member_count, SEED)
        parents = [m for m in family.members if m.role is Role.PARENT]
        assert len(parents) == 2
        assert all(m.room == 1 for m in parents)


def test_member_count_is_respected() -> None:
    for member_count in range(1, 7):
        assert len(generate_family("h5", member_count, SEED).members) == member_count


def test_young_children_share_the_parents_room() -> None:
    for household_id in (f"h{i}" for i in range(1, 11)):
        for member in generate_family(household_id, 6, SEED).members:
            if member.role is Role.CHILD and member.age < 10:
                assert member.room is None
                assert member.sleeping_room == 1


def test_older_children_get_a_bedroom() -> None:
    for household_id in (f"h{i}" for i in range(1, 11)):
        for member in generate_family(household_id, 6, SEED).members:
            if member.role is Role.CHILD and member.age >= 10:
                assert member.room is not None


def test_occupied_bedrooms_never_exceed_the_house() -> None:
    for member_count in range(1, 9):
        assert generate_family("h7", member_count, SEED).occupied_bedrooms <= BEDROOMS


def test_a_parents_age_at_every_childs_birth_is_biologically_plausible() -> None:
    """Guards against a 52-year-old parent with a newborn: a parent's age is
    derived from when each child was born, not sampled independently."""
    for household_id in (f"h{i}" for i in range(1, 11)):
        for member_count in range(2, 7):
            family = generate_family(household_id, member_count, SEED)
            parent = next(m for m in family.members if m.role is Role.PARENT)
            for child in (m for m in family.members if m.role is Role.CHILD):
                assert 15 <= parent.age - child.age <= 45


def test_grandparents_are_a_generation_older_and_retired() -> None:
    found = False
    for household_id in (f"h{i}" for i in range(1, 30)):
        family = generate_family(household_id, 6, SEED)
        parent = next(m for m in family.members if m.role is Role.PARENT)
        for grandparent in (m for m in family.members if m.role is Role.GRANDPARENT):
            found = True
            assert grandparent.occupation is Occupation.RETIRED
            assert grandparent.age - parent.age >= 20
    assert found, "six-member households should often be joint families"


def test_occupations_fit_ages() -> None:
    for household_id in (f"h{i}" for i in range(1, 30)):
        for member in generate_family(household_id, 5, SEED).members:
            if member.occupation is Occupation.SCHOOL:
                assert 6 <= member.age < 18
            if member.occupation is Occupation.INFANT:
                assert member.age < 3


def _office_worker_household() -> tuple[str, int]:
    for i in range(1, 60):
        family = generate_family(f"x{i}", 4, SEED)
        if any(m.occupation is Occupation.OFFICE for m in family.members):
            return f"x{i}", i
    raise AssertionError("no household with an office worker")


def test_an_office_worker_is_away_at_midday_on_a_weekday_and_home_on_sunday() -> None:
    household_id, _ = _office_worker_household()
    family = generate_family(household_id, 4, SEED)
    index = next(i for i, m in enumerate(family.members) if m.occupation is Occupation.OFFICE)
    assert status_at(member_days(family, WEEKDAY, SEED)[index], 12.0) is Status.AWAY
    assert status_at(member_days(family, SUNDAY, SEED)[index], 12.0) is not Status.AWAY


def test_everyone_sleeps_at_three_in_the_morning_on_an_ordinary_night() -> None:
    family = generate_family("h1", 4, SEED)
    for member, day in zip(family.members, member_days(family, WEEKDAY, SEED), strict=True):
        if member.occupation is not Occupation.NIGHT_SHIFT:
            assert status_at(day, 3.0) is Status.ASLEEP


def test_a_night_shift_worker_sleeps_through_the_morning_and_works_at_night() -> None:
    day = MemberDay(wake_h=12.5, sleep_h=4.5, away=((18.5, 27.5),))
    assert status_at(day, 9.0) is Status.ASLEEP
    assert status_at(day, 15.0) is Status.HOME
    assert status_at(day, 22.0) is Status.AWAY
    assert status_at(day, 2.0) is Status.AWAY  # the shift runs past midnight


def test_sleep_can_start_after_midnight() -> None:
    day = MemberDay(wake_h=7.0, sleep_h=24.5, away=())
    assert status_at(day, 0.25) is Status.HOME
    assert status_at(day, 3.0) is Status.ASLEEP


def test_a_family_away_window_puts_everyone_out() -> None:
    family = generate_family("h1", 4, SEED)
    override = HouseholdOverride(away_from=18.0, away_to=22.0)
    for day in member_days(family, SUNDAY, SEED, override):
        assert status_at(day, 20.0) is Status.AWAY


def test_an_away_window_past_midnight_continues_the_next_day() -> None:
    override = HouseholdOverride(away_from=20.0, away_to=26.0)
    assert override.away_at(21.0)
    assert not override.away_at(1.0)  # the start day's early hours are before the outing
    tomorrow = override.next_day()
    assert tomorrow.away_at(1.0)
    assert not tomorrow.away_at(3.0)


def test_work_from_home_keeps_office_workers_home() -> None:
    household_id, _ = _office_worker_household()
    family = generate_family(household_id, 4, SEED)
    index = next(i for i, m in enumerate(family.members) if m.occupation is Occupation.OFFICE)
    days = member_days(family, WEEKDAY, SEED, HouseholdOverride(work_from_home=True))
    assert status_at(days[index], 12.0) is Status.HOME


def test_guests_join_the_household_in_free_bedrooms() -> None:
    family = generate_family("h4", 2, SEED)  # a couple: three bedrooms free
    visited = with_guests(family, 2)
    guests = [m for m in visited.members if m.role is Role.GUEST]
    assert len(guests) == 2
    assert all(g.room == guests[0].room for g in guests)  # a pair shares a room
    assert visited.occupied_bedrooms == family.occupied_bedrooms + 1


def test_guests_with_no_free_bedroom_sleep_in_the_hall() -> None:
    family = generate_family("h5", 6, SEED)
    visited = with_guests(family, 4)
    guests = [m for m in visited.members if m.role is Role.GUEST]
    assert all(g.room is None or 1 <= g.room <= BEDROOMS for g in guests)
    assert visited.occupied_bedrooms <= BEDROOMS
