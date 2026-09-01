"""Every payload the layout interface is handed is read (#262).

Rule 4: the bus authenticates no publisher, so a leaf naming `layout` or
`dispatch` says which component answers for it and nothing about who published
this frame. The binding that runs the railroad may not be taken down by one —
a `move` today comes from the driver, a placement from the dispatcher, and
under MQTT each is another container. What cannot be read is dropped, and the
next honest frame is acted on as if the drop had never happened.

Driven at the layout interface: a command in, sensor events out.
"""

import json
from pathlib import Path
from typing import cast

from tc49.bench.runner import placement
from tc49.lib.bus import Bus, Payload
from tc49.simulator import Simulator
from tests.harness import load
from tests.simulator.test_placement import MOVE, simulator, tick

HONEST: Payload = {
    "train": "freight_1",
    "connection": "west_ladder",
    "transit": "to_dn",
    "into": "dn_w",
}
"""One command as the driver publishes it: freight_1 stands in `yard_w`, and
`west_ladder.to_dn` joins `yard_w.B` to `dn_w.A`."""


def sensors(bus: Bus) -> list[tuple[str, Payload]]:
    """The occupancy events alone — not `tc49/layout/+`, which would sweep up
    the commands these tests publish."""
    seen: list[tuple[str, Payload]] = []
    for topic in ("tc49/layout/block_occupied", "tc49/layout/block_vacated"):
        bus.subscribe(topic, lambda topic, payload: seen.append((topic, payload)))
    return seen


def build(path: Path | None = None) -> tuple[Bus, Simulator]:
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = Bus()
    return bus, simulator(bus, layout, placement(scenario.trains), path)


def send(bus: Bus, topic: str, payload: object) -> None:
    bus.publish(topic, cast(Payload, payload))
    bus.drain()


def test_a_command_that_cannot_be_read_moves_nothing() -> None:
    """None of these raises out of the handler, none schedules a sensor
    event, and the honest command after them still crosses: a drop is a drop
    and leaves nothing behind."""
    bus, sim = build()
    seen = sensors(bus)

    unreadable: list[object] = [
        "freight_1 into dn_w",  # not an object at all
        ["freight_1", "west_ladder", "to_dn", "dn_w"],  # nor a list of its fields
        {},
        {k: v for k, v in HONEST.items() if k != "train"},
        {k: v for k, v in HONEST.items() if k != "connection"},
        {k: v for k, v in HONEST.items() if k != "transit"},
        {k: v for k, v in HONEST.items() if k != "into"},  # no block entered
        {**HONEST, "train": None},
        {**HONEST, "connection": ["west_ladder"]},
        {**HONEST, "transit": 7},
        {**HONEST, "into": {"block": "dn_w"}},
    ]
    for payload in unreadable:
        send(bus, MOVE, payload)
    tick(sim)
    assert seen == []

    send(bus, MOVE, HONEST)
    tick(sim)
    assert seen == [
        ("tc49/layout/block_occupied", {"block": "dn_w"}),
        ("tc49/layout/block_vacated", {"block": "yard_w"}),
    ]


def test_a_command_naming_a_transit_this_railroad_has_not_moves_nothing() -> None:
    """The names came off the bus and the layout is what says whether they
    name anything: reaching into it with them was a `KeyError` out of a
    handler, and the answer is a drop rather than a raise (`lib.layout`). A
    transit the layout does hold is read exactly as it was before, whatever
    block the command names beside it."""
    bus, sim = build()
    seen = sensors(bus)

    for absent in (
        {**HONEST, "connection": "north_ladder"},
        {**HONEST, "transit": "to_nowhere"},
        {**HONEST, "connection": "", "transit": "west_ladder.to_dn"},
    ):
        send(bus, MOVE, absent)
    tick(sim)
    assert seen == []


def test_a_command_whose_transit_does_not_reach_the_block_it_names_moves_nothing() -> (
    None
):
    """The layout holds `east_ladder.from_up`, which joins `up_e.B` to
    `yard_e.A` and touches `dn_w` nowhere: there is no track from anywhere
    over that transit into `dn_w`, so the command describes something this
    railroad does not do and is dropped (#276).

    express_2 stands in `up_e`, at one end of the transit named — the case
    that used to pass the position check, because the near end came back the
    transit's first end and the train happened to be standing there. Nothing
    rolls, no occupancy is published, nothing raises, and the honest command
    after it still crosses.
    """
    bus, sim = build()
    seen = sensors(bus)

    send(
        bus,
        MOVE,
        {
            "train": "express_2",
            "connection": "east_ladder",
            "transit": "from_up",
            "into": "dn_w",
        },
    )
    tick(sim)
    assert seen == []

    send(bus, MOVE, HONEST)
    tick(sim)
    assert seen == [
        ("tc49/layout/block_occupied", {"block": "dn_w"}),
        ("tc49/layout/block_vacated", {"block": "yard_w"}),
    ]


def test_a_command_carrying_a_field_the_binding_does_not_know_still_moves() -> None:
    """Unknown fields are ignored, which is what lets the inventory grow one
    without every binding being rebuilt (SYSTEM.md)."""
    bus, sim = build()
    seen = sensors(bus)

    send(bus, MOVE, {**HONEST, "aspect": "clear", "id": "freight_1-1"})
    tick(sim)
    assert ("tc49/layout/block_occupied", {"block": "dn_w"}) in seen


def test_a_placement_that_cannot_be_read_moves_no_steel(tmp_path: Path) -> None:
    """`train_placed` is the one thing besides a `move` that moves a train,
    so a frame claiming to be one is a frame claiming to have lifted a
    locomotive. The file is the steel: none of these touches it, and the
    honest placement after them does.

    A null block is dropped with the unreadable ones: the fact never carries
    one — a train off the layout is `train_removed` — so a null says nothing
    about where steel stands (ADR-0039).
    """
    path = tmp_path / "placement.json"
    bus, _sim = build(path)
    stood = {"express_2": "up_e", "freight_1": "yard_w"}

    unreadable: list[object] = [
        "freight_1 in up_w",
        {},
        {"train": "freight_1"},  # no block, which is not the same as a null one
        {"block": "up_w"},
        {"train": None, "block": "up_w"},
        {"train": "freight_1", "block": 7},
        {"train": "freight_1", "block": None},
    ]
    for payload in unreadable:
        send(bus, "tc49/dispatch/train_placed", payload)
    assert not path.exists()

    send(bus, "tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    assert json.loads(path.read_text()) == {**stood, "freight_1": "up_w"}


def test_a_removal_that_cannot_be_read_takes_no_steel_away(tmp_path: Path) -> None:
    """The other half: a frame that names no train names no steel to take
    off, so the railroad is left as it was and the train still moves."""
    path = tmp_path / "placement.json"
    bus, sim = build(path)

    for payload in ("freight_1", {}, {"train": None}, {"trains": ["freight_1"]}):
        send(bus, "tc49/dispatch/train_removed", payload)
    assert not path.exists()

    seen = sensors(bus)
    send(bus, MOVE, HONEST)
    tick(sim)
    assert ("tc49/layout/block_vacated", {"block": "yard_w"}) in seen


def test_an_align_carrying_anything_at_all_is_harmless() -> None:
    """The other command: simulated points are always aligned, so this
    binding reads nothing off it and there is nothing in a payload for it to
    fail on. The honest `move` behind it still crosses."""
    bus, sim = build()
    seen = sensors(bus)

    for payload in ("west_ladder.to_dn", {}, {"points": None}):
        send(bus, "tc49/layout/align", payload)
    send(bus, MOVE, HONEST)
    tick(sim)
    assert ("tc49/layout/block_occupied", {"block": "dn_w"}) in seen
