"""The driver seam: a grant restated as the command, and a grant read (#261)."""

from typing import cast

from tc49.driver import Driver
from tc49.lib.bus import Bus, Payload

GRANTED = "tc49/dispatch/move_granted"
MOVE = "tc49/layout/move"

HONEST: Payload = {
    "id": "freight_1-1",
    "train": "freight_1",
    "transit": "west_ladder.to_dn",
    "into": "dn_w",
    "aspect": "clear",
}
"""One grant as the dispatcher publishes it, id and aspect included: the
driver acts on three of the five fields and ignores the rest, which is what
lets the inventory grow a field without the driver being rebuilt (SYSTEM.md)."""


def collect(bus: Bus, topic_filter: str) -> list[Payload]:
    seen: list[Payload] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append(payload))
    return seen


def grant(bus: Bus, payload: object) -> None:
    bus.publish(GRANTED, cast(Payload, payload))
    bus.drain()


def test_a_grant_becomes_the_command_with_the_transit_split() -> None:
    """The whole of the driver: the qualified transit the grant states is the
    connection and the bare transit the command states, and the train and the
    block entered are carried across untouched. No aspect and no id: the
    command names what moves, and turning an aspect into a speed is the end
    state's (ADR-0025)."""
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    grant(bus, HONEST)
    assert seen == [
        {
            "train": "freight_1",
            "connection": "west_ladder",
            "transit": "to_dn",
            "into": "dn_w",
        }
    ]


def test_a_grant_that_cannot_be_read_commands_nothing() -> None:
    """`move_granted` names the dispatcher because the dispatcher emits it,
    and a name is not a sender: the bus authenticates nobody, so a frame
    claiming to be a grant is one more thing anyone can publish, and a driver
    that raised on one would be taken down by whoever published it (SYSTEM.md,
    rule 4). Under MQTT that publisher is another process.

    None of these raises out of the handler, none commands anything, and the
    honest grant after them still lands. The last two fail on the split rather
    than on the shape: a transit missing either half leaves no connection or no
    transit to command with, and the form of the name is the whole of what the
    driver — which knows nothing of the layout — has to read.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    unreadable: list[object] = [
        "freight_1 into dn_w",  # not an object at all
        ["freight_1", "west_ladder.to_dn", "dn_w"],  # nor a list of its fields
        {},
        {"transit": "west_ladder.to_dn", "into": "dn_w"},  # no train
        {"train": "freight_1", "into": "dn_w"},  # no transit
        {"train": "freight_1", "transit": "west_ladder.to_dn"},  # no block entered
        {"train": None, "transit": "west_ladder.to_dn", "into": "dn_w"},
        {"train": "freight_1", "transit": 7, "into": "dn_w"},
        {"train": "freight_1", "transit": "west_ladder.to_dn", "into": ["dn_w"]},
        {"train": "freight_1", "transit": "to_dn", "into": "dn_w"},  # no connection
        {"train": "freight_1", "transit": "west_ladder.", "into": "dn_w"},  # no name
    ]
    for payload in unreadable:
        grant(bus, payload)
    assert seen == []

    grant(bus, HONEST)
    assert len(seen) == 1


def test_the_driver_holds_nothing_across_a_dropped_grant() -> None:
    """A drop is a drop and not a state: the translator holds no state at all
    (SYSTEM.md, driver footprint), so a frame it could not read leaves nothing
    behind for the next one to inherit and every honest grant is commanded,
    including a repeat of one already commanded."""
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    grant(bus, HONEST)
    grant(bus, {"train": "express_2", "into": "up_e"})
    grant(bus, HONEST)
    grant(bus, {**HONEST, "train": "express_2", "transit": "east_ladder.from_up"})
    assert [(command["train"], command["transit"]) for command in seen] == [
        ("freight_1", "to_dn"),
        ("freight_1", "to_dn"),
        ("express_2", "from_up"),
    ]
