"""A train `layout` lists on `state/overdue` is not moving (#1191, #1157).

`layout` stops a train that has not arrived within its allowance, where it
stands in the block it was entering, with its route and locks held. No sensor
reading will end that move: only a person can, so a drain that waited on it
would never end. The dispatcher reads the row for `state/moving` and for
nothing else (GLOSSARY.md, **Moving**).

Driven at the bus, the row pressed as `layout` publishes it, as
`test_out_of_use.py` presses `state/unknown_sensors`.
"""

import pytest

from tc49.bench.runner import Assembly
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import DRAINING
from tc49.lib.payload import moving
from tests.dispatcher.test_out_of_use import drawing
from tests.dispatcher.test_power import Reordering
from tests.harness import (
    leaves,
    live,
    load,
    movings,
    power,
    press,
    retaining,
    stock,
    ticks,
)

OVERDUE = "tc49/layout/state/overdue"
UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
MOVING = "tc49/dispatch/state/moving"
REQUEST_WANTED = "tc49/schedule/request_wanted"
ALLOCATION = "tc49/dispatch/state/allocation"
MEET = "crossover-yard/meet"

# What else the dispatcher says, none of which the row may move.
TRACED = (
    "lock_granted",
    "lock_released",
    "move_granted",
    "grant_refused",
    "aspects",
    "allocation",
    "disputed",
    "power_wanted",
)


def row(*trains: str) -> Payload:
    return {
        "trains": [
            {"train": train, "into": "dn_w", "reason": "no arrival"} for train in trains
        ]
    }


def lists(assembly: Assembly, *trains: str) -> None:
    press(assembly, OVERDUE, row(*trains))


def wants(assembly: Assembly, train: str, *dest: str) -> None:
    press(assembly, REQUEST_WANTED, {"train": train, "dest": list(dest)})


def under_way() -> Assembly:
    """freight_1 granted its move towards `yard_e`, nothing else moving."""
    assembly = live(MEET)
    wants(assembly, "freight_1", "yard_e.A")
    assert movings(assembly) == [False, True]
    assert assembly.dispatcher.state.crossing
    return assembly


# freight_1's crossing hint come back from the last session, with no request
# behind it (`test_a_restored_crossing_hint_with_no_request_is_moving`).
RESTORED: dict[str, Payload] = {
    ALLOCATION: {
        "trains": {"express_2": "up_w", "freight_1": "dn_e"},
        "crossing": {"freight_1": "crossover.dn_straight"},
        "locks": {},
        "requests": [],
    }
}


def test_a_listed_train_under_way_is_not_moving() -> None:
    """Its move is not over, and stays so: the train is still crossing and its
    request still active."""
    assembly = under_way()
    lists(assembly, "freight_1")

    assert movings(assembly) == [False, True, False]
    state = assembly.dispatcher.state
    assert "freight_1" in state.crossing
    assert "freight_1" in state.active


def test_a_listed_train_lets_a_drain_end() -> None:
    assembly = under_way()
    press(assembly, *power(DRAINING))
    lists(assembly, "freight_1")

    assert movings(assembly)[-1] is False


def test_a_row_without_the_train_moves_it_again() -> None:
    assembly = under_way()
    lists(assembly, "freight_1")
    lists(assembly)

    assert movings(assembly) == [False, True, False, True]


def test_another_train_under_way_keeps_the_railroad_moving() -> None:
    assembly = under_way()
    wants(assembly, "express_2", "yard_w.B")
    state = assembly.dispatcher.state
    assert {"freight_1", "express_2"} <= set(state.following)
    lists(assembly, "express_2")

    assert movings(assembly)[-1] is True


def test_a_listed_train_with_a_restored_hint_is_not_moving() -> None:
    """The hint stays: the row ends no crossing."""
    assembly = live(MEET, RESTORED)
    ticks(assembly, 1)
    lists(assembly, "freight_1")

    assert not assembly.dispatcher.state.active
    assert assembly.dispatcher.state.crossing == {"freight_1": "crossover.dn_straight"}
    assert movings(assembly) == [True, False]


def test_the_row_changes_nothing_else() -> None:
    """No lock taken or released, no grant, no refusal and no aspect: the row
    is read for `state/moving` alone. With express_2's request waiting on a
    block out of use, no new `grant_refused` is traced, so no sweep ran."""
    assembly = under_way()
    press(assembly, UNKNOWN_SENSORS, {"sensors": [{"sensor": "up_w.B"}]})
    wants(assembly, "express_2", "yard_w.B")
    state = assembly.dispatcher.state
    assert "express_2" not in state.following
    assert leaves(assembly, "grant_refused")

    before = (
        dict(state.locks),
        dict(state.crossing),
        set(state.active),
        state.out_of_use,
        [leaves(assembly, leaf) for leaf in TRACED],
    )
    lists(assembly, "freight_1")
    lists(assembly, "freight_1", "express_2")
    after = (
        dict(state.locks),
        dict(state.crossing),
        set(state.active),
        state.out_of_use,
        [leaves(assembly, leaf) for leaf in TRACED],
    )

    assert movings(assembly)[-1] is False
    assert after == before


def first_moving(retained: dict[str, Payload]) -> bool:
    """The `state/moving` a dispatcher opens with over freight_1's restored
    hint, on a bus already holding `retained` (ADR-0059). Built bare, since
    the simulator in an assembly says its own `state/overdue` first."""
    layout, roster, scenario = load(MEET)
    bus = retaining(RESTORED | retained)
    stood = {train: spec.at for train, spec in scenario.trains.items()}
    Dispatcher(bus, layout, roster, stood, FullRoute(layout, 2))
    return moving(bus.last_values.get(MOVING))


def test_a_row_the_bus_already_holds_counts_from_the_constructor() -> None:
    assert first_moving({OVERDUE: row("freight_1")}) is False
    assert first_moving({}) is True


@pytest.mark.parametrize(
    "unreadable", [{}, {"trains": None}, {"trains": [{"train": ""}]}]
)
def test_an_unreadable_row_is_dropped_and_the_last_value_stands(
    unreadable: Payload,
) -> None:
    assembly = under_way()
    lists(assembly, "freight_1")
    press(assembly, OVERDUE, unreadable)

    assert assembly.dispatcher.state.overdue == {"freight_1"}
    assert movings(assembly) == [False, True, False]


def test_a_stale_row_loses_to_the_later_one() -> None:
    clock = Clock()
    layout = drawing("single-track-meet")
    bus = Reordering(clock, OVERDUE)
    dispatcher = Dispatcher(bus, layout, stock(), {}, FullRoute(layout, 2))

    clock.advance(10.0)
    bus.publish(OVERDUE, row("runner"))
    clock.advance(20.0)
    bus.publish(OVERDUE, row("other"))
    bus.drain()

    assert dispatcher.state.overdue == {"other"}
