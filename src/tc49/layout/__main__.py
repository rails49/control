"""`python -m tc49.layout` — the layout interface as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with no store and no other app running, this connects, waits for the
store, publishes its own retained rows and stays up; it exits on nothing but a
signal. Nothing here is ordered by anything else coming up first, which is why
compose carries no `depends_on`.

Three flags, the ones a compose service passes: where the broker is, which
railroad it runs, and where the store serves the documents that railroad is
built from. Neither the drain period nor the settling time is one of them —
nothing outside this process has an opinion about how often it takes what the
broker's network thread left waiting, and what a settling time is worth is a
fact about the detectors a railroad has, which is `LayoutInterface`'s argument
and the suite's to drive (ADR-0030).

The startup order is what a cold start needs:

1. **The documents**, first and blocking, because an app with no layout has
   nothing to do and the store is the thing most likely not to be up yet. Two
   of them here, the layout and the roster: the transits a `move` may name and
   the signal at each block end come off the one, and the addresses that
   answer for a train off the other, no address ever reaching a command
   (#199). The retry and what it says on stderr are `lib/documents.py`'s.
2. **The broker**, waited for the same way, because a publish made to a broker
   that is not there is dropped rather than queued (ADR-0050) — and this app's
   opening rows are the railroad coming up dark and at rest.
3. **The traction rows a previous process left**, if the broker is holding
   any. On the in-process binding they were in `last_values` synchronously and
   the constructor zeroed them as it ran; on a broker they arrive moments after
   the subscription does, so the wait is here, in the thing that assembles the
   app, and no app code learns which binding it got.

Then the loop, which is this app's own and not the drain the other apps run:
advance the clock to wall time, `settle()`, drain, once per period. It moves
here out of `bench/runner.py`, whose physical branch paced this app in one
process. Nothing schedules `settle()` — a detector publishes a level *change*
and nothing else, so a process that never called it would sit on a quiet
railroad holding an arrival nobody was told about — and the period bounds the
resolution and nothing else: 0.1 s against 300 ms of settling has a settled
level acted on between 0.3 s and 0.4 s after it stood, which is the right
order for a detector.

`LayoutInterface` is handed a `Bus` and nothing else in the package changes.
The clock is this process's own: the run clock is read here and advanced
nowhere else, the steel keeping its own time (ADR-0009, ADR-0047), and the
processes on a broker share no clock at all — the stamps on the wire come off
wall time in the binding (ADR-0059, decision 1).
"""

import argparse
import contextlib
import signal
import sys
import threading
import time
from collections.abc import Callable

from tc49.layout.interface import WANTED_TRACTION, LayoutInterface
from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address

CLIENT_ID = "tc49-layout"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

PERIOD_S = 0.1
"""Seconds between turns of the loop. It bounds two things at once — how long
a command sits in the queue the client's network thread fills before this
thread delivers it, and how finely a settled level is noticed — so it stays
small."""

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person
watching the container is told, and how long a signal takes to be noticed
while the broker is missing."""

RETAINED_S = 1.0
"""How long the rows this app owns are waited for on the way up. A bound and
not a promise: the broker sends a retained value as the subscription lands,
and a broker holding none would otherwise be waited for forever."""

TRACTION = f"{WANTED_TRACTION}/#"
"""Every traction row, which is what has to be on the broker's way here before
the app is built on it. A filter and not a topic: a row exists for each
address a previous process wrote to, and this app holds no list of which."""


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
) -> None:
    """The app: its documents, its rows, and its loop.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in any of the waits above it — and `main`
    lets that out.

    The clock starts here and at zero, and every turn puts it where wall time
    is. Seconds since this process started, which is what a settling time is
    measured in and the only thing that reads it; nothing on the bus carries
    it, so a restart resetting it is news to nobody (ADR-0009).
    """
    layout = documents.layout(railroad)
    roster = documents.roster(railroad)
    log(f"'{railroad}': {len(layout.blocks)} blocks, {len(roster.trains)} trains")
    if not _connected(bus, stop, log):
        return
    _retained(bus, stop)
    clock = Clock()
    app = LayoutInterface(bus, layout, roster, clock)
    log(f"up on '{railroad}', draining every {period_s}s")
    started = time.monotonic()
    while not stop.is_set():
        clock.advance(time.monotonic() - started)
        app.settle()
        bus.drain()
        stop.wait(period_s)


def _connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. An app whose broker is missing has nowhere to publish and nothing
    to read, so there is nothing else for it to be doing meanwhile."""
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False


def _retained(
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

    The window is waited out **whole**, where every other app waits for one
    named row and comes back the instant it lands. There is nothing to key on:
    a row exists for each address a previous process wrote to and this app
    holds no list of which, so an empty broker and a broker still sending look
    alike from here. A second on the way up, once, against a locomotive that
    would otherwise take itself away.

    The value is read here only in the sense of being waited for; reading it is
    the app's, and this handler does nothing with what it is given.
    """
    bus.subscribe(TRACTION, lambda _topic, _payload: None)
    stop.wait(timeout_s)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.layout",
        description="Run the layout interface against a broker: the one writer"
        " of what the hardware is asked to do.",
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
