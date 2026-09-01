"""The driver seam: a grant restated as the command, and a grant read (#261).

The driver is a stateless translator that knows nothing of the layout, so its
whole contract is that mapping and the mapping is asserted directly rather
than through an assembly, where a wrong translation lands far from its cause
([#39](https://github.com/rails49/control/issues/39)). A bus and the driver
on it: one grant in, one command out, the aspect carried past unread and no
other topic touched.
"""

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


def test_a_caution_grant_commands_what_a_clear_one_does() -> None:
    """The two aspects a granted move can carry — `caution` where one block
    is locked ahead, `clear` where two are (ADR-0025) — and the driver
    ignores both (SYSTEM.md, driver footprint): turning an aspect into a
    speed would need `move` to carry a speed, which milestone 1 leaves out
    and [#283](https://github.com/rails49/control/issues/283) brings.

    So the two command the same thing, and neither reaches the command:
    `move`'s fields are the four the inventory names, and the aspect is not
    among them.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    for aspect in ("clear", "caution"):
        grant(bus, {**HONEST, "aspect": aspect})

    commanded = {
        "train": "freight_1",
        "connection": "west_ladder",
        "transit": "to_dn",
        "into": "dn_w",
    }
    assert seen == [commanded, commanded]


def test_the_driver_publishes_the_command_and_nothing_else() -> None:
    """Read off everything the run put on the bus rather than off the source:
    the driver is the only thing subscribed here, so every frame that is not
    a grant pressed in is one it published, and the whole of what it adds is
    one `move` per grant it could read. It answers nothing and states nothing
    about itself.

    **No `align` among them**, which this file once would have asserted the
    other way round: setting the route is the dispatcher's, since it answers
    for the route being free and correctly set up, so `align` is its command
    and carries the points the layout gives (ADR-0022, ADR-0031). Where that
    command is asserted is `tests/system/test_skeleton.py`, beside the
    dispatcher that sends it.
    """
    bus = Bus()
    heard: list[str] = []
    bus.subscribe("tc49/#", lambda topic, payload: heard.append(topic))
    Driver(bus)

    grant(bus, HONEST)
    grant(bus, {**HONEST, "aspect": "caution"})
    grant(bus, "not a grant at all")
    grant(bus, {**HONEST, "transit": "to_dn"})  # unqualified: no connection

    assert [topic for topic in heard if topic != GRANTED] == [MOVE, MOVE]
