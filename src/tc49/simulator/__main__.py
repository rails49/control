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

import argparse
import contextlib
import signal
import sys
import threading
from collections.abc import Callable

from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address
from tc49.simulator.sim import Simulator

CLIENT_ID = "tc49-simulator"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

PERIOD_S = 0.1
"""Seconds a wait lasts when nothing is scheduled. It bounds how long a
command sits in the queue the client's network thread fills before this thread
delivers it, and nothing else: a wait with an event ahead of it is cut to that
event instead, so the railroad's own pacing is the queue's and not this
number's."""

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

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person
watching the container is told, and how long a signal takes to be noticed
while the broker is missing."""


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
    layout = documents.layout(railroad)
    log(f"'{railroad}': {len(layout.blocks)} blocks")
    if not _connected(bus, stop, log):
        return
    clock = Clock()
    simulator = Simulator(bus, layout, clock, transit_s=transit_s, clear_s=clear_s)
    log(f"up on '{railroad}', waiting at most {period_s}s a turn")
    simulator.run_live(period_s, sleep=_waiting(stop), stop=stop.is_set)


def _connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. An app whose broker is missing has nowhere to publish and nothing
    to read, so there is nothing else for it to be doing meanwhile."""
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False


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
    parser = argparse.ArgumentParser(
        prog="python -m tc49.simulator",
        description="Run the simulator against a broker: the milestone-1"
        " binding of the layout interface, standing in for the steel.",
    )
    parser.add_argument(
        "--broker",
        required=True,
        metavar="HOST:PORT",
        help=f"the broker to run on, e.g. {BROKER_EXAMPLE}",
    )
    parser.add_argument(
        "--railroad",
        required=True,
        help="the railroad this broker runs, as the store lists it",
    )
    parser.add_argument(
        "--store",
        required=True,
        metavar="URL",
        help="where the store serves the documents, e.g. http://127.0.0.1:8765;"
        " waited for until it answers",
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
