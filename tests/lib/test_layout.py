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
    end_letter,
    facing_ends,
    facing_towards,
    opposite_end,
    transit_ends,
)
from tc49.store import AssetStore
from tests.harness import ASSETS, load


@pytest.fixture
def store() -> AssetStore:
    return AssetStore(ASSETS)


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

    reversing_loops_v0 = store.get("reversing-loops-v0")
    assert isinstance(reversing_loops_v0, Layout)
    assert reversing_loops_v0.terminal_blocks == frozenset(
        {"station_a_4", "station_c_4", "station_c_5", "station_c_6", "station_c_7"}
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


def test_a_block_end_carries_the_address_of_the_signal_standing_there() -> None:
    doc = minimal_layout()
    doc["blocks"]["a"]["signals"] = {"A": "40", "B": "41"}
    assert Layout.from_document(doc).signal_at == {
        "a.A": "40",
        "a.B": "41",
    }


def test_a_block_signalling_one_end_carries_that_one() -> None:
    doc = minimal_layout()
    doc["blocks"]["a"]["signals"] = {"B": "41"}
    assert Layout.from_document(doc).signal_at == {"a.B": "41"}


def test_a_layout_nothing_signals_holds_no_signal_at_all() -> None:
    assert Layout.from_document(minimal_layout()).signal_at == {}


def test_signals_must_name_an_end_the_block_has() -> None:
    doc = minimal_layout()
    doc["blocks"]["a"]["signals"] = {"C": "42"}
    with pytest.raises(ValueError, match="block 'a': signals names 'C'"):
        Layout.from_document(doc)


def test_two_ends_may_share_one_signal_address() -> None:
    """Two signals on one address show one aspect together, the way two points
    on one address move together (ADR-0031). A wiring fact, not a fault."""
    doc = minimal_layout()
    doc["blocks"]["a"]["signals"] = {"A": "40"}
    doc["blocks"]["b"]["signals"] = {"B": "40"}
    assert Layout.from_document(doc).signal_at == {
        "a.A": "40",
        "b.B": "40",
    }


def test_an_end_is_taken_apart_into_its_block_and_its_letter() -> None:
    assert block_of("yard_w.B") == "yard_w"
    assert end_letter("yard_w.B") == "B"


def test_the_opposite_end_is_the_other_end_of_the_same_block() -> None:
    assert opposite_end("yard_w.A") == "yard_w.B"
    assert opposite_end("yard_w.B") == "yard_w.A"


def test_a_transit_names_one_end_of_each_block_it_joins() -> None:
    """Read from either side, `transit_ends` gives that side's own end first
    and the end across second — which is what lets one function serve the
    departure end the dispatcher signals, the arrival end the scheduler faces
    a train away from, and the end a binding handed a `move` finds the train
    standing at (ADR-0047)."""
    layout, _roster, _ = load("crossover-yard/meet")

    assert transit_ends(layout, "yard_w", "west_ladder.to_dn") == (
        "yard_w.B",
        "dn_w.A",
    )
    assert transit_ends(layout, "dn_w", "west_ladder.to_dn") == (
        "dn_w.A",
        "yard_w.B",
    )


def test_a_transit_the_layout_does_not_hold_joins_no_ends() -> None:
    """Names that came off the bus answer None where reaching into the layout
    would raise, because a consumer may not raise on a payload (BUS.md, rule
    4). A transit under no connection, one no connection declares, one left
    unqualified, one that crosses the block named nowhere (#276: there is no
    track from anywhere to there, so nothing to run), and a block the layout
    does not hold."""
    layout, _roster, _ = load("crossover-yard/meet")

    assert transit_ends(layout, "yard_w", "ghost.to_dn") is None
    assert transit_ends(layout, "yard_w", "west_ladder.ghost") is None
    assert transit_ends(layout, "yard_w", "to_dn") is None  # unqualified
    assert transit_ends(layout, "up_e", "west_ladder.to_dn") is None
    assert transit_ends(layout, "ghost", "west_ladder.to_dn") is None


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


def test_a_point_says_its_address_is_reported() -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["points"] = {
        "ab": [
            {"addr": "12", "position": "thrown", "reported": True},
            {"addr": "13", "position": "closed"},
        ]
    }
    layout = Layout.from_document(doc)
    assert layout.connections["j"].points == {
        "ab": (Point("12", "thrown", reported=True), Point("13", "closed"))
    }
    assert not layout.connections["j"].points["ab"][1].reported


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_reported_is_written_true_or_left_out(value: Any) -> None:
    doc = minimal_layout()
    doc["connections"]["j"]["points"] = {
        "ab": [{"addr": "12", "position": "thrown", "reported": value}]
    }
    with pytest.raises(ValueError, match="reported"):
        Layout.from_document(doc)
