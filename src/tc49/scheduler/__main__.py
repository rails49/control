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

The startup order is `lib/startup.py`'s, and this app runs all three of its
steps with nothing of its own to add: one document, the layout, and one row it
already owns, the facing (`tc49/schedule/state/facing`).

Then the loop, which is a drain and a sleep. `Scheduler` is handed a `Bus` and
nothing else changes in the package: what a run an operator drives has is a
railroad and a person placing trains on it — no facing seed and no timetable,
those being the harness's (ADR-0036).
"""

import contextlib
import signal
import sys
import threading
from collections.abc import Callable

from tc49.lib.documents import Documents
from tc49.lib.layout import Layout
from tc49.lib.loading import Loaded, dropped
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.startup import (
    PERIOD_S,
    RETAINED_S,
    command_line,
    connected,
    retained,
)
from tc49.scheduler.scheduler import FACING, Scheduler

CLIENT_ID = "tc49-scheduler"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

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
    retained_s: float = RETAINED_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """The app: its documents, its rows, its loop, and the railroad it runs.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in either wait above it — and `main`
    lets that out. It ends the waits too: `retained_s` is a moment given to
    the broker and not one to sit through, so a stop set inside it is acted
    on where it lands (`lib/startup.py`).

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
    if not connected(bus, stop, log):
        return
    while not stop.is_set():
        retained(bus, FACING, stop, retained_s)
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
        gone = dropped(bus, OWNED, stop, retained_s)
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


def main() -> None:
    parser = command_line(
        prog="python -m tc49.scheduler",
        description="Run the scheduler against a broker: the one writer of"
        " requests, and the holder of facing.",
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
