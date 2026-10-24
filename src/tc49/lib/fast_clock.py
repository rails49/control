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
"""

import math
import time
from dataclasses import dataclass

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
