"""Feeder topology construction and traversal helpers."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.domain.grid.network import SUBSTATION_BUS, default_feeder

pytestmark = pytest.mark.unit


def test_default_feeder_includes_every_household() -> None:
    houses = [f"h{i}" for i in range(1, 11)]
    network = default_feeder(houses)

    assert network.household_buses() == frozenset(houses)


def test_default_feeder_splits_into_three_laterals() -> None:
    houses = [f"h{i}" for i in range(1, 11)]
    network = default_feeder(houses)

    lateral_roots = network.children_of(SUBSTATION_BUS)
    assert len(lateral_roots) == 3


def test_every_non_substation_bus_has_exactly_one_parent_line() -> None:
    """A well-formed tree: this is what makes `subtree()` and
    `path_from_substation()` unambiguous."""
    network = default_feeder([f"h{i}" for i in range(1, 11)])

    for bus in network.household_buses():
        # line_to() itself raises if there isn't exactly one — this just
        # proves it never raises for a real bus in the network.
        network.line_to(bus)


def test_subtree_includes_the_bus_itself_and_everything_downstream() -> None:
    network = default_feeder(["h1", "h2", "h3"])  # one house per lateral
    leaf = network.children_of(SUBSTATION_BUS)[0]

    assert network.subtree(leaf) == {leaf}


def test_subtree_of_the_substation_is_the_whole_network() -> None:
    houses = [f"h{i}" for i in range(1, 11)]
    network = default_feeder(houses)

    assert network.subtree(SUBSTATION_BUS) == network.buses()


def test_path_from_substation_reaches_the_target_bus() -> None:
    network = default_feeder([f"h{i}" for i in range(1, 11)])
    bus = "h10"  # deepest bus on the first lateral (h1, h4, h7, h10)

    path = network.path_from_substation(bus)

    assert path[0].from_bus == SUBSTATION_BUS
    assert path[-1].to_bus == bus
    # Each line's end is the next line's start — a genuine unbroken chain.
    for earlier, later in pairwise(path):
        assert earlier.to_bus == later.from_bus


def test_empty_household_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one household"):
        default_feeder([])
