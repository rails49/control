"""A train a throttle holds counts as moving with both its sensors unknown
(#1187, GLOSSARY.md, **Moving**).

`layout` stops a train both of whose block's sensors stopped reporting only
where no throttle holds it (ADR-0081). One a person is driving runs on, so a
drain waits for it, as it waits for any person-driven train between its grant
and its arrival: until the person lets go of it or presses the stop sign.

Driven at the bus, `state/taken` pressed as `layout` publishes it, as
`test_out_of_use.py` presses `state/unknown_sensors`.
"""

from tc49.bench.runner import Assembly
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import DRAINING
from tests.dispatcher.test_out_of_use import (
    YARD,
    crossing_into_dn_w,
    drawing,
    lists,
    railroad,
)
from tests.dispatcher.test_power import Reordering
from tests.harness import movings, power, press, stock

TAKEN = "tc49/layout/state/taken"


def row(*trains: str) -> Payload:
    return {"taken": {train: "throttle-1" for train in trains}}


def holds(assembly: Assembly, *trains: str) -> None:
    press(assembly, TAKEN, row(*trains))


def test_a_held_train_between_two_unknown_sensors_is_moving() -> None:
    """And letting go of it lets the drain end."""
    assembly = crossing_into_dn_w()
    press(assembly, *power(DRAINING))
    holds(assembly, "freight")
    lists(assembly, "dn_w.A", "dn_w.B")

    assert movings(assembly) == [False, True]

    holds(assembly)
    assert movings(assembly) == [False, True, False]


def test_taking_a_train_stopped_between_two_unknown_sensors_moves_it_again() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.A", "dn_w.B")
    holds(assembly, "freight")

    assert movings(assembly) == [False, True, False, True]


def test_a_held_train_with_no_move_under_way_is_not_moving() -> None:
    assembly = railroad(YARD, freight=("yard_w", "A-to-B"))
    holds(assembly, "freight")

    assert movings(assembly) == [False]


def test_a_row_that_changes_nothing_publishes_nothing() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.A", "dn_w.B")
    holds(assembly, "freight")
    holds(assembly, "freight")

    assert movings(assembly) == [False, True, False, True]


def test_an_unreadable_entry_leaves_its_train_held_by_nobody() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.A", "dn_w.B")
    holds(assembly, "freight")
    press(assembly, TAKEN, {"taken": {"freight": 7}})

    assert movings(assembly) == [False, True, False, True, False]


def test_an_unreadable_payload_holds_nothing() -> None:
    assembly = crossing_into_dn_w()
    lists(assembly, "dn_w.A", "dn_w.B")
    holds(assembly, "freight")
    press(assembly, TAKEN, {"taken": None})

    assert assembly.dispatcher.state.held == frozenset()
    assert movings(assembly)[-1] is False


def test_a_row_the_bus_already_holds_counts_from_the_constructor() -> None:
    layout = drawing("single-track-meet")
    bus = Reordering(Clock(), TAKEN)
    bus.publish(TAKEN, row("runner"))
    dispatcher = Dispatcher(bus, layout, stock(), {}, FullRoute(layout, 2))

    assert dispatcher.state.held == {"runner"}


def test_a_stale_row_loses_to_the_later_one() -> None:
    clock = Clock()
    layout = drawing("single-track-meet")
    bus = Reordering(clock, TAKEN)
    dispatcher = Dispatcher(bus, layout, stock(), {}, FullRoute(layout, 2))

    clock.advance(10.0)
    bus.publish(TAKEN, row("runner"))
    clock.advance(20.0)
    bus.publish(TAKEN, row("other"))
    bus.drain()

    assert dispatcher.state.held == {"other"}
