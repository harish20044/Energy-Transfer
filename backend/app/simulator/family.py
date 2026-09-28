"""Realistic household composition and room occupancy.

Every household in this simulation shares the same physical design — the
common case for a residential development where every unit was built to the
same plan: 4 bedrooms, one hall+kitchen, 5 washrooms, and one AC per bedroom
(4 total; the hall and kitchen have none, the typical split for an Indian
home). What differs between households is only who lives in them and how
those bedrooms actually get used — which is exactly what should drive how
much electricity a household draws, not a flat number scaled by headcount.

Family composition is generated once per household, deterministically from
its id and member count — a family's structure doesn't change tick to tick
the way its consumption does. Occupancy (who's actually home, and in which
room, at a given hour) does change, and that occupancy is what drives AC
draw in `app.simulator.profiles.consumption_kw` — a 22-year-old home in
their own room runs that room's AC; a 2-year-old is wherever their parents
are, with no room or AC of their own.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from enum import StrEnum

BEDROOMS = 4
WASHROOMS = 5
HALLS = 1
AC_UNITS = BEDROOMS  # one per bedroom; the hall/kitchen have none

_CHILDLESS_COUPLE_MIN_AGE = 25
_CHILDLESS_COUPLE_MAX_AGE = 65
_COUPLE_AGE_SPREAD = 5
_OWN_ROOM_MIN_AGE = 10  # younger than this, a child stays with the parents

# A parent's age is derived from *when they actually had each child*, not
# sampled independently of it — otherwise nothing stops a 52-year-old from
# getting a newborn. NFHS (India's National Family Health Survey) puts the
# average maternal age at first birth in the low-to-mid 20s; this samples a
# plausible range around that rather than a single fixed number.
_PARENT_AGE_AT_FIRST_CHILD_MIN = 20
_PARENT_AGE_AT_FIRST_CHILD_MAX = 30
_OLDEST_CHILD_AGE_MIN = 0
_OLDEST_CHILD_AGE_MAX = 28  # an adult child still living at home, before marriage
_CHILD_SPACING_MIN_YEARS = 2
_CHILD_SPACING_MAX_YEARS = 5

_ADULT_WORKING_MAX_AGE = 60
_SCHOOL_AGE_MIN = 5
_SCHOOL_AGE_MAX = 17
_WEEKDAY_WORK_START = 9.0
_WEEKDAY_WORK_END = 18.0
_WEEKDAY_SCHOOL_START = 8.0
_WEEKDAY_SCHOOL_END = 15.0

# A standard 1.5-ton split AC's real average draw, and the fraction of that
# it actually pulls once the thermostat starts cycling the compressor on and
# off rather than running flat out.
AC_RATED_KW = 1.45
AC_CYCLING_FACTOR = 0.7
BASE_LOAD_KW = 0.25  # always-on house load: fridge, router, standby lighting
PER_PRESENT_MEMBER_MISC_KW = 0.08  # phone charging, personal lighting, etc.


class Role(StrEnum):
    PARENT = "parent"
    CHILD = "child"


@dataclass(frozen=True, slots=True)
class FamilyMember:
    index: int
    age: int
    role: Role
    room: int | None  # 1-based bedroom number; None means "with the parents"


@dataclass(frozen=True, slots=True)
class Family:
    household_id: str
    members: tuple[FamilyMember, ...]
    occupied_bedrooms: int


@dataclass(frozen=True, slots=True)
class RoomStatus:
    room: int
    occupied: bool
    ac_intensity: float  # 0.0-1.0 duty cycle right now; 0.0 whenever unoccupied


@dataclass(frozen=True, slots=True)
class OccupancySnapshot:
    home_now: dict[int, bool]  # member index -> home right now
    rooms: tuple[RoomStatus, ...]  # every bedroom, 1..BEDROOMS, in order
    present_count: int


def _rng_for(household_id: str, seed: int, label: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{household_id}:{label}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))  # noqa: S311 -- deterministic synthetic data


def generate_family(household_id: str, member_count: int, seed: int) -> Family:
    """This household's family: always a couple, plus `member_count - 2`
    children with ages generated from an actual birth timeline — the
    parents' age is *derived from* how old their children are, not sampled
    independently of it, so a household never ends up with, say, a
    52-year-old parent and a newborn. Age, not just headcount, is what
    decides whether a child has its own room and its own AC draw.
    Deterministic and stable for the life of the household.
    """
    rng = _rng_for(household_id, seed, "family")
    members: list[FamilyMember] = []
    num_children = max(0, member_count - 2)

    if num_children == 0:
        # No children to derive an age from — sample the couple directly.
        age1 = rng.randint(_CHILDLESS_COUPLE_MIN_AGE, _CHILDLESS_COUPLE_MAX_AGE)
    else:
        # Work out the family's birth timeline oldest-child-first, then set
        # the parents' age from how old that oldest child makes them.
        oldest_child_age = rng.randint(_OLDEST_CHILD_AGE_MIN, _OLDEST_CHILD_AGE_MAX)
        age_at_first_child = rng.randint(
            _PARENT_AGE_AT_FIRST_CHILD_MIN, _PARENT_AGE_AT_FIRST_CHILD_MAX
        )
        age1 = age_at_first_child + oldest_child_age

    if member_count <= 1:
        # No seeded household is actually this small, but a lone occupant is
        # handled honestly rather than assumed impossible.
        members.append(FamilyMember(index=0, age=age1, role=Role.PARENT, room=1))
    else:
        age2 = max(18, age1 + rng.randint(-_COUPLE_AGE_SPREAD, _COUPLE_AGE_SPREAD))
        members.append(FamilyMember(index=0, age=age1, role=Role.PARENT, room=1))
        members.append(FamilyMember(index=1, age=age2, role=Role.PARENT, room=1))

    child_age = oldest_child_age if num_children > 0 else 0
    next_free_room = 2
    last_child_room = 1
    for position, index in enumerate(range(2, member_count)):
        if position > 0:
            spacing = rng.randint(_CHILD_SPACING_MIN_YEARS, _CHILD_SPACING_MAX_YEARS)
            child_age = max(0, child_age - spacing)
        room: int | None
        if child_age < _OWN_ROOM_MIN_AGE:
            room = None  # young enough to stay with the parents
        elif next_free_room <= BEDROOMS:
            room = next_free_room
            last_child_room = room
            next_free_room += 1
        else:
            # Every bedroom is already spoken for; share with whichever
            # child most recently got one, rather than crowd the parents.
            room = last_child_room
        members.append(FamilyMember(index=index, age=child_age, role=Role.CHILD, room=room))

    occupied = len({member.room for member in members if member.room is not None} | {1})
    return Family(household_id=household_id, members=tuple(members), occupied_bedrooms=occupied)


def _is_away(member: FamilyMember, hour: float, is_weekend: bool) -> bool:
    """True if this member is out of the house at this hour. Toddlers and
    anyone past typical working age are treated as generally home."""
    if is_weekend:
        return False
    if member.role is Role.PARENT and member.age < _ADULT_WORKING_MAX_AGE:
        return _WEEKDAY_WORK_START <= hour < _WEEKDAY_WORK_END
    if member.role is Role.CHILD and _SCHOOL_AGE_MIN <= member.age <= _SCHOOL_AGE_MAX:
        return _WEEKDAY_SCHOOL_START <= hour < _WEEKDAY_SCHOOL_END
    return False


def _circular_bell(hour: float, *, center: float, width_hours: float, amplitude: float) -> float:
    """Like a normal Gaussian bell, but wraps around midnight — needed for a
    peak that spans, say, 22:00 through 04:00 without two separate humps."""
    raw_diff = abs(hour - center) % 24
    circular_diff = min(raw_diff, 24 - raw_diff)
    return amplitude * math.exp(-(circular_diff**2) / (2 * width_hours**2))


def _ac_duty_cycle(hour: float) -> float:
    """How hard an occupied room's AC runs at this hour, before any
    household-specific occupancy or scenario intensity is applied — heaviest
    overnight for sleeping, a lighter secondary bump for afternoon heat."""
    night = _circular_bell(hour, center=1.0, width_hours=4.0, amplitude=0.9)
    afternoon = _circular_bell(hour, center=15.0, width_hours=2.5, amplitude=0.5)
    return min(1.0, night + afternoon)


def snapshot_occupancy(
    family: Family, hour: float, is_weekend: bool, demand_factor: float
) -> OccupancySnapshot:
    """Who's home and which bedrooms are in use right now, and how hard each
    occupied room's AC is running — the single source both the consumption
    total and the household's own live status view are built from."""
    home_now: dict[int, bool] = {}
    occupied_rooms: set[int] = set()
    present_count = 0

    for member in family.members:
        home = not _is_away(member, hour, is_weekend)
        home_now[member.index] = home
        if home:
            present_count += 1
            occupied_rooms.add(member.room if member.room is not None else 1)

    duty = min(1.0, _ac_duty_cycle(hour) * demand_factor)
    rooms = tuple(
        RoomStatus(
            room=room,
            occupied=room in occupied_rooms,
            ac_intensity=duty if room in occupied_rooms else 0.0,
        )
        for room in range(1, BEDROOMS + 1)
    )
    return OccupancySnapshot(home_now=home_now, rooms=rooms, present_count=present_count)
