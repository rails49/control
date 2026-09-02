"""Levels in, edges out: the fold from `device/sensor` (#288).

A detector reports presence at one block end, and presence is a level that can
be asked for at any time. What everything above the layout interface reads is
two anonymous events, `block_occupied` and `block_vacated`, so turning the
levels into edges is this app's private business and nothing above it learns
detector geometry (#194, ADR-0043).

Nothing here sleeps. The settling time is a constructor argument and the run
clock is driven directly, which is the only way a debounce can be tested at
all without making the suite wait for it.
"""

import logging

from tc49.layout import LayoutInterface
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    BLOCK_OCCUPIED,
    BLOCK_VACATED,
    DEVICE_SENSOR,
    Unstamped,
    align,
    elapse,
    energised,
    move,
    occupancy,
    railroad,
    reads,
    settle,
    stand,
    stock,
    wired,
)


class Kept(logging.Handler):
    """Every line the app logged, for the one thing it says to a person."""

    def __init__(self) -> None:
        super().__init__()
        self.said: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.said.append(record.getMessage())


def test_a_level_that_stands_past_the_settling_time_publishes_one_event() -> None:
    """The debounce in one sentence: a new level is held, and the event goes
    out when it has stood long enough."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    assert seen == []

    settle(bus, app, clock)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_a_level_that_flips_back_inside_the_window_is_never_seen() -> None:
    """A camera-based detector runs at 2-8 Hz with no debounce of its own and
    is biased towards reporting occupied. A flip inside the window is what the
    settling time exists for, and it reaches nothing upstream."""
    bus, app, clock = wired()
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    elapse(clock, 0.2)
    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)

    assert seen == []


def test_the_first_level_an_end_settles_says_what_the_block_reads() -> None:
    """A block this app has said nothing about is neither occupied nor clear
    to whoever reads the events, so the first settled level is news whichever
    way it falls — a block whose ends read clear is a block reported clear,
    which is what a dispute check has to compare against (#153)."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)

    assert seen == [(BLOCK_VACATED, {"block": "up_e"})]


def test_the_window_is_measured_from_the_reading_and_not_from_the_call() -> None:
    """Half the settling time is not the settling time: the level is still
    waiting, and the next stretch of clock is what publishes it."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock, after=0.15)
    assert seen == []

    settle(bus, app, clock, after=0.15)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_the_settling_time_is_the_one_that_was_injected() -> None:
    """The number is a fact about the detectors a railroad has, so it is
    given to the app rather than known by it (ADR-0030)."""
    bus, app, clock = wired(settling_s=5.0)
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock, after=1.0)
    assert seen == []

    settle(bus, app, clock, after=4.0)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_the_same_level_delivered_twice_publishes_one_event() -> None:
    """At-least-once delivery may repeat a level, and a repeat re-asserts what
    is already held. No counter and no dedup: the level is the whole of the
    state (#243)."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_a_train_crossing_publishes_the_two_events_in_the_order_the_steel_makes() -> (
    None
):
    """A train entering block Y trips Y's first detector with its head and its
    second once it is fully in. The first is `block_occupied(Y)` and the second
    is `block_vacated(X)` — the block behind, which no detector can name and
    the move this app carried out does. Occupied then vacated (ADR-0047)."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = occupancy(bus)

    reads(bus, "dn_e.A", "occupied")  # the head, at the end across the transit
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")  # fully in, which is the second sensor
    settle(bus, app, clock)

    assert seen == [
        (BLOCK_OCCUPIED, {"block": "dn_e"}),
        (BLOCK_VACATED, {"block": "up_w"}),
    ]


def test_the_second_sensor_reports_the_block_behind_only_once() -> None:
    """The crossing is finished by the reading that ends it, so a detector
    that goes on saying the same thing says nothing more about the block the
    train left."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = occupancy(bus)

    reads(bus, "dn_e.A", "occupied")
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "clear")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert seen == [
        (BLOCK_OCCUPIED, {"block": "dn_e"}),
        (BLOCK_VACATED, {"block": "up_w"}),
    ]


def test_the_tail_leaving_the_block_behind_publishes_no_second_vacate() -> None:
    """One departure is one release. The crossing named the block behind and
    said it was clear; the detectors on that block say the same thing a moment
    later, as the tail actually leaves, and that is the same fact arriving by
    the other route. The crossing owns what it published — it records the
    origin clear — so the fold sees no change and stays silent (#311)."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    reads(bus, "up_w.A", "occupied")
    reads(bus, "up_w.B", "occupied")
    settle(bus, app, clock)
    seen = occupancy(bus)

    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    reads(bus, "dn_e.A", "occupied")  # the head
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")  # fully in, so the block behind is clear
    settle(bus, app, clock)
    reads(bus, "up_w.B", "clear")  # and now the steel behind says so too
    settle(bus, app, clock)
    reads(bus, "up_w.A", "clear")
    settle(bus, app, clock)

    assert seen == [
        (BLOCK_OCCUPIED, {"block": "dn_e"}),
        (BLOCK_VACATED, {"block": "up_w"}),
    ]


def test_the_block_behind_clearing_first_is_still_one_release() -> None:
    """The other order, which is as much the railroad's as the first: the tail
    is out of the block behind at the instant it is fully into the block
    ahead, so which of the two readings settles first is a race. The block
    behind is released by whichever arrives, and the other says nothing —
    otherwise the same departure is announced twice (#311)."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    reads(bus, "up_w.A", "occupied")
    reads(bus, "up_w.B", "occupied")
    settle(bus, app, clock)
    seen = occupancy(bus)

    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_w.A", "clear")  # the block behind goes clear first
    reads(bus, "up_w.B", "clear")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")  # and only then is the train fully in
    settle(bus, app, clock)

    assert seen == [
        (BLOCK_OCCUPIED, {"block": "dn_e"}),
        (BLOCK_VACATED, {"block": "up_w"}),
    ]


def test_a_block_a_crossing_released_reads_occupied_again_as_any_other() -> None:
    """The crossing records the origin clear rather than forgetting it, so the
    next train into that block is an ordinary change in the fold: a block this
    app has said is clear going occupied is `block_occupied`, whether what
    cleared it was a detector or the crossing."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    reads(bus, "up_w.B", "occupied")
    settle(bus, app, clock)
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    reads(bus, "dn_e.A", "occupied")
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    reads(bus, "up_w.B", "clear")
    settle(bus, app, clock)
    seen = occupancy(bus)

    reads(bus, "up_w.A", "occupied")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_w"})]


def test_a_block_reads_occupied_while_either_of_its_ends_does() -> None:
    """Both detectors of a block stay inside the interface, and what they
    answer together is one occupancy: the block is clear when neither end
    reads occupied, and not before."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    reads(bus, "up_e.B", "occupied")
    settle(bus, app, clock)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]

    reads(bus, "up_e.A", "clear")
    settle(bus, app, clock)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]

    reads(bus, "up_e.B", "clear")
    settle(bus, app, clock)
    assert seen == [
        (BLOCK_OCCUPIED, {"block": "up_e"}),
        (BLOCK_VACATED, {"block": "up_e"}),
    ]


def test_a_level_no_move_explains_still_publishes_its_own_occupancy() -> None:
    """A hand putting a locomotive down is how every session starts, and a
    detector asserting on dirt looks the same from here. What to make of a
    reading nothing accounts for is the dispatcher's judgement — it holds the
    run and names the block for a person to walk (ADR-0048) — so this app
    publishes the occupancy and nothing else."""
    bus, app, clock = wired()
    energised(bus)
    seen = occupancy(bus)

    reads(bus, "up_w.A", "occupied")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_w"})]


def test_an_unknown_publishes_nothing_and_discards_no_level() -> None:
    """`unknown` is no information about that end: no edge comes of it, and
    the level the end actually had goes on standing. So the reading after it
    that repeats that level is a repeat, not a change."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)
    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]

    reads(bus, "up_e.A", "unknown", reason="not calibrated")
    settle(bus, app, clock)
    reads(bus, "up_e.A", "occupied")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_an_unknown_does_not_cancel_a_level_that_is_settling() -> None:
    """No information is not a contradiction: a level waiting out the window
    goes on waiting, and it is the level that arrived that publishes."""
    bus, app, clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    elapse(clock, 0.1)
    reads(bus, "up_e.A", "unknown", reason="drift")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


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
    the tail, which is what keeps occupied ahead of vacated."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = occupancy(bus)

    reads(bus, "dn_e.A", "occupied")
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert seen == [
        (BLOCK_OCCUPIED, {"block": "dn_e"}),
        (BLOCK_VACATED, {"block": "up_w"}),
    ]


def test_a_move_that_was_not_acted_on_leaves_no_crossing_behind() -> None:
    """The second event names the block behind because a move was carried
    out. A command that was refused carried out nothing, so the entered
    block's second sensor says only what its own block reads."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "freight_1", "up_e")  # not the transit's near end
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    seen = occupancy(bus)

    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "dn_e"})]


def test_a_reading_older_than_the_one_held_is_ignored() -> None:
    """Delivered backwards, the older value would leave a block end reading
    clear after the reading that said a train is on it — and the row keeps its
    last message, so it would stand for good (#240)."""
    clock = Clock()
    bus = Unstamped(clock)
    app = LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    seen = occupancy(bus)

    bus.publish(
        DEVICE_SENSOR + "/up_e.A",
        {"at": 20.0, "addr": "up_e.A", "occupancy": "occupied"},
    )
    bus.publish(
        DEVICE_SENSOR + "/up_e.A",
        {"at": 10.0, "addr": "up_e.A", "occupancy": "clear"},
    )
    bus.drain()
    settle(bus, app, clock)

    assert seen == [(BLOCK_OCCUPIED, {"block": "up_e"})]


def test_nothing_settles_while_the_clock_stands_still() -> None:
    """The settling time is time, and this app reads a clock rather than
    counting calls: `settle` on an unmoved clock publishes nothing."""
    bus, app, _clock = wired()
    seen = occupancy(bus)

    reads(bus, "up_e.A", "occupied")
    app.settle()
    bus.drain()

    assert seen == []
