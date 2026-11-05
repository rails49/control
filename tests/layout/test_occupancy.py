"""Levels in, levels out: from `tc49/layout/sensor` to the settled row (#288).

A detector reports presence at one block end, and presence is a level that can
be asked for at any time. What everything above the layout interface reads is
that level once it has stood for the settling time, on
`state/settled/sensor/<block>.<end>`. This app keeps no record of which block is
occupied (#1173).

Nothing here sleeps. The settling time is a constructor argument and the run
clock is driven directly, which is the only way a debounce can be tested at
all without making the suite wait for it.
"""

import logging

from tests.layout.railroad import (
    SENSOR,
    align,
    elapse,
    energised,
    heard,
    levels,
    move,
    reads,
    settle,
    stand,
    wired,
)


class Kept(logging.Handler):
    """Every line the app logged, for the one thing it says to a person."""

    def __init__(self) -> None:
        super().__init__()
        self.said: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.said.append(record.getMessage())


def test_a_level_that_stands_past_the_settling_time_publishes_one_row() -> None:
    """The debounce in one sentence: a new level is held, and the row goes
    out when it has stood long enough."""
    bus, app, clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    assert seen == []

    settle(bus, app, clock)
    assert seen == [("up_e.A", "occupied")]


def test_a_level_that_flips_back_inside_the_window_is_never_seen() -> None:
    """A camera-based detector runs at 2-8 Hz with no debounce of its own and
    is biased towards reporting occupied. A flip inside the window is what the
    settling time exists for, and it reaches nothing upstream."""
    bus, app, clock = wired()
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    elapse(clock, 0.2)
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)

    assert seen == []


def test_the_first_level_a_sensor_settles_is_news_whichever_way_it_falls() -> None:
    """A sensor this app has said nothing about is neither occupied nor clear
    to whoever reads the rows, so its first settled level goes out, clear as
    much as occupied (#153)."""
    bus, app, clock = wired(reporting=False)
    seen = levels(bus)

    reads(bus, "up_e.A", "clear")
    reads(bus, "up_e.B", "clear")
    settle(bus, app, clock)

    assert seen == [("up_e.A", "clear"), ("up_e.B", "clear")]


def test_the_window_is_measured_from_the_reading_and_not_from_the_call() -> None:
    """Half the settling time is not the settling time: the level is still
    waiting, and the next stretch of clock is what publishes it."""
    bus, app, clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock, after=0.15)
    assert seen == []

    settle(bus, app, clock, after=0.15)
    assert seen == [("up_e.A", "occupied")]


def test_the_settling_time_is_the_one_that_was_injected() -> None:
    """The number is a fact about the detectors a railroad has, so it is
    given to the app rather than known by it (ADR-0030)."""
    bus, app, clock = wired(settling_s=5.0)
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock, after=1.0)
    assert seen == []

    settle(bus, app, clock, after=4.0)
    assert seen == [("up_e.A", "occupied")]


def test_the_same_level_delivered_twice_publishes_one_row() -> None:
    """At-least-once delivery may repeat a level, and a repeat re-asserts what
    is already held. No counter and no dedup: the level is the whole of the
    state (#243)."""
    bus, app, clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)

    assert seen == [("up_e.A", "occupied")]


def test_a_level_no_move_explains_still_publishes_its_row() -> None:
    """A hand putting a locomotive down is how every session starts, and a
    detector asserting on dirt looks the same from here. What to make of a
    reading nothing accounts for is the dispatcher's judgement — it names the
    block for a person to walk (#1154) — so this app publishes the row and
    nothing else."""
    bus, app, clock = wired()
    energised(bus)
    seen = levels(bus)

    reads(bus, "up_w.A", "occupied")
    settle(bus, app, clock)

    assert seen == [("up_w.A", "occupied")]


def test_an_unknown_publishes_nothing_and_discards_no_level() -> None:
    """`unknown` is no information about that end: no row comes of it, and
    the level the end actually had goes on standing on its row."""
    bus, app, clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    assert seen == [("up_e.A", "occupied")]

    reads(bus, "up_e.A", "unknown", reason="not calibrated")
    settle(bus, app, clock)

    assert seen == [("up_e.A", "occupied")]
    row = bus.last_values["tc49/layout/state/settled/sensor/up_e.A"]
    assert row["occupancy"] == "occupied"


def test_an_unknown_does_not_cancel_a_level_that_is_settling() -> None:
    """No information is not a contradiction: a level waiting out the window
    goes on waiting, and it is the level that arrived that publishes."""
    bus, app, clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    elapse(clock, 0.1)
    reads(bus, "up_e.A", "unknown", reason="drift")
    settle(bus, app, clock)

    assert seen == [("up_e.A", "occupied")]


def test_the_reason_is_logged_once_per_transition_into_unknown() -> None:
    """The detector knows why it cannot say, and the free text is for a
    person. Once per transition: a level that goes on being unknown is the
    same end still saying nothing."""
    bus, _app, _clock = wired()
    kept = Kept()
    log = logging.getLogger("tc49.layout.interface")
    log.addHandler(kept)
    log.setLevel(logging.INFO)
    try:
        reads(bus, "up_e.A", "unknown", reason="no model")
        reads(bus, "up_e.A", "unknown", reason="no model")
        reads(bus, "up_e.A", "clear")
        reads(bus, "up_e.A", "unknown", reason="drift")
    finally:
        log.removeHandler(kept)

    assert kept.said == [
        "detector at up_e.A says unknown: no model",
        "detector at up_e.A says unknown: drift",
    ]


def test_two_ends_coming_due_together_publish_in_the_order_they_arrived() -> None:
    """One call to `settle` may find more than one level due, and the order
    they go out in is the order the detectors reported them: the head before
    the tail."""
    bus, app, clock = wired(reporting=False)
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = levels(bus)

    reads(bus, "dn_e.A", "occupied")
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert seen == [("dn_e.A", "occupied"), ("dn_e.B", "occupied")]


def test_a_report_lands_on_the_addr_it_names() -> None:
    """One topic, and the payload names the sensor: the level lands on the end
    `addr` says, and that end's row is the one published."""
    bus, app, clock = wired()
    seen = levels(bus)

    bus.publish(SENSOR, {"addr": "up_e.B", "occupancy": "occupied"})
    bus.drain()
    settle(bus, app, clock)

    assert seen == [("up_e.B", "occupied")]


def test_the_same_level_reported_ten_times_publishes_one_row() -> None:
    """A detector says its level at least once a second, changed or not, so a
    repeat is the ordinary case and a no-op (#1147)."""
    bus, app, clock = wired()
    seen = levels(bus)

    for _report in range(10):
        reads(bus, "up_e.A", "occupied")
        settle(bus, app, clock)

    assert seen == [("up_e.A", "occupied")]


def test_a_report_naming_no_sensor_is_dropped() -> None:
    """Nothing to land it on: no `addr`, or one that is no `<block>.<end>`."""
    bus, app, clock = wired()
    seen = levels(bus)

    for addr in (None, 7, "", "up_e", ".A", "up_e.", "up_e.C"):
        bus.publish(SENSOR, {"addr": addr, "occupancy": "occupied"})
        bus.drain()
    settle(bus, app, clock)

    assert seen == []


def test_a_report_is_an_event_and_nothing_waits_on_the_broker() -> None:
    """Not retained: after a restart nothing old is replayed (#1147)."""
    bus, _app, _clock = wired()

    reads(bus, "up_e.A", "occupied")

    assert SENSOR not in bus.last_values


def test_nothing_settles_while_the_clock_stands_still() -> None:
    """The settling time is time, and this app reads a clock rather than
    counting calls: `settle` on an unmoved clock publishes nothing."""
    bus, app, _clock = wired()
    seen = levels(bus)

    reads(bus, "up_e.A", "occupied")
    app.settle()
    bus.drain()

    assert seen == []


def test_a_blocks_sensors_reading_publish_only_their_rows() -> None:
    """A block reads nothing here. A sensor going occupied, and going clear,
    says so on its own row and nothing else on the bus says anything of its
    block (#1173)."""
    bus, app, clock = wired()
    published = heard(bus, "tc49/layout/#")
    bus.drain()
    published.clear()

    for level in ("occupied", "clear"):
        reads(bus, "up_e.A", level)
        reads(bus, "up_e.B", level)
        settle(bus, app, clock)

    said = [topic for topic, _payload in published if topic != SENSOR]
    assert (
        said
        == [
            "tc49/layout/state/settled/sensor/up_e.A",
            "tc49/layout/state/settled/sensor/up_e.B",
        ]
        * 2
    )


def test_a_crossings_far_sensor_says_nothing_of_the_block_behind() -> None:
    """A train fully in has left its origin, and which block that frees is the
    dispatcher's to say: the far sensor's row is all that goes out of a sensor,
    the sensors of the block behind having read nothing (#1173)."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    reads(bus, "up_w.A", "occupied")
    settle(bus, app, clock)
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = levels(bus)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert seen == [("dn_e.A", "occupied"), ("dn_e.B", "occupied")]
    assert bus.last_values["tc49/layout/state/settled/sensor/up_w.A"]["occupancy"] == (
        "occupied"
    )
