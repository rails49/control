"""The lock table, the questions asked of it and the transitions that change it
(#1315).

The transitions are tested here by building a table by hand, applying one
event and asserting on the table and the effects returned. The railroad is
`crossover-yard/meet`: `t` is sent from `yard_w` to `yard_e` over `dn_w` and
`dn_e`.
"""

import ast
from dataclasses import replace
from pathlib import Path

import tc49.dispatcher.table
from tc49.dispatcher.routing import candidates
from tc49.dispatcher.table import (
    Active,
    Disputed,
    Following,
    HeadIn,
    Move,
    MoveEnded,
    Opened,
    Placed,
    Released,
    Removed,
    Route,
    Table,
    broken,
    not_reporting,
    opening,
    placing,
    reading,
    releasing,
    removing,
    retiring,
)
from tests.harness import load
from tests.system.test_app_boundaries import tc49_imports

T1 = "west_ladder.to_dn"
T2 = "crossover.dn_straight"
T3 = "east_ladder.from_dn"


def test_the_table_imports_only_lib() -> None:
    """It holds the rules, and nothing of the dispatcher that does bus work,
    chooses routes, locks or checks safety."""
    source = Path(tc49.dispatcher.table.__file__).read_text()
    assert {
        name
        for name in tc49_imports(ast.parse(source))
        if not name.startswith("tc49.lib")
    } == set()


def a_route() -> tuple[Table, Route]:
    """An empty table and `yard_w` to `yard_e` by the down line."""
    layout, _roster, _ = load("crossover-yard/meet")
    route = candidates(
        layout, "yard_w", "yard_w.B", ("yard_e.A",), 500, 4, frozenset()
    )[0]
    assert route.blocks == ("yard_w", "dn_w", "dn_e", "yard_e")
    assert route.transits == (T1, T2, T3)
    return Table(layout, {}, {}, {}), route


def granted() -> Table:
    """`t` granted its first move, out of `yard_w` by `yard_w.B` over T1 into
    `dn_w` by `dn_w.A`, with `dn_e` and T2 held ahead. Its tail is over
    `yard_w.B`, which reads occupied."""
    table, route = a_route()
    move = Move("yard_w", T1, "dn_w", [T1, "dn_w"], [T2, "dn_e"])
    table.locks.update({"yard_w": "t", T1: "t", "dn_w": "t", T2: "t", "dn_e": "t"})
    table.block_of["t"] = "yard_w"
    table.active["t"] = Active("t-1", route, 1, move)
    table.crossing["t"] = T1
    table.occupied["t"] = ["yard_w", T1]
    table.readings["yard_w.B"] = True
    table.following["t"] = [
        Following(move, "yard_w.B", "dn_w.A", "dn_w.B", exit_read=True)
    ]
    return table


def headed() -> Table:
    """`granted`, with `dn_w.A` read occupied: the head is in `dn_w`, the tail
    not yet seen out of `yard_w`."""
    table = granted()
    move = table.following["t"][0].move
    table.block_of["t"] = "dn_w"
    table.active["t"].outstanding = None
    del table.crossing["t"]
    table.occupied["t"] = ["yard_w", T1, "dn_w"]
    table.readings["dn_w.A"] = True
    table.following["t"] = [
        Following(move, "yard_w.B", "dn_w.A", "dn_w.B", exit_read=True, head_in=True)
    ]
    return table


def test_a_repeated_reading_is_a_no_op() -> None:
    table = granted()
    new, effects = reading(table, "yard_w.B", True)
    assert new is table
    assert effects == []


def test_the_tail_out_releases_the_block_left() -> None:
    """The train is recorded in the block it is crossing into."""
    new, effects = reading(granted(), "yard_w.B", False)

    assert effects == [Disputed(frozenset()), Released("t", ("yard_w",))]
    assert "yard_w" not in new.locks
    assert new.occupied["t"] == [T1]
    assert new.block_of["t"] == "dn_w"
    assert new.crossing == {"t": T1}


def test_the_head_in_records_the_train_in_the_entered_block() -> None:
    new, effects = reading(granted(), "dn_w.A", True)

    assert effects == [Disputed(frozenset()), HeadIn("t", "dn_w")]
    assert new.block_of["t"] == "dn_w"
    assert new.occupied["t"] == ["yard_w", T1, "dn_w"]
    assert new.active["t"].outstanding is None
    assert new.crossing == {}
    assert new.following["t"][0].head_in


def test_the_whole_train_in_releases_the_transit_and_what_is_behind_it() -> None:
    """The newest move has ended with it."""
    new, effects = reading(headed(), "dn_w.A", False)

    assert effects == [
        Disputed(frozenset()),
        Released("t", ("yard_w", T1)),
        MoveEnded("t"),
    ]
    assert new.occupied["t"] == ["dn_w"]
    assert set(new.locks) == {"dn_w", T2, "dn_e"}
    assert new.following["t"] == []


def test_the_whole_train_in_keeps_a_block_ahead_whose_transit_is_locked() -> None:
    """`t` still occupies `dn_e`, behind `yard_w` on its list, from an earlier
    run, and has since been granted back into it over T2. The older move's
    tail in releases `yard_w` and T1 and not `dn_e` (#1230). The newest move
    has not ended."""
    table = headed()
    second = Move("dn_w", T2, "dn_e", [T2, "dn_e"], [])
    table.active["t"].cur_index = 2
    table.active["t"].outstanding = second
    table.crossing["t"] = T2
    table.occupied["t"] = ["dn_e", "yard_w", T1, "dn_w", T2]
    table.following["t"].append(Following(second, "dn_w.B", "dn_e.A", "dn_e.B"))

    new, effects = reading(table, "dn_w.A", False)

    assert effects == [Disputed(frozenset()), Released("t", ("yard_w", T1))]
    assert new.occupied["t"] == ["dn_e", "dn_w", T2]
    assert new.locks["dn_e"] == "t"
    assert [each.move for each in new.following["t"]] == [second]


def test_the_far_sensor_reading_occupied_ends_the_newest_move() -> None:
    new, effects = reading(headed(), "dn_w.B", True)

    assert effects == [Disputed(frozenset()), MoveEnded("t")]
    assert new.following["t"][0].at_far
    assert new.occupied["t"] == ["yard_w", T1, "dn_w"]


def test_the_far_sensor_says_the_head_is_in_where_the_entry_said_nothing() -> None:
    new, effects = reading(granted(), "dn_w.B", True)

    assert effects == [Disputed(frozenset()), HeadIn("t", "dn_w"), MoveEnded("t")]
    assert new.block_of["t"] == "dn_w"


def test_a_clear_reading_no_move_expects_changes_nothing() -> None:
    """A person backing a train at a platform: only the reading is recorded."""
    table = granted()
    new, effects = reading(table, "up_e.A", False)

    assert effects == [Disputed(frozenset())]
    assert new.readings == {**table.readings, "up_e.A": False}
    assert repr(replace(new, readings=table.readings)) == repr(table)


def test_an_occupied_reading_no_train_explains_is_disputed() -> None:
    _, effects = reading(granted(), "up_e.A", True)
    assert effects == [Disputed(frozenset({"up_e"}))]


def test_a_reading_leaves_the_table_it_was_given_unchanged() -> None:
    """The flags of each followed move included, so a search can branch from
    one table (#1315)."""
    table = granted()
    before = repr(table)

    after_head, _ = reading(table, "dn_w.A", True)
    reading(table, "yard_w.B", False)
    reading(after_head, "dn_w.A", False)

    assert repr(table) == before
    assert repr(after_head) != before


def test_a_new_list_of_sensors_not_reporting_is_held() -> None:
    table = granted()
    new, effects = not_reporting(table, frozenset({"dn_e.A"}))

    assert effects == []
    assert new.unknown_sensors == frozenset({"dn_e.A"})
    assert new.out_of_use == frozenset({"dn_e"})
    assert table.unknown_sensors == frozenset()


def test_an_unchanged_list_of_sensors_not_reporting_is_a_no_op() -> None:
    table = replace(granted(), unknown_sensors=frozenset({"dn_e.A"}))
    new, effects = not_reporting(table, frozenset({"dn_e.A"}))
    assert new is table
    assert effects == []


def test_a_release_gives_up_all_but_what_is_kept_and_the_residue() -> None:
    """In one `Released`, sorted."""
    table = granted()
    table.locks["up_e"] = "t"
    table.residue.add("up_e")

    new, effects = releasing(table, "t", ("yard_w", T1))

    assert effects == [Released("t", (T2, "dn_e", "dn_w"))]
    assert new.locks == {"yard_w": "t", T1: "t", "up_e": "t"}


def test_a_release_with_nothing_to_give_up_is_a_no_op() -> None:
    table = granted()
    new, effects = releasing(table, "t", list(table.locks))
    assert new is table
    assert effects == []


def test_a_retire_keeps_what_the_train_is_on_and_ends_its_run() -> None:
    """Its standing block and its `occupied` list; what it held ahead goes,
    and it is no longer active, crossing or departing."""
    table = granted()
    table.departure["t"] = "yard_e.B"

    new, effects = retiring(table, "t")

    assert effects == [Released("t", (T2, "dn_e", "dn_w"))]
    assert new.locks == {"yard_w": "t", T1: "t"}
    assert (new.active, new.crossing, new.departure) == ({}, {}, {})
    assert new.occupied["t"] == ["yard_w", T1]


def test_a_retire_keeps_what_it_is_told_to() -> None:
    new, effects = retiring(granted(), "t", {"yard_w"})
    assert effects == [Released("t", (T2, "dn_e", "dn_w", T1))]
    assert new.locks == {"yard_w": "t"}


def standing(occupied: bool) -> Table:
    """`t` at rest in `yard_w`, whose sensor at `B` reads `occupied`."""
    table, _ = a_route()
    table.locks["yard_w"] = "t"
    table.block_of["t"] = "yard_w"
    table.occupied["t"] = ["yard_w"]
    table.readings["yard_w.B"] = occupied
    return table


def test_removing_a_train_whose_block_reads_occupied_leaves_residue() -> None:
    """The block stays locked to the train until it reads clear (ADR-0069)."""
    new, effects = removing(standing(True), "t")

    assert effects == [Removed("t")]
    assert new.locks == {"yard_w": "t"}
    assert new.residue == {"yard_w"}
    assert (new.block_of, new.occupied) == ({}, {})
    assert broken(new) == []


def test_removing_a_train_whose_block_reads_clear_releases_it() -> None:
    new, effects = removing(standing(False), "t")

    assert effects == [Released("t", ("yard_w",)), Removed("t")]
    assert (new.locks, new.residue) == ({}, set())


def test_removing_a_crossing_train_keeps_the_transit_beside_an_occupied_block() -> None:
    """A restored hint: `t` over T1 with its tail in `yard_w`, which reads
    occupied. T1 is kept with `yard_w`; `dn_w` reads nothing and goes."""
    table = standing(True)
    table.locks.update({T1: "t", "dn_w": "t"})
    table.crossing["t"] = T1
    table.occupied["t"] = ["yard_w", T1]

    new, effects = removing(table, "t")

    assert effects == [Released("t", ("dn_w",)), Removed("t")]
    assert new.residue == {"yard_w", T1}
    assert new.crossing == {}
    assert broken(new) == []


def test_removing_a_train_off_the_layout_is_a_no_op() -> None:
    table, _ = a_route()
    new, effects = removing(table, "t")
    assert new is table
    assert effects == []


def residue() -> Table:
    """`t` removed over T1, with `yard_w.B` and `dn_w.A` reading occupied:
    both blocks and T1 are its residue."""
    table, _ = a_route()
    table.locks.update({"yard_w": "t", T1: "t", "dn_w": "t"})
    table.residue.update({"yard_w", T1, "dn_w"})
    table.readings.update({"yard_w.B": True, "dn_w.A": True})
    return table


def test_residue_opens_on_the_clear_reading() -> None:
    """The hand has lifted the loco. T1 stays kept for `yard_w`."""
    table, _ = reading(residue(), "dn_w.A", False)

    new, effects = opening(table)

    assert effects == [Opened("t", ("dn_w",))]
    assert new.locks == {"yard_w": "t", T1: "t"}
    assert new.residue == {"yard_w", T1}
    assert broken(new) == []


def test_a_transit_kept_for_residue_opens_once_neither_block_is_residue() -> None:
    """With the last of its blocks, in one `Opened`, sorted."""
    table, _ = opening(reading(residue(), "dn_w.A", False)[0])
    table, _ = reading(table, "yard_w.B", False)

    new, effects = opening(table)

    assert effects == [Opened("t", (T1, "yard_w"))]
    assert (new.locks, new.residue) == ({}, set())


def test_residue_does_not_open_while_a_sensor_is_listed() -> None:
    """A sensor not reporting says nothing about the loco (#1152)."""
    table, _ = reading(residue(), "dn_w.A", False)
    table, _ = not_reporting(table, frozenset({"dn_w.B"}))

    new, effects = opening(table)

    assert new is table
    assert effects == []


def test_placing_a_train_back_on_its_own_residue() -> None:
    """The block is free to it and becomes its standing lock: the person is
    saying the loco never left (ADR-0069). T1, kept for that block alone,
    opens after the placement."""
    table, _ = opening(reading(residue(), "dn_w.A", False)[0])
    assert table.free("yard_w", "t")

    new, effects = placing(table, "t", "yard_w")

    assert effects == [Placed("t", "yard_w"), Opened("t", (T1,))]
    assert new.locks == {"yard_w": "t"}
    assert new.residue == set()
    assert (new.block_of, new.occupied) == ({"t": "yard_w"}, {"t": ["yard_w"]})
    assert broken(new) == []


def test_placing_a_train_moves_its_standing_lock_without_a_release() -> None:
    """`train_placed` is the ledger line for a placement."""
    new, effects = placing(standing(True), "t", "up_e")

    assert effects == [Placed("t", "up_e")]
    assert new.locks == {"up_e": "t"}
    assert new.block_of == {"t": "up_e"}


def test_placing_a_crossing_train_releases_what_it_occupied_behind_it() -> None:
    """A restored hint over T1: T1 goes in a `Released` before the placement,
    and the train is no longer crossing or followed."""
    table = standing(True)
    table.locks.update({T1: "t", "dn_w": "t"})
    table.crossing["t"] = T1
    table.occupied["t"] = ["yard_w", T1]
    table.following["t"] = []

    new, effects = placing(table, "t", "dn_w")

    assert effects == [Released("t", (T1,)), Placed("t", "dn_w")]
    assert new.locks == {"dn_w": "t"}
    assert (new.crossing, new.following) == ({}, {})
    assert broken(new) == []


def test_placement_removal_release_and_opening_leave_the_table_unchanged() -> None:
    """So a search can branch from one table (#1315)."""
    lifted, _ = reading(residue(), "dn_w.A", False)
    tables = [granted(), standing(True), lifted]
    before = [repr(table) for table in tables]

    retiring(tables[0], "t")
    for table in tables:
        releasing(table, "t", ())
        removing(table, "t")
        placing(table, "t", "up_e")
        placing(table, "t", "yard_w")
        opening(table)

    assert [repr(table) for table in tables] == before
