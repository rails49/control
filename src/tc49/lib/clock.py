"""The run clock: seconds since the session started.

The layout interface owns time (ADR-0009, ADR-0047): the simulator advances
this clock — to the next scheduled event in batch, by the slept step live —
and everything else only reads it. The trace tap stamps each line from it;
no app reads it at all, and no payload carries it.
"""

from dataclasses import dataclass


@dataclass
class Clock:
    now: float = 0.0

    def advance(self, to: float) -> None:
        assert to >= self.now
        self.now = to
