"""Every payload is read and never trusted (#287, SYSTEM.md rule 4).

Nine topics from six publishers reach this app, and it answers none of them:
it reports observations, so a refusal would have nowhere to go (ADR-0034). A
frame that cannot be read is dropped, silently and to the trace, and none of
them raises — a binding that raised on a payload would be taken down by
whoever published it, leaving the railroad running with nothing watching it.
"""

from typing import Any, cast

import pytest

from tc49.lib.bus import Payload
from tests.layout.railroad import (
    ALIGN,
    ASPECTS,
    BLOCK_OCCUPIED,
    DEVICE_LINK,
    DEVICE_SENSOR,
    DEVICE_TRACK,
    MODE,
    MODE_WANTED,
    MOVE,
    PLACED,
    POWER,
    POWER_WANTED,
    RAILROAD,
    REMOVED,
    THROTTLE_WANTED,
    WANTED_TRACK,
    align,
    build,
    energised,
    heard,
    move,
    occupancy,
    reads,
    settle,
    stand,
    wired,
)

COMMANDED = (
    ALIGN,
    MOVE,
    POWER_WANTED,
    MODE_WANTED,
    THROTTLE_WANTED,
    PLACED,
    REMOVED,
    ASPECTS,
)
"""Everything above the layout interface that reaches this app: two commands,
a person's press, the throttle's two gestures, the two placement facts and the
dispatcher's picture. A frame on one of these that cannot be read leaves the
app exactly as it was."""

FOLDED = (DEVICE_TRACK, DEVICE_LINK + "/shed")
"""The two device rows the railroad's power is folded from. An unreadable
frame here is dropped in the same sense — nothing is written and nothing
raises — but it is not *nothing*: a supply or a link that cannot be read is
not one a train may move on, so the fold falls to `off` (#181). The two tests
below say so."""

SUBSCRIBED = COMMANDED + FOLDED

UNREADABLE: tuple[Any, ...] = (
    "up_w",
    ["up_w"],
    42,
    None,
    {},
    {"train": None, "block": 7, "power": [], "aspects": "clear", "points": 1},
)


@pytest.mark.parametrize("topic", SUBSCRIBED)
def test_an_unreadable_frame_is_dropped_and_raises_nothing(topic: str) -> None:
    """Whatever arrives, on whichever topic: nothing is asked of the hardware
    and no train is anywhere it was not."""
    bus, app = build()
    written = heard(bus, "tc49/layout/state/wanted/#")
    bus.drain()
    standing = len(written)

    for payload in UNREADABLE:
        bus.publish(topic, cast(Payload, payload))
        bus.drain()

    assert len(written) == standing
    assert app.position == {}


@pytest.mark.parametrize("topic", COMMANDED)
def test_the_railroad_still_works_behind_a_frame_that_was_dropped(topic: str) -> None:
    """The app read none of it and kept its own state, so the ordinary
    sequence goes through afterwards exactly as it would have before."""
    bus, app = build()
    for payload in UNREADABLE:
        bus.publish(topic, cast(Payload, payload))
        bus.drain()

    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    assert app.position == {"freight_1": "dn_e"}


def test_a_placement_naming_no_block_is_read_as_no_placement() -> None:
    """`train_placed` never carries a null block — a train taken off the
    layout is `train_removed`, which names the train alone (ADR-0039) — so
    one that does is read the way an unreadable frame is."""
    bus, app = build()
    bus.publish(PLACED, {"train": "freight_1", "block": None})
    bus.drain()

    assert app.position == {}


def test_an_unreadable_supply_is_read_as_no_power() -> None:
    """The one reader here that answers a value rather than dropping the
    frame, and the reason is which way a failure falls: a supply that cannot
    be read is not one a train may move on (#181)."""
    bus, _app = build()
    energised(bus)
    assert bus.last_values[POWER]["power"] == "on"

    bus.publish(DEVICE_TRACK, cast(Payload, {"power": "sideways"}))
    bus.drain()
    assert bus.last_values[POWER]["power"] == "off"


def test_an_unreadable_link_is_not_a_link_that_is_up() -> None:
    """The same direction on the row beside it: a link a consumer cannot read
    is not one it may call good (ADR-0050)."""
    bus, _app = build()
    energised(bus)
    assert bus.last_values[POWER]["power"] == "on"

    bus.publish(DEVICE_LINK + "/shed", cast(Payload, {"id": "shed"}))
    bus.drain()
    assert bus.last_values[POWER]["power"] == "off"


def test_the_row_this_app_does_not_act_on_passes_by_unread() -> None:
    """A `device/point` is a position where hardware reports one, and this app
    acts on none: it goes past without being taken for something else."""
    bus, app = build()
    energised(bus)
    written = heard(bus, "tc49/layout/state/wanted/#")
    bus.drain()
    standing = len(written)

    bus.publish(
        "tc49/layout/state/device/point/12",
        {"addr": "12", "position": "thrown"},
    )
    bus.drain()

    assert len(written) == standing
    assert bus.last_values[POWER]["power"] == "on"
    assert app.position == {}


def test_an_unreadable_reading_is_no_information_about_that_end() -> None:
    """The third of the observed rows, and it falls the third way: `unknown`
    is the contract's own word for no information, so a frame that cannot be
    read leaves the end reading exactly what it last actually said and
    produces no edge (#288)."""
    bus, app, clock = wired()
    seen = occupancy(bus)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]

    for payload in UNREADABLE:
        bus.publish(DEVICE_SENSOR + "/up_e.A", cast(Payload, payload))
        bus.drain()
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_a_fresh_app_has_said_four_things_and_no_more() -> None:
    """It subscribes the observed half of the device vocabulary and writes
    the desired half, so nothing it publishes reaches its own handlers and
    there is no cascade to come up out of: a fresh railroad is which railroad
    it is (#371), the supply commanded off, the app saying it believes it is,
    and nobody driving anything."""
    bus, _app = build()
    assert set(bus.last_values) == {RAILROAD, WANTED_TRACK, POWER, MODE}
