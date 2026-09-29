"""Who lives in each house, and what their day actually looks like.

Every household shares one physical design — 4 bedrooms, one hall+kitchen,
5 washrooms, one AC per bedroom (4 total; the hall and kitchen have none) —
the common case for a planned residential development. What differs is the
family: its size, ages, who works where, and so who is home, awake or asleep
in which room at any given moment. That occupancy, not a headcount
multiplier, is what drives each appliance in `app.simulator.household`.

Composition is fixed per household (deterministic from its id and size).
Routines vary day to day but reproducibly from (household, date, seed), and
depend on the time of day the way real ones do:

- Office-goers leave ~8:15-9:15 and are back ~18:30-19:45 (Chennai traffic);
  hybrid IT workers are home on about half of weekdays; a minority work the
  US-facing night shift — out ~18:30-03:30, asleep through the late morning,
  a real Chennai IT pattern that puts AC load in the middle of the day.
- School runs ~7:30-16:00; many children then go to evening tuition
  (~17:30-19:00). College students are out ~8:00-17:00, some evenings too.
- Homemakers and retirees are home most of the day, with morning walks and
  evening temple/market trips. Weekends bring family outings.
- Families of 5-6 are usually joint families: grandparents live in.
- Children under 10 sleep in the parents' room.

A `HouseholdOverride` layers the user's "what if" on top: guests staying,
the family out for a window of time, or working from home that day.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace
from datetime import date
from enum import IntEnum, StrEnum

BEDROOMS = 4
WASHROOMS = 5
HALLS = 1
AC_UNITS = BEDROOMS  # one per bedroom; the hall/kitchen have none

PARENTS_ROOM = 1

_CHILDLESS_COUPLE_MIN_AGE = 25
_CHILDLESS_COUPLE_MAX_AGE = 65
_COUPLE_AGE_SPREAD = 5
_OWN_ROOM_MIN_AGE = 10  # younger than this, a child sleeps in the parents' room

# A parent's age is derived from *when they actually had each child*, not
# sampled independently — otherwise nothing stops a 52-year-old getting a
# newborn. NFHS-5 (2019-21) puts India's median age at first birth at 21.2,
# with a rising share of urban mothers starting after 30.
_PARENT_AGE_AT_FIRST_CHILD_MIN = 21
_PARENT_AGE_AT_FIRST_CHILD_MAX = 32
_OLDEST_CHILD_AGE_MIN = 0
_OLDEST_CHILD_AGE_MAX = 28  # an adult child still living at home, before marriage
_CHILD_SPACING_MIN_YEARS = 2
_CHILD_SPACING_MAX_YEARS = 5
_GENERATION_GAP_MIN = 24
_GENERATION_GAP_MAX = 32
_MAX_AGE = 88

_RETIREMENT_AGE = 60
_HOMEMAKER_PROBABILITY = 0.5
_NIGHT_SHIFT_PROBABILITY = 0.08
_HYBRID_WORKER_PROBABILITY = 0.4
_HYBRID_WFH_DAY_PROBABILITY = 0.5
_WEEKEND_OUTING_PROBABILITY = 0.35
_TUITION_DAY_PROBABILITY = 0.8  # on a weekday, for a child who goes to tuition

# How much earlier or later this household's whole day runs than the
# typical one — different jobs, commutes and habits.
_SCHEDULE_OFFSET_HOURS = 0.75


class Role(StrEnum):
    PARENT = "parent"
    CHILD = "child"
    GRANDPARENT = "grandparent"
    GUEST = "guest"


class Occupation(StrEnum):
    OFFICE = "office"
    HYBRID = "hybrid"
    NIGHT_SHIFT = "night-shift"
    HOMEMAKER = "homemaker"
    RETIRED = "retired"
    COLLEGE = "college"
    SCHOOL = "school"
    PRESCHOOL = "preschool"
    INFANT = "infant"
    VISITING = "visiting"


WORKING = (Occupation.OFFICE, Occupation.HYBRID, Occupation.NIGHT_SHIFT)
HOME_DURING_DAY = (Occupation.HOMEMAKER, Occupation.RETIRED, Occupation.VISITING)


class Status(IntEnum):
    ASLEEP = 0
    HOME = 1
    AWAY = 2


@dataclass(frozen=True, slots=True)
class FamilyMember:
    index: int
    age: int
    role: Role
    # Their own bedroom (1-based), or None for a young child who sleeps in
    # the parents' room (or a guest with no free bedroom, on the hall sofa).
    room: int | None
    occupation: Occupation

    @property
    def sleeping_room(self) -> int | None:
        if self.room is not None:
            return self.room
        return None if self.role is Role.GUEST else PARENTS_ROOM


@dataclass(frozen=True, slots=True)
class Habits:
    """Which appliances a household owns and how it uses them — fixed for
    the life of the household, like its family. Ownership rates follow what
    a well-off Chennai 4-bedroom home plausibly has in 2026."""

    electric_rice_cooker: bool
    irons_at_home: bool  # otherwise sends clothes to the neighbourhood istriwala
    solar_water_heater: bool  # if so, the geyser never runs
    microwave: bool
    kitchen_chimney: bool
    electric_kettle: bool
    induction_cooktop: bool  # alongside LPG, for quick cooking
    ro_purifier: bool
    mosquito_vaporiser: bool
    bedroom_tv: bool
    gaming_pc: bool  # for a teenager or college student, if there is one
    ev_scooter: bool
    ev_car: bool
    evening_tuition: bool  # school-age children go to tuition after school
    wet_grinder_days_per_week: float
    # Personal heat tolerance: shifts the temperature at which this
    # household reaches for the AC remote, deg C (negative = feels the heat sooner).
    ac_comfort_offset_c: float


@dataclass(frozen=True, slots=True)
class Family:
    household_id: str
    members: tuple[FamilyMember, ...]
    occupied_bedrooms: int
    schedule_offset_hours: float
    habits: Habits

    def count(self, *occupations: Occupation) -> int:
        return sum(1 for m in self.members if m.occupation in occupations)


@dataclass(frozen=True, slots=True)
class HouseholdOverride:
    """A "what if" for one household on one simulated day."""

    guests: int = 0
    # The whole family out from `away_from` to `away_to` (IST hours; the end
    # may be past midnight, e.g. 18.0 -> 23.5, or 20.0 -> 26.0).
    away_from: float | None = None
    away_to: float | None = None
    work_from_home: bool = False
    # Fraction of solar output lost to dust or shade, 0-1.
    panel_derate: float = 0.0

    def away_at(self, hour: float) -> bool:
        """Is the family out at `hour` of the override's own day (0-24)?"""
        if self.away_from is None or self.away_to is None:
            return False
        return self.away_from <= hour < min(self.away_to, 24.0)

    def next_day(self) -> HouseholdOverride:
        """The same what-if carried into the following date: guests stay and
        dusty panels stay dusty; a WFH day doesn't repeat; an outing that ran
        past midnight continues until it ends."""
        runs_over = self.away_to is not None and self.away_to > 24.0
        return HouseholdOverride(
            guests=self.guests,
            away_from=0.0 if runs_over else None,
            away_to=(self.away_to - 24.0) if runs_over and self.away_to is not None else None,
            panel_derate=self.panel_derate,
        )

    def history(self) -> HouseholdOverride:
        """What of the what-if already applied on earlier days: only the
        panels' condition (dust doesn't arrive overnight)."""
        return HouseholdOverride(panel_derate=self.panel_derate)


NO_OVERRIDE = HouseholdOverride()


@dataclass(frozen=True, slots=True)
class MemberDay:
    """One member's day, in IST decimal hours. Sleep runs from `sleep_h` to
    `wake_h` and may wrap past midnight (22.5 -> 6.0) or not (4.5 -> 12.5
    for a night-shift worker); away intervals may also run past 24."""

    wake_h: float
    sleep_h: float
    away: tuple[tuple[float, float], ...]


def _rng_for(household_id: str, seed: int, label: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{household_id}:{label}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))  # noqa: S311 -- deterministic synthetic data


def _working_occupation(rng: random.Random) -> Occupation:
    roll = rng.random()
    if roll < _NIGHT_SHIFT_PROBABILITY:
        return Occupation.NIGHT_SHIFT
    if roll < _NIGHT_SHIFT_PROBABILITY + _HYBRID_WORKER_PROBABILITY:
        return Occupation.HYBRID
    return Occupation.OFFICE


def _child_occupation(age: int, rng: random.Random) -> Occupation:
    if age < 3:
        return Occupation.INFANT
    if age < 6:
        return Occupation.PRESCHOOL
    if age < 18:
        return Occupation.SCHOOL
    if age < 23:
        return Occupation.COLLEGE
    return _working_occupation(rng)


def generate_family(household_id: str, member_count: int, seed: int) -> Family:
    """This household's family. Deterministic and stable for its lifetime."""
    rng = _rng_for(household_id, seed, "family")

    grandparents = 0
    if member_count >= 6:
        grandparents = 2 if rng.random() < 0.7 else 1
    elif member_count == 5 and rng.random() < 0.6:
        grandparents = 1
    num_children = max(0, member_count - 2 - grandparents)

    if num_children == 0:
        parent_age = rng.randint(_CHILDLESS_COUPLE_MIN_AGE, _CHILDLESS_COUPLE_MAX_AGE)
        oldest_child_age = 0
    else:
        oldest_child_age = rng.randint(_OLDEST_CHILD_AGE_MIN, _OLDEST_CHILD_AGE_MAX)
        parent_age = oldest_child_age + rng.randint(
            _PARENT_AGE_AT_FIRST_CHILD_MIN, _PARENT_AGE_AT_FIRST_CHILD_MAX
        )

    def parent_occupation(age: int, *, may_be_homemaker: bool) -> Occupation:
        if age >= _RETIREMENT_AGE:
            return Occupation.RETIRED
        if may_be_homemaker and rng.random() < _HOMEMAKER_PROBABILITY:
            return Occupation.HOMEMAKER
        return _working_occupation(rng)

    members: list[FamilyMember] = [
        FamilyMember(
            index=0,
            age=parent_age,
            role=Role.PARENT,
            room=PARENTS_ROOM,
            occupation=parent_occupation(parent_age, may_be_homemaker=False),
        )
    ]
    if member_count >= 2:
        spouse_age = max(18, parent_age + rng.randint(-_COUPLE_AGE_SPREAD, _COUPLE_AGE_SPREAD))
        members.append(
            FamilyMember(
                index=1,
                age=spouse_age,
                role=Role.PARENT,
                room=PARENTS_ROOM,
                occupation=parent_occupation(spouse_age, may_be_homemaker=True),
            )
        )

    next_free_room = 2
    if grandparents:
        grandparent_room = next_free_room
        next_free_room += 1
        first_age = min(
            _MAX_AGE, parent_age + rng.randint(_GENERATION_GAP_MIN, _GENERATION_GAP_MAX)
        )
        for g in range(grandparents):
            age = first_age
            if g > 0:
                age = max(_RETIREMENT_AGE, min(_MAX_AGE, first_age + rng.randint(-5, 3)))
            members.append(
                FamilyMember(
                    index=len(members),
                    age=age,
                    role=Role.GRANDPARENT,
                    room=grandparent_room,
                    occupation=Occupation.RETIRED,
                )
            )

    child_age = oldest_child_age
    last_child_room = PARENTS_ROOM
    for position in range(num_children):
        if position > 0:
            spacing = rng.randint(_CHILD_SPACING_MIN_YEARS, _CHILD_SPACING_MAX_YEARS)
            child_age = max(0, child_age - spacing)
        room: int | None
        if child_age < _OWN_ROOM_MIN_AGE:
            room = None
        elif next_free_room <= BEDROOMS:
            room = next_free_room
            last_child_room = room
            next_free_room += 1
        else:
            # Every bedroom is taken; share with the sibling who most
            # recently got one rather than crowd the parents.
            room = last_child_room
        members.append(
            FamilyMember(
                index=len(members),
                age=child_age,
                role=Role.CHILD,
                room=room,
                occupation=_child_occupation(child_age, rng),
            )
        )

    habits_rng = _rng_for(household_id, seed, "habits")
    habits = Habits(
        electric_rice_cooker=habits_rng.random() < 0.5,
        irons_at_home=habits_rng.random() < 0.5,
        solar_water_heater=habits_rng.random() < 0.3,
        microwave=habits_rng.random() < 0.45,
        kitchen_chimney=habits_rng.random() < 0.6,
        electric_kettle=habits_rng.random() < 0.6,
        induction_cooktop=habits_rng.random() < 0.35,
        ro_purifier=habits_rng.random() < 0.9,
        mosquito_vaporiser=habits_rng.random() < 0.8,
        bedroom_tv=habits_rng.random() < 0.4,
        gaming_pc=habits_rng.random() < 0.5,
        ev_scooter=habits_rng.random() < 0.35,
        ev_car=habits_rng.random() < 0.12,
        evening_tuition=habits_rng.random() < 0.6,
        wet_grinder_days_per_week=habits_rng.uniform(2.0, 4.0),
        ac_comfort_offset_c=habits_rng.gauss(0.0, 0.8),
    )
    schedule_offset = _rng_for(household_id, seed, "schedule").uniform(
        -_SCHEDULE_OFFSET_HOURS, _SCHEDULE_OFFSET_HOURS
    )
    return Family(
        household_id=household_id,
        members=tuple(members),
        occupied_bedrooms=_occupied(members),
        schedule_offset_hours=schedule_offset,
        habits=habits,
    )


def _occupied(members: list[FamilyMember] | tuple[FamilyMember, ...]) -> int:
    return len({m.sleeping_room for m in members if m.sleeping_room is not None})


def with_guests(family: Family, guests: int) -> Family:
    """The family plus `guests` visiting adults, put up in free bedrooms
    (switching on those rooms' ACs and fans) or, once those run out, the hall."""
    if guests <= 0:
        return family
    used = {m.sleeping_room for m in family.members}
    free = [room for room in range(1, BEDROOMS + 1) if room not in used]
    members = list(family.members)
    for g in range(guests):
        # Guests come in pairs to a room where they can.
        room = free[g // 2] if g // 2 < len(free) else None
        members.append(
            FamilyMember(
                index=len(members),
                age=45,
                role=Role.GUEST,
                room=room,
                occupation=Occupation.VISITING,
            )
        )
    return replace(family, members=tuple(members), occupied_bedrooms=_occupied(members))


def _has_daytime_caregiver(family: Family) -> bool:
    return family.count(*HOME_DURING_DAY) > 0


def member_days(
    family: Family, day: date, seed: int, override: HouseholdOverride = NO_OVERRIDE
) -> tuple[MemberDay, ...]:
    """Every member's wake/sleep times and time away from home on `day`."""
    rng = _rng_for(family.household_id, seed, f"routine:{day.isoformat()}")
    weekend = day.weekday() >= 5
    offset = family.schedule_offset_hours

    outing: tuple[float, float] | None = None
    if weekend and rng.random() < _WEEKEND_OUTING_PROBABILITY:
        start = rng.uniform(16.5, 17.5)
        outing = (start, start + rng.uniform(2.5, 3.5))
    family_away: tuple[float, float] | None = None
    if override.away_from is not None and override.away_to is not None:
        # This date's share of the outing; any part past midnight belongs to
        # the next date (see HouseholdOverride.next_day).
        family_away = (override.away_from, min(override.away_to, 24.0))

    days: list[MemberDay] = []
    for member in family.members:
        away: list[tuple[float, float]] = []
        occupation = member.occupation
        at_home_today = weekend or override.work_from_home

        if occupation in (Occupation.OFFICE, Occupation.HYBRID):
            wake, sleep = rng.uniform(5.75, 6.5), rng.uniform(22.5, 23.5)
            wfh = occupation is Occupation.HYBRID and rng.random() < _HYBRID_WFH_DAY_PROBABILITY
            if not at_home_today and not wfh:
                away.append((rng.uniform(8.25, 9.25) + offset, rng.uniform(18.5, 19.75) + offset))
        elif occupation is Occupation.NIGHT_SHIFT:
            # Out for the US-facing shift, home before dawn, asleep till noon.
            wake, sleep = rng.uniform(12.0, 13.0), rng.uniform(4.25, 5.0)
            if not at_home_today:
                away.append((rng.uniform(18.25, 18.75), rng.uniform(27.25, 27.75)))
        elif occupation is Occupation.HOMEMAKER:
            wake, sleep = rng.uniform(5.25, 6.0), rng.uniform(22.25, 23.0)
            if not weekend and rng.random() < 0.4:
                start = rng.uniform(10.0, 11.0)
                away.append((start, start + rng.uniform(0.75, 1.25)))
            if rng.random() < 0.3:
                start = rng.uniform(17.5, 18.25)
                away.append((start, start + rng.uniform(0.75, 1.25)))  # temple/market
        elif occupation is Occupation.RETIRED:
            wake, sleep = rng.uniform(5.0, 5.75), rng.uniform(21.5, 22.25)
            if rng.random() < 0.5:
                start = wake + rng.uniform(0.5, 1.0)
                away.append((start, start + 0.75))  # morning walk
            if rng.random() < 0.35:
                start = rng.uniform(17.25, 18.0)
                away.append((start, start + rng.uniform(0.75, 1.25)))
        elif occupation is Occupation.VISITING:
            wake, sleep = rng.uniform(6.0, 7.0), rng.uniform(22.0, 23.0)
            if rng.random() < 0.5:
                start = rng.uniform(10.0, 16.0)
                away.append((start, start + rng.uniform(2.0, 4.0)))  # out seeing the city
        elif occupation is Occupation.COLLEGE:
            wake, sleep = rng.uniform(6.25, 7.0), rng.uniform(23.0, 24.5)
            if not weekend:
                away.append((rng.uniform(7.5, 8.25), rng.uniform(16.5, 17.5)))
            if rng.random() < 0.3:
                start = rng.uniform(18.0, 19.5)
                away.append((start, start + rng.uniform(1.5, 2.5)))  # evening out
        elif occupation is Occupation.SCHOOL:
            wake, sleep = rng.uniform(6.0, 6.5), rng.uniform(21.5, 22.25)
            if not weekend:
                away.append((rng.uniform(7.25, 7.75), rng.uniform(15.75, 16.5)))
                tuition = family.habits.evening_tuition and member.age >= 10
                if tuition and rng.random() < _TUITION_DAY_PROBABILITY:
                    start = rng.uniform(17.25, 18.0)
                    away.append((start, start + rng.uniform(1.0, 1.5)))
        elif occupation is Occupation.PRESCHOOL:
            wake, sleep = rng.uniform(6.5, 7.0), rng.uniform(21.0, 21.5)
            if not weekend:
                away.append((8.5, 12.5))
        else:  # INFANT
            wake, sleep = rng.uniform(6.5, 7.5), rng.uniform(20.5, 21.5)
            if not weekend and not _has_daytime_caregiver(family):
                away.append((8.25 + offset, 18.75 + offset))  # daycare

        if weekend and occupation is not Occupation.NIGHT_SHIFT:
            wake += 1.0
            sleep += 0.25
        if outing is not None:
            away.append(outing)
        if family_away is not None:
            away.append(family_away)
        days.append(MemberDay(wake_h=wake + offset, sleep_h=sleep + offset, away=tuple(away)))
    return tuple(days)


def _within(hour: float, start: float, end: float) -> bool:
    """Is `hour` (0-24) inside [start, end), where the interval may run past
    midnight (end > 24)?"""
    return start <= hour < end or start <= hour + 24.0 < end


def status_at(member_day: MemberDay, hour: float) -> Status:
    """Away, asleep or home at `hour` (0-24). Being out wins — a family out
    at a wedding isn't asleep in its bedrooms. The early-morning hours of an
    overnight sleep belong to the previous night, assumed to have started at
    the same bedtime as tonight's."""
    if any(_within(hour, start, end) for start, end in member_day.away):
        return Status.AWAY
    sleep_start = member_day.sleep_h % 24.0
    wake = member_day.wake_h % 24.0
    if sleep_start <= wake:
        asleep = sleep_start <= hour < wake
    else:
        asleep = hour >= sleep_start or hour < wake
    return Status.ASLEEP if asleep else Status.HOME
