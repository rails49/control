"""The fast clock: the railroad's time of day, run at its speed-up from where
it was started (ADR-0090)."""

import time

import pytest

from tc49.lib.fast_clock import DAY_S, FastClock, time_of_day


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
