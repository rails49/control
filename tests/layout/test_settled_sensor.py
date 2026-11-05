"""`tc49/layout/state/settled/sensor/<block>.<end>`: what each sensor has read
for the settling time, kept so that a dispatcher restarted or a page opened
while a locomotive stands on a sensor knows it at once (#1168).

The bench railroad's `up_w` has the sensors `up_w.A` and `up_w.B`.
"""

from typing import cast

from tc49.layout.interface import SETTLING_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.inventory import device_topic
from tests.layout.railroad import (
    BLOCK_OCCUPIED,
    SENSOR,
    elapse,
    heard,
    occupancy,
    reads,
    settle,
    wired,
)

SETTLED = "tc49/layout/state/settled/sensor"
END = "up_w.A"
ROW = device_topic(SETTLED, END)


def published(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every row of every sensor from here on."""
    return heard(bus, f"{SETTLED}/#")


def readings(rows: list[tuple[str, Payload]]) -> list[tuple[str, object, object]]:
    """The rows heard, as the topic, the address and the level each carries."""
    return [(topic, row["addr"], row["occupancy"]) for topic, row in rows]


def test_a_level_that_stands_publishes_one_row() -> None:
    bus, app, clock = wired(reporting=False)
    rows = published(bus)

    reads(bus, END, "occupied")
    settle(bus, app, clock)

    assert readings(rows) == [(ROW, END, "occupied")]
    assert "at" in rows[0][1]


def test_nothing_is_published_before_the_settling_time_has_passed() -> None:
    bus, app, clock = wired(reporting=False)
    rows = published(bus)

    reads(bus, END, "occupied")
    settle(bus, app, clock, after=SETTLING_S / 2)

    assert rows == []


def test_a_flip_inside_the_settling_time_publishes_nothing() -> None:
    bus, app, clock = wired(reporting=False)
    reads(bus, END, "clear")
    settle(bus, app, clock)
    rows = published(bus)
    bus.drain()
    rows.clear()

    reads(bus, END, "occupied")
    elapse(clock, SETTLING_S / 2)
    reads(bus, END, "clear")
    settle(bus, app, clock)

    assert rows == []


def test_a_repeat_of_the_level_publishes_nothing() -> None:
    bus, app, clock = wired(reporting=False)
    reads(bus, END, "occupied")
    settle(bus, app, clock)
    rows = published(bus)
    bus.drain()
    rows.clear()

    reads(bus, END, "occupied")
    settle(bus, app, clock)

    assert rows == []


def test_unknown_publishes_nothing_and_leaves_the_row() -> None:
    """`unknown` stays on `state/unknown_sensors`: the row stands at the last
    level that settled, whether or not a sensor is listed."""
    bus, app, clock = wired(reporting=False)
    reads(bus, END, "occupied")
    settle(bus, app, clock)
    rows = published(bus)
    bus.drain()
    rows.clear()

    reads(bus, END, "unknown", "no model")
    settle(bus, app, clock)
    settle(bus, app, clock)

    assert rows == []
    assert bus.last_values[ROW]["occupancy"] == "occupied"


def test_a_level_that_takes_a_sensor_off_the_list_publishes_the_row() -> None:
    """Even a level equal to the one held: it is what took the sensor off, and
    a reader treats an equal level as a repeat."""
    bus, app, clock = wired(reporting=False)
    reads(bus, END, "occupied")
    settle(bus, app, clock)
    reads(bus, END, "unknown", "no model")
    settle(bus, app, clock)
    rows = published(bus)
    bus.drain()
    rows.clear()

    reads(bus, END, "occupied")
    settle(bus, app, clock)

    assert readings(rows) == [(ROW, END, "occupied")]


def test_a_sensor_that_has_settled_no_level_has_no_row() -> None:
    bus, app, clock = wired(reporting=False)
    settle(bus, app, clock)
    reads(bus, END, "unknown", "no model")
    settle(bus, app, clock)

    assert ROW not in bus.last_values


def test_a_sensor_not_on_the_drawing_gets_a_row_like_any_other() -> None:
    """Judging it is the reader's, as it is for the block event it also gets."""
    bus, app, clock = wired(reporting=False)
    rows = published(bus)

    reads(bus, "nowhere.A", "occupied")
    settle(bus, app, clock)

    assert readings(rows) == [
        (device_topic(SETTLED, "nowhere.A"), "nowhere.A", "occupied")
    ]


def test_two_sensors_settling_together_publish_in_the_order_they_came_due() -> None:
    bus, app, clock = wired(reporting=False)
    rows = published(bus)

    reads(bus, "up_w.B", "occupied")
    reads(bus, END, "occupied")
    settle(bus, app, clock)

    assert [row["addr"] for _topic, row in rows] == ["up_w.B", END]


def test_a_name_no_topic_can_carry_has_no_row_and_still_folds() -> None:
    """A name reaches a topic here and nowhere else, and a broker's client
    refuses a wildcard in a topic with a raise that would take the app down on
    whoever typed it (BUS.md, rule 4). The block event is a payload, and goes
    out as it always did."""
    bus, app, clock = wired(reporting=False)
    rows = published(bus)
    events = occupancy(bus)

    for name in ("up+w.A", "up#w.A"):
        bus.publish(SENSOR, cast(Payload, {"addr": name, "occupancy": "occupied"}))
        bus.drain()
    settle(bus, app, clock)

    assert rows == []
    assert events == [
        (BLOCK_OCCUPIED, {"block": "up+w"}),
        (BLOCK_OCCUPIED, {"block": "up#w"}),
    ]
