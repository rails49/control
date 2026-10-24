"""The fast clock's row as a layout binding holds it: said at each beat and
at once when a person sets it, and what is kept with the railroad (ADR-0090)."""

from collections.abc import Callable

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.clock_row import CLOCK, CLOCK_WANTED, FastClockRow
from tc49.lib.fast_clock import FastClock, KeptClock


class Monotonic:
    """A real clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def clocked(
    kept: list[KeptClock] | None = None,
) -> tuple[InProcessBus, Monotonic, Callable[[], None], list[Payload]]:
    """The fast clock's row on a bus, started at 07:00:30 at a speed-up of 1
    on a railroad that keeps 07:00, the beat that says it, and what it says.
    What it keeps goes in `kept`."""
    bus = InProcessBus(Clock())
    monotonic = Monotonic()
    said: list[Payload] = []
    bus.subscribe(CLOCK, lambda _topic, payload: said.append(payload))
    row = FastClockRow(
        bus,
        FastClock(7 * 3600 + 30, 1.0, monotonic.now),
        KeptClock(7 * 3600, 1.0),
        monotonic,
        (kept if kept is not None else []).append,
    )

    def beat() -> None:
        row.say()
        bus.drain()

    beat()
    return bus, monotonic, beat, said


def test_a_new_time_is_said_at_once_and_counted_on_from() -> None:
    bus, monotonic, beat, said = clocked()
    monotonic.now += 10
    bus.publish(CLOCK_WANTED, {"time": 9 * 3600})
    bus.drain()
    monotonic.now += 5
    beat()
    assert [row["time"] for row in said] == [7 * 3600 + 30, 9 * 3600, 9 * 3600 + 5]
    assert said[-1]["speed_up"] == 1


def test_a_new_speed_up_runs_from_where_the_clock_stood() -> None:
    bus, monotonic, beat, said = clocked()
    monotonic.now += 60
    bus.publish(CLOCK_WANTED, {"speed_up": 8})
    bus.drain()
    monotonic.now += 1
    beat()
    assert [row["time"] for row in said[1:]] == [7 * 3600 + 90, 7 * 3600 + 98]
    assert said[-1]["speed_up"] == 8


def test_a_new_time_is_kept_as_the_start_rounded_down_to_the_minute() -> None:
    """Setting the time saves it as the start time (ADR-0090, decision 3),
    with the speed-up the clock runs at."""
    kept: list[KeptClock] = []
    bus, _, _, _ = clocked(kept)
    bus.publish(CLOCK_WANTED, {"time": 9 * 3600 + 59})
    bus.drain()
    assert kept == [KeptClock(9 * 3600, 1.0)]


def test_a_new_speed_up_is_kept_with_the_start_it_had() -> None:
    """Where the clock stands is not kept, only what a person set: the
    railroad still starts at 07:00, now at 8."""
    kept: list[KeptClock] = []
    bus, monotonic, _, _ = clocked(kept)
    monotonic.now += 600
    bus.publish(CLOCK_WANTED, {"speed_up": 8})
    bus.publish(CLOCK_WANTED, {"time": 18 * 3600, "speed_up": 4})
    bus.drain()
    assert kept == [KeptClock(7 * 3600, 8.0), KeptClock(18 * 3600, 4.0)]


def test_a_clock_that_runs_keeps_nothing() -> None:
    """The store is written only when a person sets the clock, so the backup
    has nothing new to save while it runs (ADR-0090)."""
    kept: list[KeptClock] = []
    _, monotonic, beat, _ = clocked(kept)
    for _ in range(3):
        monotonic.now += 1
        beat()
    assert kept == []


def test_a_clock_gesture_that_cannot_be_read_says_nothing() -> None:
    """Dropped as any malformed gesture is (ADR-0034): no row, and the clock
    runs on as it was."""
    kept: list[KeptClock] = []
    bus, _, _, said = clocked(kept)
    for payload in ({}, {"time": 86400}, {"speed_up": 0}, {"time": 1, "speed_up": -1}):
        bus.publish(CLOCK_WANTED, payload)
    bus.drain()
    assert len(said) == 1
    assert kept == []
