"""`python -m tc49.layout` — the layout interface as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with no store and no other app running, this connects, waits for the
store, publishes its own retained rows and stays up; it exits on nothing but a
signal. Nothing here is ordered by anything else coming up first, which is why
compose carries no `depends_on`.

Two flags, the ones a compose service passes: where the broker is, and where
the store serves the documents the railroad is built from. Which railroad is
not one of them, the store recording that (ADR-0072, decision 5). Neither the drain period nor the
settling time is one of them — nothing outside this process has an opinion
about how often it takes what the broker's network thread left waiting, and
what a settling time is worth is a fact about the detectors a railroad has,
which is `LayoutInterface`'s argument and the suite's to drive (ADR-0030).
How long a throttle may go silent before its trains are let go of is not a
flag either: a container is configured by its environment, so it is
`TC49_LAYOUT_THROTTLE_SILENCE` on the layout's service (docs/DEPLOY.md), read
once here, and a bad one stops the app before it looks for a broker.

The startup order is `lib/startup.py`'s, and the steps from the store's
record to the rows cleared on a move are `rebuilding`'s, the loop both
layout bindings run (`lib/loading.py`, ADR-0086): the record first, standing
where the store cannot give it, `tc49/layout/railroad_wanted` followed before
each build, a drawing that is not a valid drawing named with `built: false`,
the trains kept under the same name. What is this binding's own is handed
over as `_Binding`. **Two documents**: the transits a `move` may name and
the signal at each block end come off the layout, and the addresses that
answer for a train off the roster, no address ever reaching a command
(#199). **The rows it adopts** are the traction rows a previous process left,
waited for as each build begins and zeroed by the constructor (#333).

Then the loop, which is this app's own and not the drain the other apps run:
advance the clock to wall time, `settle()`, drain, once per period. It moves
here out of `bench/runner.py`, whose physical branch paced this app in one
process. Nothing schedules `settle()` — a detector publishes a level *change*
and nothing else, so a process that never called it would sit on a quiet
railroad holding an arrival nobody was told about — and the period bounds the
resolution and nothing else: 0.1 s against 300 ms of settling has a settled
level acted on between 0.3 s and 0.4 s after it stood, which is the right
order for a detector.

The loop is also where `layout` says it is up: `alive_confirmed`, once a
second by the monotonic clock whatever the period, so that something off the
box can cut track power when the box goes silent (#716). Standing and
reloading are outside it and say nothing. The fast clock goes out at the same
beat, `tc49/layout/state/clock`, started at each build from the box's wall
time of day at a speed-up of 1 and run on the monotonic clock from there
(ADR-0090): the wall clock is read once a build, here, and by nothing in
`LayoutInterface`, which never learns what time it is (ADR-0044).

`LayoutInterface` is handed a `Bus` and nothing else in the package changes.
The clock is this process's own: the run clock is read here and advanced
nowhere else, the steel keeping its own time (ADR-0009, ADR-0047), and the
processes on a broker share no clock at all — the stamps on the wire come off
wall time in the binding (ADR-0059, decision 1).
"""

import contextlib
import math
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence

from tc49.layout.interface import (
    ALIVE_CONFIRMED,
    ALLOCATION,
    THROTTLE_SILENCE_S,
    WANTED_TRACTION,
    LayoutInterface,
)
from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.fast_clock import FastClock, time_of_day
from tc49.lib.layout import Layout
from tc49.lib.loading import NO_RAILROAD, Running, rebuilding
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.roster import Roster
from tc49.lib.startup import PERIOD_S, RETAINED_S, command_line, connected

CLIENT_ID = "tc49-layout"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (BUS.md, rule 4)."""

OWNED = (
    "tc49/layout/state/railroad",
    "tc49/layout/state/power",
    "tc49/layout/state/driving",
    "tc49/layout/state/taken",
    "tc49/layout/state/functions",
    "tc49/layout/state/clock",
    "tc49/layout/state/wanted/#",
)
"""The retained rows this app writes: which railroad is loaded, the supply as
it observes it, the driving mode, which throttle holds which train, which of
each train's functions are on, the fast clock, and every desired row under
`wanted/` — one per
address a railroad's wiring decides. The observed rows under `device/` are
**not** here: they belong to whatever answers for that address, which is
hardware and not this app (ADR-0043, ADR-0058), and a reload leaves them to
be cleared by the thing that wrote them.

A filter rather than a list, because the rows that matter on a reload are the
ones keyed by an address the new railroad does not have — a list of topics
would be a list of the addresses this railroad has, which is exactly the
wrong railroad's (ADR-0060)."""

ALIVE_S = 1.0
"""How often a built `layout` says it is up, in seconds of the monotonic
clock and not in turns of the loop: something off the box cuts track power
when `alive_confirmed` stops (#716), and its timeout is set against this
rate, which the drain period must not move."""

CLOCK = "tc49/layout/state/clock"
"""The fast clock, said at the beat `alive_confirmed` is (ADR-0090)."""

TRACTION = f"{WANTED_TRACTION}/#"
"""Every traction row, which is what has to be on the broker's way here before
the app is built on it. A filter and not a topic: a row exists for each
address a previous process wrote to, and this app holds no list of which."""


SILENCE_ENV = "TC49_LAYOUT_THROTTLE_SILENCE"
"""The environment variable on the layout's service that overrides how long a
throttle holding a train may go unheard, in seconds (docs/DEPLOY.md)."""

SILENCE_FLOOR_S = 1.0
"""What a silence must be longer than. A throttle says `throttle_alive` once a
second, so a silence of a second or less lets go of a train between two of
them from a throttle that is still there."""


def silence(environ: Mapping[str, str]) -> float:
    """`THROTTLE_SILENCE_S`, or whatever the deployment's environment says.

    Unset, or empty or blank, is no value at all and leaves the default, so
    that compose passing an unset variable through as `""` means the same
    thing as not passing it. A number greater than `SILENCE_FLOOR_S` is that
    many seconds. Anything else raises `ValueError` naming the variable: the
    app stops at start rather than letting go of trains on a silence nobody
    configured, and the person reading why knows which line of the env file
    to fix.
    """
    said = environ.get(SILENCE_ENV, "").strip()
    if not said:
        return THROTTLE_SILENCE_S
    try:
        seconds = float(said)
    except ValueError:
        seconds = math.nan
    # Written so that `nan`, which compares false with everything, fails.
    if not seconds > SILENCE_FLOOR_S:
        raise ValueError(
            f"{SILENCE_ENV} is {said!r}, not a number of seconds"
            f" greater than {SILENCE_FLOOR_S}"
        )
    return seconds


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`documents:`, `mqtt:`)."""
    print(f"layout: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    documents: Documents,
    railroad: str,
    stop: threading.Event,
    period_s: float = PERIOD_S,
    log: Callable[[str], None] = to_stderr,
    throttle_silence_s: float = THROTTLE_SILENCE_S,
) -> None:
    """The app: the broker, then the rebuild loop both layout bindings run
    (`lib/loading.py`, ADR-0086), handed this one's `_Binding`.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in any of the waits above it — and `main`
    lets that out.

    `railroad` is where this app starts **where the store records nothing**
    (`Answering.recorded`), read once the broker is there.

    The desired rows go with the railroad that is left — a speed for a
    locomotive the new railroad does not have, a position for a point it
    does not have, and nothing would ever republish either (`OWNED`).
    """
    if not connected(bus, stop, log):
        return
    binding = _Binding(bus, documents, stop, period_s, throttle_silence_s)
    rebuilding(bus, documents, railroad, stop, binding, log, period_s, RETAINED_S)


class _Binding:
    """What this app hands the rebuild loop: two documents read, the
    traction rows waited for before each build (#333), and a
    `LayoutInterface` built on them."""

    owned: Sequence[str] = OWNED

    def __init__(
        self,
        bus: MqttBus,
        documents: Documents,
        stop: threading.Event,
        period_s: float,
        throttle_silence_s: float,
    ) -> None:
        self._bus = bus
        self._documents = documents
        self._stop = stop
        self._period_s = period_s
        self._throttle_silence_s = throttle_silence_s

    def read(self, railroad: str) -> tuple[Layout, Roster]:
        """The pair the interface is built from: the railroad's topology and
        the stock that runs on it."""
        return self._documents.layout(railroad), self._documents.roster(railroad)

    def nothing(self, railroad: str) -> tuple[Layout, Roster]:
        """What this app runs on where `railroad`'s drawing is not a valid
        drawing and there is no build to keep: no block and no train under
        its name, so the row names it and the power is still answered
        (ADR-0085, decision 4)."""
        return Layout(railroad, {}, {}, frozenset(), {}), Roster(railroad, {})

    def layout(self, read: tuple[Layout, Roster]) -> Layout:
        return read[0]

    def build(
        self, read: tuple[Layout, Roster], position: dict[str, str], built: bool
    ) -> Running:
        """The traction rows seen, then the interface built on its own clock,
        starting at zero, and the fast clock started at the box's time of
        day: a railroad is loaded at its start time (ADR-0090, decision 4),
        and one with no start time of its own starts at the wall clock's, at
        a speed-up of 1."""
        retained(self._bus, self._stop)
        layout, roster = read
        clock = Clock()
        app = LayoutInterface(
            self._bus,
            layout,
            roster,
            clock,
            throttle_silence_s=self._throttle_silence_s,
            position=position,
            built=built,
        )
        fast = FastClock(time_of_day(time.localtime()), 1.0, time.monotonic())
        return _Running(self._bus, app, clock, fast, self._stop, self._period_s)


class _Running:
    """A built `LayoutInterface` and the loop that paces it: advance the
    clock to wall time, say it is up and what the fast clock reads,
    `settle()`, drain, once per period."""

    def __init__(
        self,
        bus: MqttBus,
        app: LayoutInterface,
        clock: Clock,
        fast: FastClock,
        stop: threading.Event,
        period_s: float,
    ) -> None:
        self._bus = bus
        self._app = app
        self._clock = clock
        self._fast = fast
        self._stop = stop
        self._period_s = period_s
        self._started = time.monotonic()
        # When it last said it is up and what the fast clock reads: kept
        # across `run` being entered again after a pick that was not built,
        # so the rate holds (#716, ADR-0090).
        self._alive: float | None = None

    @property
    def position(self) -> dict[str, str]:
        return self._app.position

    def run(self, until: Callable[[], bool]) -> None:
        while not until():
            now = time.monotonic()
            self._clock.advance(now - self._started)
            # Here and only here: standing, or reloading for another
            # railroad, says nothing, and loading needs the power off, so a
            # cut then changes nothing (#716).
            if self._alive is None or now - self._alive >= ALIVE_S:
                self._bus.publish(ALIVE_CONFIRMED, {})
                self._bus.publish(CLOCK, self._fast.row(now))
                self._alive = now
            self._app.settle()
            self._bus.drain()
            self._stop.wait(self._period_s)


def retained(
    bus: MqttBus, stop: threading.Event, timeout_s: float = RETAINED_S
) -> None:
    """Subscribe to the traction rows and give the broker its moment to hand
    over whatever it holds on them, before the app is built.

    What `LayoutInterface` reads out of `last_values` as it is constructed: a
    traction row is retained, so a broker that outlived the last process hands
    the speed it was left at back verbatim and a translator subscribed to it
    sends that speed at the first connect — the locomotive rolls the moment
    somebody powers the rails, with no grant and nothing on the bus that says
    why (#333, ADR-0054). Zeroing them is the constructor's, and it can only
    zero the rows it can see.

    The window is waited out **whole**, for the reason `lib/startup.py` gives
    a wait with nothing to name: what is being waited for is a row per
    address a previous process wrote to, and this app holds no list of which.
    A second on the way up, once, against a locomotive that would otherwise
    take itself away.

    The value is read here only in the sense of being waited for; reading it is
    the app's, and this handler does nothing with what it is given.

    The dispatcher's allocation is waited for in the same window: it is where
    the app takes each train's position from, `train_placed` being an event
    the broker does not keep (#960).
    """
    bus.subscribe(TRACTION, lambda _topic, _payload: None)
    bus.subscribe(ALLOCATION, lambda _topic, _payload: None)
    stop.wait(timeout_s)


def main() -> None:
    parser = command_line(
        prog="python -m tc49.layout",
        description="Run the layout interface against a broker: the one writer"
        " of what the hardware is asked to do.",
    )
    args = parser.parse_args()
    try:
        host, port = address(args.broker)
    except ValueError as refused:
        parser.error(str(refused))
    try:
        quiet_s = silence(os.environ)
    except ValueError as refused:
        parser.error(str(refused))
    # A signal is what ends this app, and SIGTERM is the one a container is
    # stopped with: given SIGINT's own handler it raises where the process
    # stands, so a wait for a store that never comes up ends on it too.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    to_stderr(f"broker {host}:{port}, store {args.store}")
    to_stderr(f"a throttle silent for {quiet_s}s lets go of its trains")
    bus = MqttBus(host, port, client_id=CLIENT_ID)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            serve(
                bus,
                Documents(args.store),
                NO_RAILROAD,
                threading.Event(),
                throttle_silence_s=quiet_s,
            )
    finally:
        bus.close()


if __name__ == "__main__":
    main()
