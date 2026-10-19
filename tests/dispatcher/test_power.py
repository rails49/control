"""The dispatcher routes only while power is on (ADR-0078, #822).

Power is one switch a person turns, `on`, `draining` or `off`, and `layout`
states it. The dispatcher branches on one thing: whether it reads `on`.
Anything else routes nothing — no route chosen, no move granted, no lock
taken — and no signalled end goes on showing `clear` over a train that will
not be let past it. A move already granted is not retractable and runs to its
sensor whatever the power. Power reading `on` again runs a sweep, so a person
turning it on is the whole of the go.

Driven at the bus, which is where the value arrives: `tc49/layout/state/power`
as the layout states it, and the trace out. What the dispatcher does with a
value is the subject, so the value is stated rather than pressed and the
binding's rules about which press it answers stay out of it. The runs that
start off are built live — a batch run's timetable mints and is granted in
the opening drain, before any statement could land, so what queues into them
arrives as gestures.

A payload the reader cannot make an enum value of is one of the "not `on`"
cases too, and is driven at a dispatcher with no trace on its bus (#175).
"""

from collections import deque
from typing import cast

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import DRAINING, OFF, ON
from tests.harness import (
    POWER,
    leaves,
    live,
    load,
    minted,
    power,
    press,
    ticks,
)

REQUEST_WANTED = "tc49/schedule/request_wanted"


class Reordering(InProcessBus):
    """A bus that hands one topic's values to its subscribers backwards.

    The in-process bus delivers in one total order, so the reordering
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
    (BUS.md, rule 4).
    """

    def _stamped(self, payload: Payload) -> Payload:
        return payload


def ids(assembly: Assembly, leaf: str) -> list[str]:
    return [str(line["id"]) for line in leaves(assembly, leaf)]


def dispatcher_on(bus: InProcessBus) -> Dispatcher:
    """The dispatcher of the usual railroad, on the bus it is given, with its
    trains stood where the scenario document stands them."""
    layout, roster, scenario = load("crossover-yard/meet")
    dispatcher = Dispatcher(
        bus, layout, roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    bus.drain()
    return dispatcher


def told(payload: object) -> Dispatcher:
    """A dispatcher on a bus of its own, told `on` and then that on the power
    topic.

    The trace is not on this bus, and deliberately: it is a promise about
    what the *apps* write and fails loudly on a payload outside the
    inventory (SYSTEM.md, the trace). The dispatcher's rule is the opposite
    one — it reads what arrives and never raises (ADR-0034) — and that is
    what is under test here.
    """
    bus = InProcessBus(Clock())
    dispatcher = dispatcher_on(bus)
    bus.publish(POWER, {"power": ON})
    bus.drain()
    bus.publish(POWER, cast(Payload, payload))
    bus.drain()
    return dispatcher


def off_with_three_requests() -> Assembly:
    """A live railroad with the power off and three gestures queued into it:
    two of freight_1's in a chain around one of express_2's. The chain runs
    through `dn_w` and on to `yard_e`, the way a train carries on (ADR-0080):
    a chain out of a stub is rejected `unreachable`, its far end leading
    nowhere."""
    assembly = live("crossover-yard/meet")
    press(assembly, *power(OFF))
    press(
        assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["dn_w.A", "dn_w.B"]}
    )
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["yard_w.B"]})
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    return assembly


def test_a_dispatcher_with_no_power_reading_routes_nothing() -> None:
    """The railroad comes up `off` (ADR-0078), so a dispatcher nobody has
    told about the power takes it for `off`: nothing is routed over rails it
    has not heard from."""
    bus = InProcessBus(Clock())
    dispatcher = dispatcher_on(bus)
    assert dispatcher.state.power == OFF


@pytest.mark.parametrize("state", [OFF, DRAINING])
def test_nothing_is_granted_while_power_is_not_on(state: str) -> None:
    """The whole of the guarantee, on the events that would move a train:
    the requests arrive and are admitted, and no route is committed.
    Admission is cheap and reversible; launching is the commitment."""
    assembly = live("crossover-yard/meet")
    press(assembly, *power(state))
    press(
        assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["dn_w.A", "dn_w.B"]}
    )
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["yard_w.B"]})
    ticks(assembly, 3)

    assert len(ids(assembly, "request_admitted")) == 2
    assert leaves(assembly, "route_chosen") == []
    assert leaves(assembly, "move_granted") == []
    assert leaves(assembly, "grant_refused") == []
    # The startup standing locks and nothing since.
    assert {line["train"] for line in leaves(assembly, "lock_granted")} == {
        "freight_1",
        "express_2",
    }
    # And no end shows `clear` over a train that will not be let past it.
    shown = leaves(assembly, "aspects")[-1]["aspects"]
    assert set(shown.values()) == {"stop"}


@pytest.mark.parametrize("state", [OFF, DRAINING])
def test_a_train_under_way_takes_no_next_move(state: str) -> None:
    """A drain stops each moving train in the next block (ADR-0078): the
    move already granted runs to its sensors, and nothing more is granted —
    not to the train under way either. It keeps its route and its locks."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert len(leaves(assembly, "move_granted")) == 1

    press(assembly, *power(state))
    ticks(assembly, 6)

    state_now = assembly.dispatcher.state
    assert len(leaves(assembly, "move_granted")) == 1
    assert "freight_1" in state_now.active
    assert not state_now.crossing
    assert leaves(assembly, "request_completed") == []


def test_a_granted_move_completes_under_off() -> None:
    """A move already sent is not retractable, so a sensor applies where it
    lands whatever the power: the move ends and gives back the block and the
    transit behind it, rather than holding them for as long as the power is
    off."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    granted = leaves(assembly, "move_granted")[0]
    assert assembly.dispatcher.state.crossing == {"freight_1": granted["transit"]}

    press(assembly, *power(OFF))
    ticks(assembly, 4)

    assert assembly.dispatcher.state.crossing == {}
    released = leaves(assembly, "lock_released")[-1]
    assert released["resources"] == ["yard_w", granted["transit"]]
    assert len(leaves(assembly, "move_granted")) == 1


def test_power_on_sweeps_on_the_statement_itself() -> None:
    """Power reading `on` runs a sweep (ADR-0078, decision 6): the first route
    commits with the statement and no beat is waited out."""
    assembly = live("crossover-yard/meet")
    press(assembly, *power(OFF))
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert leaves(assembly, "route_chosen") == []

    press(assembly, *power(ON))
    assert ids(assembly, "route_chosen") == [minted(assembly, "freight_1")]


def test_power_on_after_a_drain_carries_on_what_was_granted() -> None:
    """`on` resumes: the train a drain stopped mid-route takes its next move
    and its request completes, on the route it kept."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    press(assembly, *power(DRAINING))
    ticks(assembly, 4)
    assert len(leaves(assembly, "move_granted")) == 1

    press(assembly, *power(ON))
    ticks(assembly, 20)

    assert len(leaves(assembly, "move_granted")) > 1
    assert ids(assembly, "route_chosen") == [minted(assembly, "freight_1")]
    assert ids(assembly, "request_completed") == [minted(assembly, "freight_1")]


def test_admissions_keep_their_order_while_off() -> None:
    """`_phases` stamps an admission with the sweep count it joined at, and
    the queue records the order power `on` will honour."""
    assembly = off_with_three_requests()
    assert ids(assembly, "request_admitted") == [
        minted(assembly, "freight_1"),
        minted(assembly, "express_2"),
        minted(assembly, "freight_1", 2),
    ]


def test_a_queue_built_while_off_leaves_in_the_order_it_accumulated() -> None:
    """Nothing reorders the list while off, so it leaves in the order it
    was admitted (ADR-0080)."""
    assembly = off_with_three_requests()
    press(assembly, *power(ON))
    ticks(assembly, 40)

    queued = [
        minted(assembly, "freight_1"),
        minted(assembly, "express_2"),
        minted(assembly, "freight_1", 2),
    ]
    assert ids(assembly, "route_chosen") == queued
    assert set(ids(assembly, "request_completed")) == set(queued)


def test_a_degenerate_request_waits_for_the_power_too() -> None:
    """A request whose train already stands in one of its own arrival blocks
    completes without moving a wheel, and still waits: "no `route_chosen`" is
    read literally, and a sweep that answered one request would be a sweep
    that committed."""
    assembly = live("crossover-yard/meet")
    press(assembly, *power(OFF))
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    ticks(assembly, 3)

    assert ids(assembly, "request_admitted") == [minted(assembly, "freight_1")]
    assert leaves(assembly, "route_chosen") == []

    press(assembly, *power(ON))
    assert leaves(assembly, "route_chosen")[0]["route"] == ["yard_w"]
    assert ids(assembly, "request_completed") == [minted(assembly, "freight_1")]


def test_the_same_value_twice_sweeps_once() -> None:
    """A binding that restates its supply says nothing new: an `on` read
    while already `on` is not the power returning, and routes nothing a
    sweep had not already."""
    assembly = live("crossover-yard/meet")
    press(assembly, *power(ON))
    published = len(leaves(assembly, "aspects"))
    press(assembly, *power(ON))
    assert len(leaves(assembly, "aspects")) == published


def test_a_stranded_train_keeps_its_locks_and_its_crossing_entry() -> None:
    """A move granted before the cut is a train between two blocks with no
    sensor coming, when the supply is really off. Its locks and its
    `crossing` entry stand — nothing on the bus retracts a `move` already
    sent, and the dispatcher must not guess where the train ended up — and
    what power `off` buys is that no *other* train is granted anything over
    the top of it. The live loop is not turned: the steel does not move while
    the supply is off."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    state = assembly.dispatcher.state
    crossing = dict(state.crossing)
    locks = dict(state.locks)
    assert crossing  # a train is between two blocks

    press(assembly, *power(OFF))
    press(assembly, REQUEST_WANTED, {"train": "express_2", "dest": ["yard_w.B"]})

    assert state.crossing == crossing
    assert state.locks == locks
    assert len(leaves(assembly, "move_granted")) == 1
    assert len(leaves(assembly, "route_chosen")) == 1
    assert leaves(assembly, "request_rejected") == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"power": 42}, {"power": "sideways"}, "off"],
    ids=["no field", "not a string", "outside the set", "not an object"],
)
def test_a_power_payload_that_cannot_be_read_routes_nothing(payload: object) -> None:
    """Nothing on this topic takes the dispatcher down, and an unreadable
    value is no reason to go on routing.

    Anything at all can arrive once the bus is not in-process (#173), so the
    value is read rather than subscripted. It fails towards `off`: a dropped
    power value would leave the dispatcher routing over track whose state
    could not be read (DISPATCH.md).
    """
    assert told(payload).state.power == OFF


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


def test_the_same_pair_in_order_is_the_power_off() -> None:
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


def test_an_unstamped_value_is_taken_and_ordering_starts_again() -> None:
    """The publisher owns the value: one carrying no stamp — an older build
    of the binding, or a value hand-edited into a retained file — is acted
    on, and the stamp held against the topic goes with it. Refusing it would
    leave the dispatcher routing over track nobody had heard from.
    """
    bus = Unstamped(Clock())
    dispatcher = dispatcher_on(bus)

    bus.publish(POWER, {"at": 30.0, "power": ON})
    bus.drain()
    bus.publish(POWER, {"power": OFF})
    bus.drain()

    assert dispatcher.state.power == OFF
