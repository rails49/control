"""The fast clock as a binding of the layout interface holds it for one
build: said on `tc49/layout/state/clock`, set on `tc49/layout/clock_wanted`,
and kept with the railroad (ADR-0090).

Both bindings hold it, `layout` timed off the monotonic clock and the
simulator off its run clock, so it is here and not in either app (ADR-0013).
What the clock reads is `lib.fast_clock`'s; this is the bus and the store
around it.
"""

import queue
import threading
import time
from collections.abc import Callable

from tc49.lib.bus import Bus, Payload
from tc49.lib.documents import Documents
from tc49.lib.fast_clock import FastClock, KeptClock, start_of, time_of_day
from tc49.lib.payload import wanted_clock
from tc49.lib.settings import THROTTLE_SILENCE_S, KeptInstallation, KeptSettings

type Kept = KeptClock | KeptSettings | KeptInstallation
"""What `Keeping` writes: a railroad's clock or settings, or the
installation's settings."""

CLOCK = "tc49/layout/state/clock"
"""The fast clock, said at the beat `alive_confirmed` is (ADR-0090)."""

CLOCK_WANTED = "tc49/layout/clock_wanted"
"""A person setting the fast clock: a time of day, a speed-up, or both
(ADR-0090, decision 2)."""


class Keeping:
    """A railroad's clock written to the store on a thread of its own, in the
    order it was set (ADR-0090, decision 3), and its settings beside it and
    the installation's, the other things `layout` writes when a person sets
    them (#1126, #1132).

    `Documents` waits for a store that does not answer, as it does for the
    loaded-railroad record; on the loop's thread that wait would hold up
    `alive_confirmed`, and something off the box cuts track power when that
    stops (#716). Setting the clock is not worth a dark railroad. The thread
    starts at the first thing set and is a daemon: one still waiting when the
    app stops loses that setting, as a store that never comes back would.
    """

    def __init__(self, documents: Documents, log: Callable[[str], None]) -> None:
        self._documents = documents
        self._log = log
        self._waiting: queue.SimpleQueue[tuple[str, Kept]] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None

    def keep(self, railroad: str, kept: Kept) -> None:
        """Write `kept` as `railroad`'s clock or settings, or as the
        installation's settings whatever railroad is loaded, after anything
        set before it."""
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._write, name="clock-keeping", daemon=True
            )
            self._thread.start()
        self._waiting.put((railroad, kept))

    def _write(self) -> None:
        while True:
            railroad, kept = self._waiting.get()
            try:
                if isinstance(kept, KeptClock):
                    self._documents.put_clock(railroad, kept)
                elif isinstance(kept, KeptSettings):
                    self._documents.put_settings(railroad, kept)
                else:
                    self._documents.put_installation(kept)
            except (OSError, ValueError, TypeError) as refused:
                if isinstance(kept, KeptInstallation):
                    self._log(f"the installation's settings were not kept: {refused}")
                    continue
                what = "clock was" if isinstance(kept, KeptClock) else "settings were"
                self._log(f"'{railroad}': the {what} not kept: {refused}")


class FastClockRow:
    """The fast clock as `layout` holds it for one build and says it: once a
    beat, and at once when a person sets it on `tc49/layout/clock_wanted`.
    The real seconds are read off `monotonic`.

    `kept` is the start time and speed-up the railroad keeps, or would keep:
    each setting is handed to `keep` with what it changed, a new time as the
    start rounded down to the minute and a new speed-up as it is (ADR-0090,
    decision 3). The clock as it runs is never kept.

    It subscribes as it is made, at each build: a reload forgets every
    subscription with the railroad it leaves."""

    def __init__(
        self,
        bus: Bus,
        fast: FastClock,
        kept: KeptClock,
        monotonic: Callable[[], float],
        keep: Callable[[KeptClock], None],
    ) -> None:
        self._bus = bus
        self._fast = fast
        self._kept = kept
        self._monotonic = monotonic
        self._keep = keep
        bus.subscribe(CLOCK_WANTED, self._wanted)

    def say(self) -> None:
        """What the clock reads now, on `tc49/layout/state/clock`."""
        self._bus.publish(CLOCK, self._fast.row(self._monotonic()))

    def _wanted(self, topic: str, payload: Payload) -> None:
        """A person set the clock (ADR-0090, decision 2): the new time taken
        at once, the new speed-up run at from now, and every page told
        without waiting for the beat. Taken whatever track power and the run
        are doing, and one that cannot be read is dropped as any malformed
        gesture is (ADR-0034). Then kept with the railroad."""
        wanted = wanted_clock(payload)
        if wanted is None:
            return
        self._fast = self._fast.changed(self._monotonic(), wanted.time, wanted.speed_up)
        self.say()
        self._kept = KeptClock(
            self._kept.start if wanted.time is None else start_of(wanted.time),
            self._fast.speed_up,
        )
        self._keep(self._kept)


def kept_by(
    documents: Documents, railroad: str, log: Callable[[str], None]
) -> KeptClock | None:
    """The clock `railroad` keeps, or None. One the store cannot read is
    said and started as none would be, at the wall clock's time: a clock is
    no reason not to build a railroad, and nothing in the control path reads
    it (ADR-0044)."""
    try:
        return documents.clock(railroad)
    except (ValueError, TypeError) as refused:
        log(f"'{railroad}': {refused} — the clock starts at the box's time")
        return None


def loaded(
    bus: Bus,
    kept: KeptClock | None,
    monotonic: Callable[[], float],
    moment: time.struct_time,
    keep: Callable[[KeptClock], None],
) -> FastClockRow:
    """The row a build starts: at the start time the railroad keeps
    (ADR-0090, decision 4), or, where it keeps none, at `moment`'s time of
    day, the box's wall clock read once a build, at a speed-up of 1, which is
    not written until a person sets the clock."""
    if kept is None:
        now = time_of_day(moment)
        fast = FastClock(now, 1.0, monotonic())
        kept = KeptClock(start_of(now), 1.0)
    else:
        fast = kept.started(monotonic())
    return FastClockRow(bus, fast, kept, monotonic, keep)


def silence(documents: Documents, log: Callable[[str], None]) -> float:
    """The throttle silence the installation keeps, in seconds, or
    `THROTTLE_SILENCE_S` where it keeps none. One the store cannot read is
    said and run as none would be, as a railroad's clock is: a setting is no
    reason not to come up (#1132)."""
    try:
        kept = documents.installation()
    except (ValueError, TypeError) as refused:
        log(f"{refused} — the throttle silence is the default")
        return THROTTLE_SILENCE_S
    return THROTTLE_SILENCE_S if kept is None else kept.throttle_silence
