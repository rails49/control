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

Three flags, the ones a compose service passes: where the broker is, which
railroad it runs, and where the store serves the drawing that railroad derives
from. **One document and not two**, where `layout` reads a roster as well: an
address is what a roster answers with and this binding sends no command to
anything, so the track alone is what it stands in for. Neither the drain
period nor the two delays is a flag — nothing outside this process has an
opinion about how often it takes what the broker's network thread left
waiting, and what a transit costs is this binding's own stand-in for travel
time rather than a number a person restarts a container to change (ADR-0030).

The startup order is what a cold start needs:

1. **The document**, first and blocking, because an app with no layout has
   nothing to do and the store is the thing most likely not to be up yet. The
   retry and what it says on stderr are `lib/documents.py`'s.
2. **The broker**, waited for the same way, because a publish made to a broker
   that is not there is dropped rather than queued (ADR-0050) — and the two
   rows the constructor states, which railroad this is and that the track is
   live, are this app's opening ones.
3. **No rows of a previous process to adopt, and no steel standing before it.**
   Retained state lives in the broker and nowhere else (ADR-0059, decision 3),
   which leaves this binding's placement file — the steel's own memory, on no
   topic and in no inventory (ADR-0030) — with nowhere to live in a container,
   so the process is given none. A simulator restarted under a running
   railroad therefore comes up with an empty layout while the dispatcher comes
   up with the picture it left on the broker, and the two disagree until a
   hand places the trains again: `train_placed` is an event, so the broker
   holds none to replay. What that costs is a `move` for a train this process
   is not holding, which is dropped for the same reason a stale one is — the
   train is not standing at the transit's near end (ADR-0047) — and never a
   train invented under a command. Decision 3 answers #123 for every row the
   broker holds; this one is on no topic by ADR-0030, so where the steel's
   memory lives in a container is open, and not this command line's to
   invent.

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
dropped exactly as it was in one process (#262, SYSTEM.md rule 4) — under MQTT
whoever published it is another container, and a bug there must not take the
thing that watches the railroad down with it.
"""

import contextlib
import signal
import sys
import threading
from collections.abc import Callable

from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.layout import Layout
from tc49.lib.loading import Answering, dropped
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.startup import PERIOD_S, RETAINED_S, command_line, connected
from tc49.simulator.sim import Simulator

CLIENT_ID = "tc49-simulator"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

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

OWNED = ("tc49/layout/state/railroad", "tc49/layout/state/power")
"""The retained rows this binding of the layout interface writes: which
railroad it is standing in for, and a supply that is live because simulated
rails always are. The block events it publishes as trains move are events and
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
    """The app: its document, its rows, and the loop it already owns.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in either wait above it — and `main`
    lets that out.

    The clock starts here and at zero, and `run_live` is the only thing that
    advances it: seconds since this process started, which is what the two
    delays are measured in. Nothing on the bus carries it — the stamps on the
    wire come off wall time in the binding (ADR-0059, decision 1) — so a
    restart resetting it is news to nobody (ADR-0009).
    """
    # No precondition, because this binding drives no hardware: the power row
    # it publishes is a constant `on` — a power cut is a physical act ADR-0030
    # keeps out of the simulation — so a gesture waiting for `off` here would
    # wait for ever. There is no steel that could disagree with the drawing
    # just loaded, so there is nothing for a person to confirm (ADR-0060 as
    # amended).
    loaded = Answering(railroad, precondition=None)
    layout = documents.layout(loaded.name)
    log(f"'{loaded.name}': {len(layout.blocks)} blocks")
    if not connected(bus, stop, log):
        return
    while not stop.is_set():
        # Before the app's opening rows and not after, where the five apps
        # that follow the state row subscribe afterwards: what this one
        # watches is a **gesture**, and an event is not retained, so a press
        # landing in the instant between the rows and the subscription would
        # simply be gone (ADR-0059, decision 5). It also picks up the supply
        # this app is about to state, which is the precondition on the
        # gesture — and simulated rails are always live, so what this
        # binding hears is `on` and the gesture is refused. A power cut is a
        # physical act, and simulating one would be the branch ADR-0030
        # keeps out of every app (ADR-0060).
        loaded.follow(bus)
        clock = Clock()
        simulator = Simulator(bus, layout, clock, transit_s=transit_s, clear_s=clear_s)
        built = loaded.name
        log(f"up on '{built}', waiting at most {period_s}s a turn")
        # The loop the app already owns, ended by a signal or by the railroad
        # moving under it — this binding's steel is the drawing it was built
        # from, so another railroad is another simulator (ADR-0030).
        simulator.run_live(
            period_s,
            sleep=_waiting(stop),
            stop=lambda: stop.is_set() or loaded.moved,
        )
        if not loaded.moved:
            return
        layout = _loading(documents, loaded, built, log)
        gone = dropped(bus, OWNED, stop, RETAINED_S)
        log(f"loading '{loaded.name}': {len(gone)} rows of '{built}' cleared")


def _loading(
    documents: Documents, loaded: Answering, built: str, log: Callable[[str], None]
) -> Layout:
    """The railroad just named, or the one still running where the store has
    no such railroad or its drawing does not derive. A store that is not
    answering is waited for rather than refused, which is `lib/documents.py`'s
    own retry and not a case here (ADR-0050)."""
    try:
        return documents.layout(loaded.name)
    except (OSError, ValueError, TypeError) as refused:
        log(f"'{loaded.name}': {refused} — staying on '{built}'")
        loaded.keep(built)
        return documents.layout(built)


def _waiting(stop: threading.Event) -> Callable[[float], None]:
    """The loop's wait: a sleep a stop cuts short, which is what the other
    apps get from `stop.wait(period_s)` at the foot of their own loops.

    The deployment sets `stop` never, so this is `time.sleep` there; the suite
    sets it, and a turn waiting out a transit would otherwise hold the process
    open for the rest of that transit after the test had finished with it.
    """

    def wait(seconds: float) -> None:
        stop.wait(seconds)

    return wait


def main() -> None:
    parser = command_line(
        prog="python -m tc49.simulator",
        description="Run the simulator against a broker: the milestone-1"
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
            serve(bus, Documents(args.store), args.railroad, threading.Event())
    finally:
        bus.close()


if __name__ == "__main__":
    main()
