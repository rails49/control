"""The layout says whether a train may move, and the run holds when it may
not (ADR-0041, #159).

Track power is an observation before it is anything else, and the dispatcher
branches on one thing: whether it is `on`. Anything else holds the run, so
nothing more is committed and no signalled end goes on showing `clear` over
track with no volts in it. Power returning releases nothing — the operator
presses GO — and a GO pressed while the rails are dead is dropped, releasing
into them being how the next train is stranded like the first.

Driven at the bus, which is where both arrive: `tc49/layout/state/power` from
the layout binding, `tc49/dispatch/run_wanted` from a page.

A payload the reader cannot make an enum value of is one of the "not `on`"
cases too, and is driven at a dispatcher with no trace on its bus (#175).

The cut itself is the power press alone, with the live loop never turned:
the steel does not move while the supply is off, so the moves already sent
are never executed and no sensor ever answers them.
"""

from collections import deque
from typing import cast

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, assemble, placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import HELD, OFF, ON, RUNNING
from tests.harness import (
    RUN_WANTED,
    leaves,
    load,
    press,
    run_rows,
    run_wanted,
    runs,
    ticks,
)

POWER = "tc49/layout/state/power"


class Reordering(InProcessBus):
    """A bus that hands one topic's values to its subscribers backwards.

    The milestone-1 binding delivers in one total order, so the reordering
    MQTT permits has to be staged deliberately (#240): a publisher's
    reconnect, or a QoS-1 retransmission with more than one message in
    flight, can put a pair on the wire in one order and take it off in the
    other (ADR-0008). What is queued for the named topic is delivered newest
    first, each value carrying the stamp it was published with.
    """

    def __init__(self, clock: Clock, topic: str) -> None:
        super().__init__(clock)
        self._backwards = topic

    def drain(self) -> None:
        queued = list(self._queue)
        swapped = iter(
            reversed([entry for entry in queued if entry[0] == self._backwards])
        )
        self._queue = deque(
            next(swapped) if entry[0] == self._backwards else entry for entry in queued
        )
        super().drain()


class Unstamped(InProcessBus):
    """A bus that stamps nothing, and so publishes a state value exactly as
    it was handed one.

    What a binding on the other side of a broker can put on a topic: an older
    build that does not stamp, or a value hand-edited into the retained file.
    A payload proves nothing about its sender and is read rather than trusted
    (SYSTEM.md, rule 4).
    """

    def _stamped(self, payload: Payload) -> Payload:
        return payload


def dispatcher_on(bus: InProcessBus) -> Dispatcher:
    """The dispatcher of the usual railroad, on the bus it is given, with its
    trains stood where the scenario document stands them."""
    layout, roster, scenario = load("crossover-yard/meet")
    dispatcher = Dispatcher(
        bus, layout, roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    bus.drain()
    return dispatcher


def power(state: str) -> tuple[str, Payload]:
    """The layout reporting its supply, as `ticks` plans an event."""
    return (POWER, {"power": state})


def told(payload: object) -> Dispatcher:
    """A dispatcher on a bus of its own, told that on the power topic.

    The trace is not on this bus, and deliberately: it is a promise about
    what the *apps* write and fails loudly on a payload outside the
    inventory (SYSTEM.md, the trace). The dispatcher's rule is the opposite
    one — it reads what arrives and never raises (ADR-0034) — and that is
    what is under test here.
    """
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    dispatcher = Dispatcher(
        bus, layout, _roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    bus.drain()
    bus.publish(POWER, cast(Payload, payload))
    bus.drain()
    return dispatcher


def test_power_leaving_on_holds_a_running_run() -> None:
    """Either value: the dispatcher branches on "not `on`" and nothing else."""
    for state in ("off", "stopped"):
        assembly = assemble(*load("crossover-yard/meet"))
        ticks(assembly, 3, at={2: power(state)})
        assert runs(assembly) == ["running", "held"], state
        # And no end goes on showing `clear` over track with no volts in it,
        # which is the lie the hold refuses to tell (ADR-0037).
        shown = leaves(assembly, "aspects")[-1]["aspects"]
        assert set(shown.values()) == {"stop"}, state


@pytest.mark.parametrize(
    "payload",
    [{}, {"power": 42}, {"power": "sideways"}, "off"],
    ids=["no field", "not a string", "outside the set", "not an object"],
)
def test_a_power_payload_that_cannot_be_read_holds_the_run(payload: object) -> None:
    """Nothing on this topic takes the dispatcher down, and an unreadable
    value is no reason to go on running.

    Anything at all can arrive once the bus is not in-process (#173), so the
    value is read rather than subscripted. It fails towards the hold: a
    dropped power value would mean *not* holding, leaving the run committing
    over track whose state could not be read. So an unreadable payload is
    one of the "anything but `on`" cases the contract already has
    (DISPATCH.md), and the run holds exactly as `stopped` or `off` holds it.
    """
    dispatcher = told(payload)

    assert dispatcher.state.power != ON
    assert dispatcher.state.run == HELD


def test_the_same_value_twice_republishes_nothing(timetabled: Assembly) -> None:
    """A binding that restates its supply on a timer says nothing new, and an
    already-held run is not held again. Read as the rows went out, `moving`
    and all: the whole row is what the dispatcher compares (#406)."""
    ticks(timetabled, 5, at={1: power("off"), 2: power("off"), 3: power("off")})
    assert run_rows(timetabled) == [
        ("running", False),
        ("running", True),
        ("held", True),
    ]


def test_power_holds_a_run_that_is_already_held(timetabled: Assembly) -> None:
    """Nothing moves: the person held it, and the layout agrees."""
    ticks(timetabled, 5, at={1: run_wanted("held"), 3: power("off")})
    assert runs(timetabled) == ["running", "held"]


def test_a_stranded_train_keeps_its_locks_and_its_crossing_entry(
    timetabled: Assembly,
) -> None:
    """The failure this issue exists for, made honest rather than fixed.

    A move granted one boundary before the cut is a train between two blocks
    with no sensor coming. Its locks and its `crossing` entry stand — nothing
    on the bus retracts a `move` already sent, and the dispatcher must not
    guess where the train ended up — so it is drawn on its connection and
    cannot be freed short of a restart (Not this issue). What the hold buys
    is that no *other* train is granted anything over the top of it.

    The return request its train will now never depart is already queued —
    requests go in at the start of a run (ADR-0047) — and it stays queued:
    the strandedness reaches exactly as far as a launch that never comes.
    """
    ticks(timetabled, 2)  # the first transit completes; the next moves go out
    state = timetabled.dispatcher.state
    crossing = dict(state.crossing)
    locks = dict(state.locks)
    granted = len(leaves(timetabled, "move_granted"))
    routed = len(leaves(timetabled, "route_chosen"))
    released = len(leaves(timetabled, "lock_released"))
    assert crossing  # a train is between two blocks

    press(timetabled, POWER, {"power": "off"})

    assert state.crossing == crossing
    assert state.locks == locks
    assert len(leaves(timetabled, "move_granted")) == granted
    assert len(leaves(timetabled, "route_chosen")) == routed
    assert len(leaves(timetabled, "lock_released")) == released
    assert leaves(timetabled, "request_rejected") == []
    queued = leaves(timetabled, "allocation")[-1]["requests"]
    assert any(request["id"] == "freight_1-2" for request in queued)


def test_power_returning_grants_nothing_until_a_go(timetabled: Assembly) -> None:
    """The bar the hold exists for: an explicit GO before anything moves,
    whatever the rails did in the meantime."""
    ticks(timetabled, 6, at={1: power("off"), 3: power("on")})
    assert runs(timetabled) == ["running", "held"]
    granted = len(leaves(timetabled, "move_granted"))

    ticks(timetabled, 4, at={0: run_wanted("running")})
    assert runs(timetabled) == ["running", "held", "running"]
    assert len(leaves(timetabled, "move_granted")) > granted


def test_a_go_is_dropped_while_the_rails_are_dead(timetabled: Assembly) -> None:
    """In silence and to the trace, as every refused gesture is (ADR-0034):
    nothing is published, and the press is on the trace where it landed."""
    ticks(timetabled, 4, at={1: power("off"), 2: run_wanted("running")})

    assert runs(timetabled) == ["running", "held"]
    assert len(leaves(timetabled, "run_wanted")) == 1


def test_a_go_is_honoured_once_the_power_is_back(timetabled: Assembly) -> None:
    """The same press, after the same supply returned: the value is the run's
    answer to the rails and not to how often it was asked."""
    ticks(
        timetabled,
        6,
        at={
            1: power("off"),
            2: run_wanted("running"),
            3: power("on"),
            4: run_wanted("running"),
        },
    )
    assert runs(timetabled) == ["running", "held", "running"]


def test_the_run_is_never_running_while_the_rails_are_dead(
    timetabled: Assembly,
) -> None:
    """The refusal is aimed at the release alone.

    A hold asks for less than the railroad is already doing, so there is no
    state of the rails it can be refused in — and with the power off the run
    is already where it asks for, which is exactly why the two presses cannot
    be told apart at the bus. What can be told apart is the release, dropped
    where the hold is not, and the invariant it buys: the run is held for as
    long as the supply is anything but `on`.
    """
    ticks(timetabled, 6, at={1: power("off"), 3: run_wanted("running")})
    assert runs(timetabled) == ["running", "held"]

    press(timetabled, RUN_WANTED, {"run": "held"})
    assert timetabled.dispatcher.state.run == "held"
    assert runs(timetabled) == ["running", "held"]


# --- the stamp keeps a reordered pair straight (#240) ------------------------


def test_a_reordered_pair_leaves_the_later_value_in_place() -> None:
    """The failure this rule exists for: the supply goes off, then on, and
    the two arrive backwards. Nothing in the delivery says which is which —
    the stamp does, and the older one is ignored.

    Held the other way round it would be the worse of the two directions: the
    dispatcher would go on believing the track is dead while it is live, and
    a page would show a person the same.
    """
    clock = Clock()
    bus = Reordering(clock, POWER)
    dispatcher = dispatcher_on(bus)

    clock.advance(10.0)
    bus.publish(POWER, {"power": OFF})
    clock.advance(20.0)
    bus.publish(POWER, {"power": ON})
    bus.drain()  # `on` first, then the `off` published before it

    assert dispatcher.state.power == ON
    assert dispatcher.state.run == RUNNING


def test_the_same_pair_in_order_is_the_run_held() -> None:
    """The contrast, on an ordinary bus: the pair delivered as it was
    published leaves the supply where the later value put it. What the guard
    refuses is an older value and nothing else.
    """
    clock = Clock()
    bus = InProcessBus(clock)
    dispatcher = dispatcher_on(bus)

    clock.advance(10.0)
    bus.publish(POWER, {"power": ON})
    clock.advance(20.0)
    bus.publish(POWER, {"power": OFF})
    bus.drain()

    assert dispatcher.state.power == OFF
    assert dispatcher.state.run == HELD


def test_an_unstamped_value_is_taken_and_ordering_starts_again() -> None:
    """The publisher owns the value: one carrying no stamp — an older build
    of the binding, or a value hand-edited into a retained file — is acted
    on, and the stamp held against the topic goes with it. Refusing it would
    leave the run committing over track nobody had heard from.
    """
    bus = Unstamped(Clock())
    dispatcher = dispatcher_on(bus)

    bus.publish(POWER, {"at": 30.0, "power": ON})
    bus.drain()
    bus.publish(POWER, {"power": OFF})
    bus.drain()

    assert dispatcher.state.power == OFF
    assert dispatcher.state.run == HELD
