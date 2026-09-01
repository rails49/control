"""Tests at the Layout seam: model queries and load-time validation."""

from typing import Any

import pytest

from tc49.lib.layout import (
    FACINGS,
    Layout,
    Point,
    block_of,
    connected_end,
    connected_facing,
    departure_end,
    end_across,
    end_crossed,
    end_letter,
    end_on,
    facing_ends,
    facing_towards,
    opposite_end,
)
from tc49.store import AssetStore
from tests.harness import ROOT, load


@pytest.fixture
def store() -> AssetStore:
    return AssetStore(ROOT)


def minimal_layout() -> dict[str, Any]:
    return {
        "layout": "mini",
        "units": "mm",
        "blocks": {"a": {"length": 1000}, "b": {"length": 1000}},
        "connections": {"j": {"transits": {"ab": ["a.B", "b.A"]}}},
    }


def test_crossover_yard_loads_clean(store: AssetStore) -> None:
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert layout.blocks["yard_w"] == 1400
    assert set(layout.connections["crossover"].transits) == {
        "up_straight",
        "dn_straight",
        "up_to_dn",
        "dn_to_up",
    }


def test_terminal_blocks_are_derived(store: AssetStore) -> None:
    crossover = store.get("crossover-yard")
    assert isinstance(crossover, Layout)
    assert crossover.terminal_blocks == frozenset({"yard_w", "yard_e"})

    gotthard_v0 = store.get("gotthard-v0")
    assert isinstance(gotthard_v0, Layout)
    assert gotthard_v0.terminal_blocks == frozenset(
        {"airolo_4", "claro_4", "claro_5", "claro_6", "claro_7"}
    )


def test_conflicts_by_inversion(store: AssetStore) -> None:
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    # The declared concurrent pair does not conflict, either way round.
    assert not layout.conflicts("crossover.up_straight", "crossover.dn_straight")
    assert not layout.conflicts("crossover.dn_straight", "crossover.up_straight")
    # Every undeclared pair at the connection conflicts.
    assert layout.conflicts("crossover.up_straight", "crossover.up_to_dn")
    assert layout.conflicts("crossover.up_to_dn", "crossover.dn_to_up")
    # Transits are self-exclusive.
    assert layout.conflicts("crossover.up_straight", "crossover.up_straight")
    # Transits at different connections never conflict.
    assert not layout.conflicts("west_ladder.to_up", "east_ladder.from_up")


def test_mistyped_end_is_a_load_time_error_naming_the_fault() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["transits"]["ab"] = ["a.B", "bb.A"]
    with pytest.raises(ValueError, match="bb"):
        Layout.from_document(doc)


def test_end_letter_must_be_a_or_b() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["transits"]["ab"] = ["a.C", "b.A"]
    with pytest.raises(ValueError, match="a.C"):
        Layout.from_document(doc)


def test_block_end_belongs_to_at_most_one_connection() -> None:
    doc = minimal_layout()
    doc["connections"]["k"] = {"transits": {"ba": ["b.A", "a.A"]}}
    with pytest.raises(ValueError, match="b.A"):
        Layout.from_document(doc)


def test_concurrent_must_name_declared_transits() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["concurrent"] = [["ab", "nope"]]
    with pytest.raises(ValueError, match="nope"):
        Layout.from_document(doc)


def test_unknown_keys_are_rejected() -> None:
    doc = minimal_layout()
    doc["bloks"] = {}
    with pytest.raises(ValueError, match="bloks"):
        Layout.from_document(doc)


def test_a_transit_carries_the_points_its_way_needs() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["points"] = {
        "ab": [
            {"addr": "12", "position": "thrown"},
            {"addr": "13", "position": "closed"},
        ]
    }
    layout = Layout.from_document(doc)
    assert layout.connections["j"].points == {
        "ab": (Point("12", "thrown"), Point("13", "closed"))
    }


def test_a_connection_with_nothing_to_throw_has_no_points() -> None:
    layout = Layout.from_document(minimal_layout())
    assert layout.connections["j"].points == {}


def test_points_must_name_a_transit_the_connection_has() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["points"] = {"ba": [{"addr": "12", "position": "thrown"}]}
    with pytest.raises(ValueError, match="ba"):
        Layout.from_document(doc)


def test_a_position_is_one_of_the_two_a_motor_answers_to() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["points"] = {"ab": [{"addr": "12", "position": "sideways"}]}
    with pytest.raises(ValueError, match="sideways"):
        Layout.from_document(doc)


def test_an_end_is_taken_apart_into_its_block_and_its_letter() -> None:
    assert block_of("yard_w.B") == "yard_w"
    assert end_letter("yard_w.B") == "B"


def test_the_opposite_end_is_the_other_end_of_the_same_block() -> None:
    assert opposite_end("yard_w.A") == "yard_w.B"
    assert opposite_end("yard_w.B") == "yard_w.A"


def test_a_transit_names_one_end_of_each_block_it_joins() -> None:
    """Read from either side, `end_on` gives that side's own end — which is
    what lets one function serve the departure end the dispatcher signals and
    the arrival end the scheduler faces a train away from."""
    layout, _roster, _ = load("crossover-yard/meet")
    connection = next(iter(layout.connections))
    transit, (first, second) = next(
        iter(layout.connections[connection].transits.items())
    )
    transit_id = f"{connection}.{transit}"

    assert end_on(layout, block_of(first), transit_id) == first
    assert end_on(layout, block_of(second), transit_id) == second


def test_a_transit_the_layout_does_not_hold_crosses_no_end() -> None:
    """The same question asked of names that came off the bus: `end_crossed`
    answers None where `end_on` reaches straight into the layout and raises,
    because a consumer may not raise on a payload (SYSTEM.md, rule 4). A
    transit under no connection, one no connection declares, one left
    unqualified, and one that crosses the block named nowhere."""
    layout, _roster, _ = load("crossover-yard/meet")

    assert end_crossed(layout, "yard_w", "west_ladder.to_dn") == "yard_w.B"
    assert end_crossed(layout, "yard_w", "ghost.to_dn") is None
    assert end_crossed(layout, "yard_w", "west_ladder.ghost") is None
    assert end_crossed(layout, "yard_w", "to_dn") is None  # unqualified
    assert end_crossed(layout, "up_e", "west_ladder.to_dn") is None
    assert end_crossed(layout, "ghost", "west_ladder.to_dn") is None


def test_a_transit_crosses_an_end_across_from_the_block_asked_about() -> None:
    """`end_on` read from the other side, and what a binding handed a `move`
    asks: the command names the block the train is entering, and the end
    across the transit from there is the one it must be standing at
    (ADR-0047).

    A transit the layout does not hold answers None, where reaching into the
    layout with a name off the bus raises. A transit the layout does hold
    that touches neither end of the block asked about answers None too
    (#276): it crosses no track from anywhere to there, so there is no near
    end for a train to be standing at and nothing to run.

    Read across a transit that does reach the block, both directions still
    answer the end on the other side."""
    layout, _roster, _ = load("crossover-yard/meet")

    assert end_across(layout, "dn_w", "west_ladder.to_dn") == "yard_w.B"
    assert end_across(layout, "yard_w", "west_ladder.to_dn") == "dn_w.A"
    assert end_across(layout, "dn_w", "ghost.to_dn") is None
    assert end_across(layout, "dn_w", "west_ladder.ghost") is None
    assert end_across(layout, "dn_w", "to_dn") is None  # unqualified
    assert end_across(layout, "up_e", "west_ladder.to_dn") is None
    assert end_across(layout, "ghost", "west_ladder.to_dn") is None


def test_a_block_with_both_ends_connected_answers_the_candidate(
    store: AssetStore,
) -> None:
    """Where a connection holds the candidate the candidate stands: the
    question only has a second answer on a terminal block (#145)."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert connected_end(layout, "dn_w.A") == "dn_w.A"
    assert connected_end(layout, "dn_w.B") == "dn_w.B"
    assert connected_end(layout, "yard_w.B") == "yard_w.B"


def test_a_terminal_blocks_wall_is_answered_with_its_connected_end(
    store: AssetStore,
) -> None:
    """A terminal block has exactly one connected end, so a candidate naming
    the wall is answered with that one — never with a second wall."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert connected_end(layout, "yard_w.A") == "yard_w.B"
    assert connected_end(layout, "yard_e.B") == "yard_e.A"


def test_a_departure_end_is_the_far_side_of_the_end_entered_through(
    store: AssetStore,
) -> None:
    """Routes are strict pass-throughs: a train leaves through the end of its
    block opposite the one it came in by."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert departure_end(layout, "dn_w.A") == "dn_w.B"
    assert departure_end(layout, "dn_w.B") == "dn_w.A"


def test_a_departure_end_in_a_terminal_block_is_its_one_connected_end(
    store: AssetStore,
) -> None:
    """The far side of the end a train entered a stub through is the wall, so
    the pass-through rule alone would send it nowhere; the one end a stub has
    is the one it can leave by, whichever way it came in (#145)."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert departure_end(layout, "yard_w.B") == "yard_w.B"
    assert departure_end(layout, "yard_e.A") == "yard_e.A"


def test_a_facing_runs_between_the_two_ends_of_its_block() -> None:
    """The value read apart: a train facing 'A-to-B' stands with its tail at
    A and its nose at B, which is the end it would depart through (#241)."""
    assert facing_ends("dn_w.A-to-B") == ("dn_w.A", "dn_w.B")
    assert facing_ends("dn_w.B-to-A") == ("dn_w.B", "dn_w.A")
    assert FACINGS == ("A-to-B", "B-to-A")


def test_a_facing_is_written_from_the_end_a_train_would_depart_through() -> None:
    """The other direction of the same reading, which is the one every site
    that settles a facing takes: the layout answers an end."""
    assert facing_towards("dn_w.B") == "dn_w.A-to-B"
    assert facing_towards("dn_w.A") == "dn_w.B-to-A"


def test_a_departure_end_reads_a_facing_as_the_end_it_names(
    store: AssetStore,
) -> None:
    """A train that came in at A and a train facing A-to-B lie the same way,
    so the rule is one rule and answers the same end for either spelling
    (#241)."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert departure_end(layout, "dn_w.A-to-B") == departure_end(layout, "dn_w.A")
    assert departure_end(layout, "dn_w.B-to-A") == departure_end(layout, "dn_w.B")
    assert departure_end(layout, "dn_w.A-to-B") == "dn_w.B"


def test_a_facing_in_a_terminal_block_is_turned_off_the_wall(
    store: AssetStore,
) -> None:
    """`connected_end` asked of a facing: a stub has one end a train can
    depart through, so a candidate pointing at the buffer is turned around
    rather than kept (#145)."""
    layout = store.get("crossover-yard")
    assert isinstance(layout, Layout)
    assert connected_facing(layout, "yard_w.B-to-A") == "yard_w.A-to-B"
    assert connected_facing(layout, "yard_e.A-to-B") == "yard_e.B-to-A"
    assert connected_facing(layout, "dn_w.A-to-B") == "dn_w.A-to-B"
