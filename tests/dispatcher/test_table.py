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
    Released,
    Route,
    Table,
    not_reporting,
    reading,
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
