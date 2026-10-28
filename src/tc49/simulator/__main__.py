"""`python -m tc49.simulator` — the simulator as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with no store and no other app running, this connects, waits for the
store, publishes its own retained rows and stays up; it exits on nothing but a
signal. Nothing here is ordered by anything else coming up first, which is why
compose carries no `depends_on`.

A box with no hardware runs this container **in place of** `layout`, not
beside it: a run has one binding of the layout interface and neither knows the
other exists (ADR-0030), so which one a box starts is the only difference
between a simulated railroad and steel, and nothing above them can tell.

Two flags, the ones a compose service passes: where the broker is, and where
the store serves the drawing the railroad derives from. **The record first**,
as `layout` reads it: the store says which railroad was loaded last
(`/loaded`), this binding starts on that one — nothing on the command line
names a railroad, and a box that records none stands — and each railroad it
is built on is written back to the record before the build (ADR-0072,
decision 5). **The drawing and the clock, and no roster**, where
`layout` reads a roster as well: an address is what a roster answers with and
this binding sends no command to anything, so the track alone is what it
stands in for. The clock is the railroad's start time and speed-up,
`layouts/<layout>.clock.yaml`, read and kept as `layout` reads and keeps it
(`lib/clock_row.py`), and the fast clock it starts is said off the run clock
(ADR-0090). Neither the drain
period nor the two delays is a flag — nothing outside this process has an
opinion about how often it takes what the broker's network thread left
waiting, and what a transit costs is this binding's own stand-in for travel
time rather than a number a person restarts a container to change (ADR-0030).

The startup order is `lib/startup.py`'s, and its third step is empty here:
**no rows of a previous process to adopt, and no steel standing before it.**
Retained state lives in the broker and nowhere else (ADR-0059, decision 3),
which leaves this binding's placement file — the steel's own memory, on no
topic and in no inventory (ADR-0030) — with nowhere to live in a container, so
the process is given none. A simulator restarted under a running railroad
therefore comes up with an empty layout while the dispatcher comes up with the
picture it left on the broker, and the two disagree until a hand places the
trains again: `train_placed` is an event, so the broker holds none to replay.
What that costs is a `move` for a train this process is not holding, which is
dropped for the same reason a stale one is — the train is not standing at the
transit's near end (ADR-0047) — and never a train invented under a command.
Decision 3 answers #123 for every row the broker holds; this one is on no
topic by ADR-0030, so where the steel's memory lives in a container is open,
and not this command line's to invent. A **rebuild** is not a restart: the
process is still holding its steel, and under the same railroad name it hands
that to the next build, less any train whose block the new drawing lacks
(ADR-0071). A railroad the store does not have
leaves it **standing** — up, naming no railroad (`""`) on
`tc49/layout/state/railroad`, built on the first one a person picks that the
store can give (#564, #727, `lib/loading.py`). One whose drawing is not a
valid drawing stays named, with `built: false`, as in `layout` (ADR-0085).
Those steps, from the store's record to the rows cleared on a move, are
`rebuilding`'s, the loop both layout bindings run (`lib/loading.py`,
ADR-0086); what this file hands it is its own `_Binding`.

Then the loop, which is this app's own and older than its command line: the
discrete-event queue slept on a wall clock (`run_live`). Where every other
app's process writes a `while` of its own, this one hands `Simulator` its wait
and its stop and lets it run — the layout interface owns time (ADR-0009,
ADR-0047), and the run's pacing and the drain are one loop here rather than
two. The period caps a wait, so a command arriving while nothing is scheduled
is drained within it, and a wait already cut to the next scheduled event is
left alone: a sensor fires at the stamp a batch run would give it, which is
what makes a live run and a benchmark the same run.

`Simulator` is handed a `Bus` and nothing else in the package changes: which
binding it got is this file's business, and a payload that cannot be read is
dropped exactly as it was in one process (#262, BUS.md rule 4) — under MQTT
whoever published it is another container, and a bug there must not take the
thing that watches the railroad down with it.
"""

import contextlib
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence

from tc49.lib.clock import Clock
from tc49.lib.clock_row import Keeping, kept_by, loaded
from tc49.lib.documents import Documents
from tc49.lib.fast_clock import KeptClock
from tc49.lib.layout import Layout
from tc49.lib.loading import NO_RAILROAD, Running, rebuilding
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.startup import PERIOD_S, RETAINED_S, Alive, command_line, connected
from tc49.simulator.sim import Simulator

CLIENT_ID = "tc49-simulator"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (BUS.md, rule 4)."""

TRANSIT_S = 30.0
CLEAR_S = 30.0
"""The two fixed delays a deployed simulator carries a train on: the head
reaching the far detector, then the tail clearing the near one. Stated here
rather than left to the constructor's defaults so that what a transit costs on
a running box is read off the process that runs it, and passed in rather than
flagged for ADR-0030's reason — a delay this binding chose is not a distance
divided by a speed, and the railroad it stands in for is the one thing that
could say otherwise. The suite shortens them, a test that waited out a real
transit spending half a minute on one move."""

ALIVE_CONFIRMED = "tc49/layout/alive_confirmed"
"""`layout`'s saying it is up, said by this binding in its place: a page names
the layout interface when it goes quiet, on a simulated railroad as on steel
(#1113). The devices that cut track power on it are on steel boxes only, so
saying it here cuts nothing (#716)."""

OWNED = (
    "tc49/layout/state/railroad",
    "tc49/layout/state/power",
    "tc49/layout/state/clock",
)
"""The retained rows this binding of the layout interface writes: which
railroad it is standing in for, the supply each answered press set, and the
fast clock. The block events it publishes as trains move are events and
carry no retained value to drop (ADR-0060)."""


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`documents:`, `mqtt:`)."""
    print(f"simulator: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    documents: Documents,
    railroad: str,
    stop: threading.Event,
    period_s: float = PERIOD_S,
    transit_s: float = TRANSIT_S,
    clear_s: float = CLEAR_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """The app: the broker, then the rebuild loop both layout bindings run
    (`lib/loading.py`, ADR-0086), handed this one's `_Binding`.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in either wait above it — and `main`
    lets that out.

    The gesture waits for `off` here as it does in `layout`: this binding
    answers the band's power presses as that one does and comes up `off`, so
    a railroad is picked before a person presses ON or after OFF (ADR-0070).
    """
    if not connected(bus, stop, log):
        return
    binding = _Binding(bus, documents, stop, period_s, transit_s, clear_s, log)
    rebuilding(bus, documents, railroad, stop, binding, log, period_s, RETAINED_S)


type _Read = tuple[Layout, KeptClock | None]
"""What a railroad is simulated from: its layout, and the clock it keeps,
None where it keeps none."""


class _Binding:
    """What this binding hands the rebuild loop: two documents read, the
    drawing and the clock, and a `Simulator` built on them. This binding's
    steel is the drawing it was built from, so another railroad is another
    simulator (ADR-0030)."""

    owned: Sequence[str] = OWNED

    def __init__(
        self,
        bus: MqttBus,
        documents: Documents,
        stop: threading.Event,
        period_s: float,
        transit_s: float,
        clear_s: float,
        log: Callable[[str], None],
    ) -> None:
        self._bus = bus
        self._stop = stop
        self._period_s = period_s
        self._transit_s = transit_s
        self._clear_s = clear_s
        self._documents = documents
        self._log = log
        self._keeping = Keeping(documents, log)
        # Kept across builds, so the rate holds over a reload (#1113).
        self._alive = Alive(bus, ALIVE_CONFIRMED)

    def read(self, railroad: str) -> _Read:
        """The drawing and the clock the railroad keeps: this binding sends
        no command, so it reads no roster."""
        return (
            self._documents.layout(railroad),
            kept_by(self._documents, railroad, self._log),
        )

    def nothing(self, railroad: str) -> _Read:
        """What this binding stands in for where `railroad`'s drawing is not
        a valid drawing and there is no build to keep: no track under its
        name, the layout interface's own answer (ADR-0085, decision 4). Its
        clock is the railroad's all the same."""
        return (
            Layout(railroad, {}, {}, frozenset(), {}),
            kept_by(self._documents, railroad, self._log),
        )

    def layout(self, read: _Read) -> Layout:
        return read[0]

    def build(self, read: _Read, position: dict[str, str], built: bool) -> Running:
        """The simulator on its own clock, starting at zero, which `run_live`
        is the only thing to advance. The steel stands where it stood under
        the same name, a train longer than its block included: that is where
        the steel has it (ADR-0071).

        The fast clock is started as `layout` starts it, at the start time and
        speed-up the railroad keeps or at the box's time of day at 1, and run
        on the run clock from there; what a person sets is kept with the
        railroad as `layout` keeps it (ADR-0090)."""
        layout, kept = read
        clock = Clock()

        def keep(changed: KeptClock) -> None:
            self._keeping.keep(layout.name, changed)

        fast = loaded(self._bus, kept, lambda: clock.now, time.localtime(), keep)
        simulator = Simulator(
            self._bus,
            layout,
            clock,
            position,
            transit_s=self._transit_s,
            clear_s=self._clear_s,
            built=built,
            fast=fast,
        )
        return _Running(simulator, self._alive, self._stop, self._period_s)


class _Running:
    """A built `Simulator` and the loop it already owns: the discrete-event
    queue slept on a wall clock, ended by a signal or by `until`, saying it is
    up on each wait a second after the last (#1113)."""

    def __init__(
        self,
        simulator: Simulator,
        alive: Alive,
        stop: threading.Event,
        period_s: float,
    ) -> None:
        self._simulator = simulator
        self._alive = alive
        self._stop = stop
        self._period_s = period_s

    @property
    def position(self) -> dict[str, str]:
        return self._simulator.position

    def run(self, until: Callable[[], bool]) -> None:
        self._simulator.run_live(
            self._period_s,
            sleep=_waiting(self._stop, self._alive),
            stop=until,
            monotonic=time.monotonic,
        )


def _waiting(stop: threading.Event, alive: Alive) -> Callable[[float], None]:
    """The loop's wait: a sleep a stop cuts short, which is what the other
    apps get from `stop.wait(period_s)` at the foot of their own loops, and
    `alive_confirmed` said before it where a second has passed. A wait is
    never longer than the period, so the beat keeps to the second.

    The deployment sets `stop` never, so a wait here runs its whole length
    there; the suite sets it, and a turn waiting out a transit would otherwise
    hold the process open for the rest of that transit after the test had
    finished with it.
    """

    def wait(seconds: float) -> None:
        alive.say()
        stop.wait(seconds)

    return wait


def main() -> None:
    parser = command_line(
        prog="python -m tc49.simulator",
        description="Run the simulator against a broker: the second"
        " binding of the layout interface, standing in for the steel.",
    )
    args = parser.parse_args()
    try:
        host, port = address(args.broker)
    except ValueError as refused:
        parser.error(str(refused))
    # A signal is what ends this app, and SIGTERM is the one a container is
    # stopped with: given SIGINT's own handler it raises where the process
    # stands, so a wait for a store that never comes up ends on it too.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    to_stderr(f"broker {host}:{port}, store {args.store}")
    bus = MqttBus(host, port, client_id=CLIENT_ID)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            serve(bus, Documents(args.store), NO_RAILROAD, threading.Event())
    finally:
        bus.close()


if __name__ == "__main__":
    main()
