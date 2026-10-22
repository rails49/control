"""`state/moving`: whether a power cut now would strand a train (ADR-0078,
ADR-0062, #822, #844).

`layout` ends a drain by switching the supply off, and the moment it may is
the first at which nothing is moving. The dispatcher, which knows what is
granted, states it on a row of its own: true while any train is **crossing**
(GLOSSARY.md, **Moving**). It is a boolean beside power and not a value of it —
a drain can be moving, because a move already granted runs to its sensor, and
a train standing partway along its route, or `on` with nothing granted, is
not.

Driven at the bus: the gestures and `state/power` in, `state/moving` and the
trace out.
"""

from tc49.bench.runner import Assembly
from tc49.lib.inventory import DRAINING, OFF
from tests.harness import live, movings, power, press, ticks

REQUEST_WANTED = "tc49/schedule/request_wanted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
ALLOCATION = "tc49/dispatch/state/allocation"


def under_way() -> Assembly:
    """A live railroad with freight_1 one boundary into a route it was just
    launched on: a train the dispatcher has granted a move to and no sensor
    has yet finished with."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 1)
    return assembly


def test_moving_goes_true_at_the_grant_and_false_at_the_completion() -> None:
    """The whole of the row: nothing is granted, so nothing is moving; the
    launch grants and it is; the request completes and it is not again. Each
    value once, because the row moves only when what it says moves."""
    assembly = live("crossover-yard/meet")
    assert movings(assembly) == []  # nothing said until the bus is turned

    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert movings(assembly) == [False, True]
    assert assembly.dispatcher.state.crossing

    ticks(assembly, 40)
    assert assembly.dispatcher.state.active == {}
    assert movings(assembly) == [False, True, False]


def test_a_drain_over_a_train_under_way_is_moving() -> None:
    """The failure ADR-0062 exists for: the move already granted runs to its
    sensor, so a drain begins with `moving` true and a reader that cut the
    supply on the power word alone would strand the train."""
    assembly = under_way()
    press(assembly, *power(DRAINING))

    assert movings(assembly)[-1] is True
    assert assembly.dispatcher.state.crossing


def test_a_restored_crossing_hint_with_no_request_is_moving() -> None:
    """A hint the last session left is a train the dispatcher believes is
    between two blocks, and nothing but a person clears it (#123, #154).
    There is no request behind it — the queue comes back empty — so `active`
    is empty and the hint alone is what says the railroad is not still."""
    assembly = live(
        "crossover-yard/meet",
        {
            ALLOCATION: {
                "trains": {"express_2": "up_w", "freight_1": "dn_e"},
                "crossing": {"freight_1": "crossover.dn_straight"},
                "locks": {},
                "requests": [],
            }
        },
    )
    ticks(assembly, 1)

    assert not assembly.dispatcher.state.active
    assert movings(assembly) == [True]


def test_lifting_the_wedged_train_off_stops_the_moving() -> None:
    """The way out of a drain a train holds open forever: take the train off
    the layout (ADR-0039, ADR-0069). The gesture drops the hint and the
    request together, and the row follows it, or `layout` waiting to switch
    the supply off would wait on a railroad that has nothing left on it."""
    assembly = under_way()
    press(assembly, *power(DRAINING))
    press(assembly, PLACEMENT_WANTED, {"train": "freight_1", "block": None})

    assert movings(assembly)[-1] is False
    assert not assembly.dispatcher.state.crossing
    assert not assembly.dispatcher.state.active


def test_power_changes_nothing_moving_says() -> None:
    """Power going off moves no train, so it moves no row: `moving` answers
    for the trains and not for the switch."""
    assembly = under_way()
    said = movings(assembly)
    press(assembly, *power(OFF))
    assert movings(assembly) == said


def test_a_train_standing_partway_along_its_route_is_not_moving() -> None:
    """A drain stops a train under way in the block it is entering, with its
    route and its locks (ADR-0078, decision 4). Standing there it loses
    nothing when the supply goes, so the row reads false once the move's
    sensor has fired, though the request is still active (#844)."""
    assembly = under_way()
    press(assembly, *power(DRAINING))
    state = assembly.dispatcher.state
    assert movings(assembly)[-1] is True

    ticks(assembly, 6)

    assert movings(assembly)[-1] is False
    assert not state.crossing
    assert "freight_1" in state.active
    assert state.block_of["freight_1"] == "dn_w"
    assert state.active["freight_1"].route.blocks[-1] == "yard_e"
    assert {"dn_w", "crossover.dn_straight", "dn_e"} <= {
        resource for resource, holder in state.locks.items() if holder == "freight_1"
    }
