"""The fast clock: the railroad's time of day, run at its speed-up from where
it was started (ADR-0090)."""

import time

import pytest

from tc49.lib.fast_clock import (
    DAY_S,
    FastClock,
    KeptClock,
    kept_clock,
    start_of,
    time_of_day,
)


def test_it_reads_its_start_before_any_time_has_passed() -> None:
    clock = FastClock(start=7 * 3600, speed_up=1.0, since=100.0)
    assert clock.time(100.0) == 7 * 3600


def test_it_runs_at_its_speed_up() -> None:
    """At 8, a real minute is eight on the railroad."""
    clock = FastClock(start=7 * 3600, speed_up=8.0, since=0.0)
    assert clock.time(60.0) == 7 * 3600 + 8 * 60


def test_it_reads_whole_seconds() -> None:
    clock = FastClock(start=0, speed_up=1.5, since=0.0)
    assert clock.time(1.0) == 1


def test_it_wraps_at_midnight_and_has_no_date() -> None:
    clock = FastClock(start=DAY_S - 10, speed_up=1.0, since=0.0)
    assert clock.time(15.0) == 5
    assert clock.time(15.0 + 3 * DAY_S) == 5


def test_its_row_is_the_time_and_the_speed_up() -> None:
    clock = FastClock(start=3600, speed_up=4.0, since=0.0)
    assert clock.row(1.0) == {"time": 3604, "speed_up": 4.0}


def test_a_speed_up_that_is_not_greater_than_zero_is_refused() -> None:
    with pytest.raises(ValueError):
        FastClock(start=0, speed_up=0.0, since=0.0)


def test_the_time_of_day_is_seconds_since_midnight() -> None:
    """What a railroad with no start time of its own starts at: the box's
    wall clock, read as a time of day (ADR-0090, decision 4)."""
    moment = time.struct_time((2026, 10, 24, 13, 5, 9, 5, 297, 0))
    assert time_of_day(moment) == 13 * 3600 + 5 * 60 + 9


def test_a_new_time_is_taken_at_once() -> None:
    """A person sets the clock (ADR-0090, decision 2): it reads the new time
    from now and runs at the speed-up it had."""
    clock = FastClock(start=7 * 3600, speed_up=8.0, since=0.0)
    set_ = clock.changed(100.0, time=9 * 3600)
    assert set_.time(100.0) == 9 * 3600
    assert set_.time(101.0) == 9 * 3600 + 8


def test_a_new_speed_up_runs_from_where_the_clock_stands() -> None:
    clock = FastClock(start=7 * 3600, speed_up=1.0, since=0.0)
    set_ = clock.changed(60.0, speed_up=8.0)
    assert set_.time(60.0) == 7 * 3600 + 60
    assert set_.time(61.0) == 7 * 3600 + 68


def test_a_new_speed_up_loses_no_part_of_a_second() -> None:
    """Half a fast second stood is still there at the new speed-up: setting
    it again and again does not hold the clock back."""
    clock = FastClock(start=0, speed_up=1.0, since=0.0)
    set_ = clock.changed(0.5, speed_up=2.0)
    assert set_.time(0.75) == 1


def test_both_are_taken_together() -> None:
    clock = FastClock(start=0, speed_up=1.0, since=0.0)
    set_ = clock.changed(10.0, time=3600, speed_up=4.0)
    assert set_.row(11.0) == {"time": 3604, "speed_up": 4.0}


def test_nothing_asked_changes_nothing() -> None:
    clock = FastClock(start=3600, speed_up=4.0, since=0.0)
    assert clock.changed(10.0).time(20.0) == clock.time(20.0)


def test_a_kept_clock_reads_its_start_as_hours_and_minutes() -> None:
    kept = kept_clock({"start": "06:45", "speed_up": 8})
    assert kept == KeptClock(start=(6 * 60 + 45) * 60, speed_up=8.0)


def test_a_kept_clock_is_written_as_the_document_it_was_read_from() -> None:
    doc = {"start": "23:05", "speed_up": 2.5}
    assert kept_clock(doc).document() == doc


def test_a_railroad_is_loaded_at_its_start_time() -> None:
    clock = KeptClock(start=6 * 3600, speed_up=4.0).started(50.0)
    assert clock.time(50.0) == 6 * 3600
    assert clock.time(51.0) == 6 * 3600 + 4


@pytest.mark.parametrize(
    "doc",
    [
        None,
        {"start": "06:00"},
        {"speed_up": 1},
        {"start": "06:00", "speed_up": 1, "date": "monday"},
        {"start": 750, "speed_up": 1},
        {"start": "6:00", "speed_up": 1},
        {"start": "24:00", "speed_up": 1},
        {"start": "06:60", "speed_up": 1},
        {"start": "06:00:30", "speed_up": 1},
        {"start": "06:00", "speed_up": 0},
        {"start": "06:00", "speed_up": -2},
        {"start": "06:00", "speed_up": float("nan")},
        {"start": "06:00", "speed_up": float("inf")},
        {"start": "06:00", "speed_up": True},
        {"start": "06:00", "speed_up": "8"},
    ],
)
def test_a_kept_clock_that_is_not_one_is_refused(doc: object) -> None:
    with pytest.raises(ValueError):
        kept_clock(doc)


def test_a_new_time_is_kept_as_a_start_rounded_down_to_the_minute() -> None:
    assert start_of(8 * 3600 + 59) == 8 * 3600
    assert start_of(8 * 3600) == 8 * 3600
