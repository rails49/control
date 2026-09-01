"""The driver seam: a grant restated as the command, and a grant read (#261).

The driver is a stateless translator that knows nothing of the layout, so its
whole contract is that mapping and the mapping is asserted directly rather
than through an assembly, where a wrong translation lands far from its cause
([#39](https://github.com/rails49/control/issues/39)). A bus and the driver
on it: one grant in, one command out, the aspect turned into the speed the
command carries ([#283](https://github.com/rails49/control/issues/283)) and
no other topic touched.
"""

from typing import cast

from tc49.driver import Driver
from tc49.driver.driver import SPEEDS
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
"""One grant as the dispatcher publishes it: the driver acts on four of the
five fields and ignores the id, which correlates an answer and the driver
answers nothing."""

COMMANDED: Payload = {
    "train": "freight_1",
    "connection": "west_ladder",
    "transit": "to_dn",
    "into": "dn_w",
    "speed": 1.0,
}
"""What `HONEST` becomes: the transit split, the train and the block entered
carried across, and `clear` turned into full speed."""


def collect(bus: Bus, topic_filter: str) -> list[Payload]:
    seen: list[Payload] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append(payload))
    return seen


def grant(bus: Bus, payload: object) -> None:
    bus.publish(GRANTED, cast(Payload, payload))
    bus.drain()


def test_a_grant_becomes_the_command_with_the_transit_split() -> None:
    """The whole of the driver: the qualified transit the grant states is the
    connection and the bare transit the command states, the train and the
    block entered are carried across untouched, and the aspect leaves as a
    speed. No aspect and no id on the command: what the layout interface is
    handed is what moves and how fast, and correlating an answer is not a
    thing the driver does (ADR-0025)."""
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    grant(bus, HONEST)
    assert seen == [COMMANDED]


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

    Every one of them shows `clear`, so each is refused for the one reason it
    is here to state; an aspect the driver cannot price is its own test below.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    aspect = {"aspect": "clear"}
    unreadable: list[object] = [
        "freight_1 into dn_w",  # not an object at all
        ["freight_1", "west_ladder.to_dn", "dn_w"],  # nor a list of its fields
        aspect,  # an aspect and nothing to move
        {**aspect, "transit": "west_ladder.to_dn", "into": "dn_w"},  # no train
        {**aspect, "train": "freight_1", "into": "dn_w"},  # no transit
        {**aspect, "train": "freight_1", "transit": "west_ladder.to_dn"},  # no block
        {**aspect, "train": None, "transit": "west_ladder.to_dn", "into": "dn_w"},
        {**aspect, "train": "freight_1", "transit": 7, "into": "dn_w"},
        {**aspect, "train": "freight_1", "transit": "west_ladder.to_dn", "into": []},
        {**aspect, "train": "freight_1", "transit": "to_dn", "into": "dn_w"},  # bare
        {**aspect, "train": "freight_1", "transit": "west_ladder.", "into": "dn_w"},
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


def test_a_caution_grant_commands_the_slower_speed_a_clear_one_does_not() -> None:
    """The two aspects a granted move can carry — `caution` where one block
    is locked ahead, `clear` where two are (ADR-0025) — and the speed is the
    whole of the difference they make. Everything else about the command is
    the same move over the same transit, because where the train goes was
    settled before the aspect was shown.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    for aspect in ("clear", "caution"):
        grant(bus, {**HONEST, "aspect": aspect})

    assert seen == [COMMANDED, {**COMMANDED, "speed": 0.4}]


def test_a_driver_given_another_mapping_commands_that_mappings_numbers() -> None:
    """The mapping is a constructor argument and the module constant is only
    its default: a railroad whose locomotives crawl under `caution`, or one
    that signals a third aspect its dispatcher does not yet show, says so
    where it builds the driver.

    `SPEEDS` is what an unconfigured driver uses, asserted here rather than
    trusted, so the default and the injection are one statement.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus, {"clear": 0.75, "caution": 0.1})

    for aspect in ("clear", "caution"):
        grant(bus, {**HONEST, "aspect": aspect})

    assert [command["speed"] for command in seen] == [0.75, 0.1]
    assert dict(SPEEDS) == {"clear": 1.0, "caution": 0.4}


def test_an_aspect_the_mapping_does_not_carry_commands_nothing() -> None:
    """A grant the driver cannot price is dropped, and the run is not touched.

    `stop` is the case that matters on the railroad: it reads perfectly well
    and is no permission to move, so there is nothing to command and nothing
    to answer — a train stands by not being told to go. The rest are the same
    drop for the same reason: with no speed in the mapping there is nothing to
    fall back on but a number this component invented, which would be
    authority the dispatcher never gave.

    The honest grant after them still lands, so the drop is a drop and not a
    driver that has stopped listening.
    """
    bus = Bus()
    seen = collect(bus, MOVE)
    Driver(bus)

    for payload in (
        {**HONEST, "aspect": "stop"},
        {**HONEST, "aspect": "approach"},  # the middle aspect's retired name
        {**HONEST, "aspect": "CLEAR"},
        {**HONEST, "aspect": ""},
        {**HONEST, "aspect": 1.0},  # not a name at all
        {**HONEST, "aspect": None},
        {key: value for key, value in HONEST.items() if key != "aspect"},
    ):
        grant(bus, payload)
    assert seen == []

    grant(bus, HONEST)
    assert seen == [COMMANDED]


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
    grant(bus, {**HONEST, "aspect": "stop"})  # no speed to command
    grant(bus, {**HONEST, "transit": "to_dn"})  # unqualified: no connection

    assert [topic for topic in heard if topic != GRANTED] == [MOVE, MOVE]
