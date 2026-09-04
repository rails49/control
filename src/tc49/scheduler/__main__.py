"""`python -m tc49.scheduler` — the scheduler as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with no store and no other app running, this connects, waits for the
store, publishes its own retained rows and stays up; it exits on nothing but a
signal. Nothing here is ordered by anything else coming up first, which is why
compose carries no `depends_on`.

Three flags, the ones a compose service passes: where the broker is, which
railroad it runs, and where the store serves the documents that railroad is
built from. The drain period is not one of them — nothing outside this process
has an opinion about how often it takes what the broker's network thread left
waiting, and it is short enough that a person's gesture is acted on in the
same tenth of a second whoever started the container.

The startup order is what a cold start needs:

1. **The documents**, first and blocking, because an app with no layout has
   nothing to do and the store is the thing most likely not to be up yet. The
   retry and what it says on stderr are `lib/documents.py`'s.
2. **The broker**, waited for the same way, because a publish made to a broker
   that is not there is dropped rather than queued (ADR-0050) — and the rows
   below are this app's opening ones.
3. **The facing this app already owns**, if the broker is holding one. On the
   in-process binding a retained value is there synchronously and the
   scheduler reads it as it is constructed (#123); on a broker it arrives
   moments after the subscription does, so the wait is here, in the thing that
   assembles the app, and no app code learns which binding it got.

Then the loop, which is a drain and a sleep. `Scheduler` is handed a `Bus` and
nothing else changes in the package: what a run an operator drives has is a
railroad and a person placing trains on it — no facing seed and no timetable,
those being the harness's (ADR-0036).
"""

import argparse
import contextlib
import signal
import sys
import threading
import time
from collections.abc import Callable

from tc49.lib.documents import Documents
from tc49.lib.layout import Layout
from tc49.lib.loading import Loaded, dropped
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address
from tc49.scheduler.scheduler import FACING, Scheduler

CLIENT_ID = "tc49-scheduler"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

PERIOD_S = 0.1
"""Seconds between drains. The railroad's own pacing is elsewhere entirely —
this only bounds how long a gesture sits in the queue the client's network
thread fills before this thread delivers it, so it stays small."""

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person
watching the container is told, and how long a signal takes to be noticed
while the broker is missing."""

RETAINED_S = 1.0
"""How long the rows this app owns are waited for on the way up. A bound and
not a promise: the broker sends a retained value as the subscription lands,
and a broker holding none would otherwise be waited for forever. Overrunning
it is a cold start, which is what a railroad with no such row is."""

OWNED = ("tc49/schedule/state/#",)
"""The retained rows this app writes, as a filter rather than a list: a
topic has one writing role (ADR-0035), so what the broker holds under this is
this app's whatever wrote it, and a reload drops the lot before rebuilding
(ADR-0060). The gestures under `tc49/schedule/` are events and carry no
retained value to drop."""


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`documents:`, `mqtt:`)."""
    print(f"scheduler: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    documents: Documents,
    railroad: str,
    stop: threading.Event,
    period_s: float = PERIOD_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """The app: its documents, its rows, its loop, and the railroad it runs.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in either wait above it — and `main`
    lets that out.

    The outer loop is one railroad each time round. A railroad is loaded
    while the apps run (ADR-0060), so the row naming another one ends the
    inner loop, the subscriptions of the app built on the last one are
    forgotten, the rows it owns are cleared and the whole of the above is
    done again. A railroad the store cannot give is said and not taken: an
    app still running the last one is worth more than one running none
    (ADR-0050).
    """
    loaded = Loaded(railroad)
    layout = documents.layout(loaded.name)
    log(f"'{loaded.name}': {len(layout.blocks)} blocks")
    if not _connected(bus, stop, log):
        return
    while not stop.is_set():
        _retained(bus, FACING)
        Scheduler(bus, layout)
        # After the app is built and not before: the row is retained, so
        # subscribing here is handed whatever it holds, and nothing this app
        # does on the way up moves — a gesture published in the instant
        # between an app's opening rows and its own subscriptions is lost,
        # and that instant is not one to lengthen (ADR-0059, decision 5).
        loaded.follow(bus)
        built = loaded.name
        log(f"up on '{built}', draining every {period_s}s")
        while not stop.is_set() and not loaded.moved:
            bus.drain()
            stop.wait(period_s)
        if not loaded.moved:
            return
        layout = _loading(documents, loaded, built, log)
        gone = dropped(bus, OWNED, stop, RETAINED_S)
        log(f"loading '{loaded.name}': {len(gone)} rows of '{built}' cleared")


def _loading(
    documents: Documents, loaded: Loaded, built: str, log: Callable[[str], None]
) -> Layout:
    """The railroad just named, or the one still running where the store has
    no such railroad or its drawing does not derive. A store that is not
    answering is waited for rather than refused, which is `lib/documents.py`'s
    own retry and not a case here."""
    try:
        return documents.layout(loaded.name)
    except (OSError, ValueError, TypeError) as refused:
        log(f"'{loaded.name}': {refused} — staying on '{built}'")
        loaded.keep(built)
        return documents.layout(built)


def _connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. An app whose broker is missing has nowhere to publish and nothing
    to read, so there is nothing else for it to be doing meanwhile."""
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False


def _retained(bus: MqttBus, topic: str, timeout_s: float = RETAINED_S) -> None:
    """Subscribe, and come back once the broker has handed over what it holds
    on `topic` — or once it is clear it holds nothing.

    What `Scheduler` reads out of `last_values` as it is constructed: the
    facing a process of its own left behind, which is what a scheduler
    restarted under a running railroad adopts rather than dropping every
    train's direction arrow (#123). The value is read here only in the sense
    of being waited for; reading it is the app's, through `lib.payload` like
    every payload, and this handler does nothing with what it is given.
    """
    bus.subscribe(topic, lambda _topic, _payload: None)
    deadline = time.monotonic() + timeout_s
    while topic not in bus.last_values and time.monotonic() < deadline:
        time.sleep(0.01)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.scheduler",
        description="Run the scheduler against a broker: the one writer of"
        " requests, and the holder of facing.",
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
