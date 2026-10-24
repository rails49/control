"""The fast clock: the railroad's operating time of day (ADR-0090).

It runs at its **speed-up** from a start time, wraps at midnight and has no
date. `layout` holds one per build and publishes it on
`tc49/layout/state/clock` once a real second, so every page draws the same
time and none reads a wall clock of its own (ADR-0009). Nothing in the control
path reads it (ADR-0044): it feeds scheduling and scenery, never dispatch and
never safety.

The clock is handed the real seconds it is read at rather than reading them,
so the binding that runs it decides what a second is — the monotonic clock in
`layout` — and a test drives it without sleeping.

What the railroad **keeps** of it is its start time and its speed-up
(`KeptClock`), the store's `layouts/<layout>.clock.yaml`: `start` as
`"HH:MM"`, `speed_up` as a number. Read here from the document the store
answers and written back as the same document, so the store and `layout`
check one shape.
"""

import math
import re
import time
from dataclasses import dataclass
from typing import Any, cast

DAY_S = 24 * 60 * 60
"""Seconds in a day: where the fast clock wraps."""


@dataclass(frozen=True)
class FastClock:
    """The fast clock as it was started: `start` fast-clock seconds since
    midnight at `since`, a reading of the real clock in seconds, running
    `speed_up` fast seconds per real second from there."""

    start: int
    speed_up: float
    since: float

    def __post_init__(self) -> None:
        # Written so that `nan`, which compares false with everything, fails.
        if not self.speed_up > 0:
            raise ValueError(f"a speed-up of {self.speed_up} is not greater than 0")

    def time(self, now: float) -> int:
        """The time of day at the real clock's reading `now`, in whole
        fast-clock seconds since midnight, `0` to `DAY_S - 1`."""
        return int(self.start + (now - self.since) * self.speed_up) % DAY_S

    def changed(
        self, now: float, time: int | None = None, speed_up: float | None = None
    ) -> "FastClock":
        """The clock a person set at the real clock's reading `now`: reading
        `time` from now, or where it stands if None, and running at
        `speed_up`, or the one it ran at if None (ADR-0090, decision 2).

        Where it stands keeps the part of a second it had run into, so a
        speed-up set again and again does not hold the clock back."""
        rate = self.speed_up if speed_up is None else speed_up
        if time is not None:
            return FastClock(time, rate, now)
        stands = self.start + (now - self.since) * self.speed_up
        whole = math.floor(stands)
        return FastClock(whole % DAY_S, rate, now - (stands - whole) / rate)

    def row(self, now: float) -> dict[str, int | float]:
        """The payload of `tc49/layout/state/clock` at `now`, less the stamp
        the binding adds."""
        return {"time": self.time(now), "speed_up": self.speed_up}


def time_of_day(moment: time.struct_time) -> int:
    """`moment` as seconds since its midnight: what a railroad with no start
    time of its own starts at, read off the box's wall clock (ADR-0090,
    decision 4)."""
    return (moment.tm_hour * 60 + moment.tm_min) * 60 + min(moment.tm_sec, 59)


_HH_MM = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


@dataclass(frozen=True)
class KeptClock:
    """What a railroad keeps of its fast clock (ADR-0090, decision 3): the
    time of day it starts at when loaded, in seconds since midnight on a whole
    minute, and its speed-up."""

    start: int
    speed_up: float

    def __post_init__(self) -> None:
        if not 0 <= self.start < DAY_S or self.start % 60:
            raise ValueError(f"a start of {self.start} s is not a minute of the day")
        # Written so that `nan`, which compares false with everything, fails.
        if not (math.isfinite(self.speed_up) and self.speed_up > 0):
            raise ValueError(f"a speed-up of {self.speed_up} is not greater than 0")

    def started(self, now: float) -> FastClock:
        """The clock as the railroad is loaded at the real clock's reading
        `now`: at its start time (ADR-0090, decision 4)."""
        return FastClock(self.start, self.speed_up, now)

    def document(self) -> dict[str, str | float]:
        """The store's document: `start` as `"HH:MM"`, and `speed_up`."""
        minutes = self.start // 60
        return {
            "start": f"{minutes // 60:02d}:{minutes % 60:02d}",
            "speed_up": self.speed_up,
        }


def start_of(time: int) -> int:
    """`time`, in seconds since midnight, as a start time: rounded down to the
    minute, which is all `"HH:MM"` says (ADR-0090, decision 3)."""
    return time - time % 60


def kept_clock(doc: object) -> KeptClock:
    """The `KeptClock` a store document says, or `ValueError` naming what is
    wrong with it. Both fields, `start` as `"HH:MM"` text and `speed_up` a
    finite number greater than 0, and nothing else. A bool is no number,
    though Python counts it one.

    `start` is text because YAML 1.1, which the store reads in, takes an
    unquoted `12:30` as the integer 750: a document that says one is refused
    rather than read as a time it may not mean."""
    if not isinstance(doc, dict):
        raise ValueError("a clock is a document of 'start' and 'speed_up'")
    fields = cast(dict[str, Any], doc)
    if set(fields) != {"start", "speed_up"}:
        raise ValueError(
            f"a clock has 'start' and 'speed_up', not {sorted(map(str, fields))}"
        )
    start = fields["start"]
    matched = _HH_MM.fullmatch(start) if isinstance(start, str) else None
    if matched is None:
        raise ValueError(f"clock 'start' is {start!r}, not \"HH:MM\" quoted")
    speed_up = fields["speed_up"]
    if isinstance(speed_up, bool) or not isinstance(speed_up, (int, float)):
        raise ValueError(f"clock 'speed_up' is {speed_up!r}, not a number")
    hours, minutes = int(matched[1]), int(matched[2])
    return KeptClock((hours * 60 + minutes) * 60, float(speed_up))
