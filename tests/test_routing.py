"""Direct unit tests for candidates(): DISPATCH.md's route ordering."""

from pathlib import Path

import pytest

from tc49.layout import Layout
from tc49.routing import Route, candidates
from tc49.store import AssetStore

ROOT = Path(__file__).parent.parent


@pytest.fixture
def crossover() -> Layout:
    layout = AssetStore(ROOT).get("crossover-yard")
    assert isinstance(layout, Layout)
    return layout


def test_routes_ordered_by_transit_count_then_block_ids(crossover: Layout) -> None:
    # yard_w.B to yard_e.A: four 3-transit routes, ordered by block-id sequence.
    routes = candidates(crossover, "yard_w", "yard_w.B", ("yard_e.A",), 600, k=4)
    assert [r.blocks for r in routes] == [
        ("yard_w", "dn_w", "dn_e", "yard_e"),
        ("yard_w", "dn_w", "up_e", "yard_e"),
        ("yard_w", "up_w", "dn_e", "yard_e"),
        ("yard_w", "up_w", "up_e", "yard_e"),
    ]
    assert routes[0].transits == (
        "west_ladder.to_dn",
        "crossover.dn_straight",
        "east_ladder.from_dn",
    )


def test_candidates_merge_every_arrival_end(crossover: Layout) -> None:
    # From up_e.A, entering yard_w through B: crossover to dn or straight to up.
    routes = candidates(crossover, "up_e", "up_e.A", ("yard_w.B",), 600, k=4)
    assert [r.blocks for r in routes] == [
        ("up_e", "dn_w", "yard_w"),
        ("up_e", "up_w", "yard_w"),
    ]


def test_k_caps_the_merged_list(crossover: Layout) -> None:
    routes = candidates(crossover, "yard_w", "yard_w.B", ("yard_e.A",), 600, k=1)
    assert len(routes) == 1


def test_fit_filters_whole_routes(crossover: Layout) -> None:
    # A train longer than the up/dn blocks (3200) can never leave the yard.
    routes = candidates(crossover, "yard_w", "yard_w.B", ("yard_e.A",), 5000, k=4)
    assert routes == []


def test_departure_end_fixes_the_first_transit(crossover: Layout) -> None:
    # Departing yard_w through A (the dead end): no transits, no routes.
    routes = candidates(crossover, "yard_w", "yard_w.A", ("yard_e.A",), 600, k=4)
    assert routes == []


def test_congested_blocks_demote_tied_candidates(crossover: Layout) -> None:
    # The same four tied routes as above, with the down main congested: the
    # penalty counts congested blocks beyond the origin, so the clear route
    # leads, single-block routes follow in block-id order, and the fully
    # congested route comes last.
    routes = candidates(
        crossover,
        "yard_w",
        "yard_w.B",
        ("yard_e.A",),
        600,
        k=4,
        congested=frozenset({"dn_w", "dn_e"}),
    )
    assert [r.blocks for r in routes] == [
        ("yard_w", "up_w", "up_e", "yard_e"),
        ("yard_w", "dn_w", "up_e", "yard_e"),
        ("yard_w", "up_w", "dn_e", "yard_e"),
        ("yard_w", "dn_w", "dn_e", "yard_e"),
    ]


def test_transit_count_still_dominates_congestion(crossover: Layout) -> None:
    # Congestion is a tie-break, not an additive cost: the one-transit route
    # stays first even with its arrival block congested and the two-transit
    # routes clear.
    routes = candidates(
        crossover,
        "up_w",
        "up_w.B",
        ("up_e.A", "yard_e.A"),
        600,
        k=4,
        congested=frozenset({"up_e"}),
    )
    assert routes[0].blocks == ("up_w", "up_e")


def test_routes_are_simple_paths(crossover: Layout) -> None:
    # All routes from up_w.B to up_e entering through A; none may revisit a block.
    routes = candidates(crossover, "up_w", "up_w.B", ("up_e.A",), 600, k=10)
    for route in routes:
        assert len(set(route.blocks)) == len(route.blocks)
        assert len(set(route.transits)) == len(route.transits)
    assert routes[0] == Route(("up_w", "up_e"), ("crossover.up_straight",))
