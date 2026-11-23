"""A route may end in or pass through a block shorter than the train while the
railroad's settings say `short_blocks` (#1287).

Driven at the bus on `crossover-yard/meet` with `dn_w` cut to 1000, shorter
than `freight_1`'s 1100, and the `tc49/layout/state/settings` row as a layout
binding states it. The tail of a train sent so stands over the transit it came
in by, and nothing new protects it: the transit is released only once the entry
sensor reads clear, which a tail that never leaves it does not do.
"""

from dataclasses import replace
from typing import Any

from tc49.bench.runner import DEFAULT_K
from tc49.dispatcher import Dispatcher, Incremental
from tc49.dispatcher.dispatch import SETTINGS, broken
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import ON
from tests.dispatcher.test_power import Reordering
from tests.harness import POWER, load, retaining, settled

REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
T1 = "west_ladder.to_dn"


def short_dn_w(bus: InProcessBus) -> Dispatcher:
    """The dispatcher over the usual railroad with `dn_w` shorter than
    `freight_1`, `freight_1` in `yard_w` and `express_2` in `up_w`."""
    layout, roster, _ = load("crossover-yard/meet")
    layout = replace(layout, blocks={**layout.blocks, "dn_w": 1000})
    stood = {"freight_1": "yard_w", "express_2": "up_w"}
    return Dispatcher(bus, layout, roster, stood, Incremental(layout, DEFAULT_K))


def deliver(bus: InProcessBus, topic: str, payload: Payload) -> None:
    bus.publish(topic, payload)
    bus.drain()


def said(short_blocks: object) -> Payload:
    return {"short_blocks": short_blocks}


def test_short_blocks_is_off_until_a_row_says_otherwise() -> None:
    bus = InProcessBus(Clock())
    dispatcher = short_dn_w(bus)
    bus.drain()

    assert not dispatcher.state.short_blocks


def test_a_row_already_held_is_adopted_at_construction() -> None:
    dispatcher = short_dn_w(retaining({SETTINGS: said(True)}))

    assert dispatcher.state.short_blocks


def test_each_row_heard_sets_it_and_an_unreadable_one_leaves_it() -> None:
    bus = InProcessBus(Clock())
    dispatcher = short_dn_w(bus)

    deliver(bus, SETTINGS, said(True))
    assert dispatcher.state.short_blocks
    deliver(bus, SETTINGS, said("yes"))
    assert dispatcher.state.short_blocks
    deliver(bus, SETTINGS, {"point_gap": 1.0})
    assert dispatcher.state.short_blocks
    deliver(bus, SETTINGS, said(False))
    assert not dispatcher.state.short_blocks


def test_a_row_older_than_the_one_held_changes_nothing() -> None:
    """`true` then `false`, delivered backwards: the stamp says `false` is
    the later, and the older `true` is ignored as `state/power`'s is."""
    clock = Clock()
    bus = Reordering(clock, SETTINGS)
    dispatcher = short_dn_w(bus)

    clock.advance(10.0)
    bus.publish(SETTINGS, said(True))
    clock.advance(20.0)
    bus.publish(SETTINGS, said(False))
    bus.drain()  # `false` first, then the `true` published before it

    assert not dispatcher.state.short_blocks


def test_a_tail_that_never_clears_the_entry_sensor_keeps_its_transit() -> None:
    """`freight_1` sent into `dn_w`, 100 shorter than itself: its head is in
    and its tail never clears `dn_w.A`, so it keeps `west_ladder.to_dn`, and
    `express_2`'s move from `up_w` into `yard_w` over the west ladder is not
    granted. `dn_w.A` reading clear releases the transit, and the move is
    granted."""
    bus = InProcessBus(Clock())
    dispatcher = short_dn_w(bus)
    state = dispatcher.state
    granted: list[dict[str, Any]] = []
    bus.subscribe(
        "tc49/dispatch/move_granted", lambda topic, payload: granted.append(payload)
    )
    deliver(bus, POWER, {"power": ON})
    deliver(bus, SETTINGS, said(True))

    deliver(
        bus,
        REQUEST_SUBMITTED,
        {"id": "f-1", "train": "freight_1", "depart": "yard_w.B", "dest": ["dn_w.A"]},
    )
    for sensor, occupied in (
        ("yard_w.B", True),
        ("dn_w.A", True),
        ("yard_w.B", False),
        ("dn_w.B", True),
    ):
        deliver(bus, *settled(sensor, occupied))
    assert state.block_of["freight_1"] == "dn_w"
    assert state.locks[T1] == "freight_1"

    deliver(
        bus,
        REQUEST_SUBMITTED,
        {"id": "e-1", "train": "express_2", "depart": "up_w.A", "dest": ["yard_w.B"]},
    )
    assert [p["id"] for p in granted] == ["f-1"]
    assert state.locks[T1] == "freight_1"
    assert broken(state) == []

    deliver(bus, *settled("dn_w.A", False))

    assert T1 not in state.locks
    assert [p["id"] for p in granted] == ["f-1", "e-1"]
    assert granted[-1]["into"] == "yard_w"
    assert broken(state) == []
