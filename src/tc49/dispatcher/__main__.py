"""`python -m tc49.dispatcher` — the dispatcher as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with no store and no other app running, this connects, waits for the
store, publishes its own retained rows and stays up; it exits on nothing but a
signal. Nothing here is ordered by anything else coming up first, which is why
compose carries no `depends_on`.

Three flags, the ones a compose service passes: where the broker is, which
railroad it runs, and where the store serves the documents that railroad is
built from. Neither the drain period nor the route budget is one of them —
nothing outside this process has an opinion about how often it takes what the
broker's network thread left waiting, or about how many candidates a launch
tries, and `bench` is where a budget is a number somebody varies.

The startup order is what a cold start needs:

1. **The documents**, first and blocking, because an app with no layout has
   nothing to do and the store is the thing most likely not to be up yet. Two
   of them here, the layout and the roster: the roster is the whole of what
   the dispatcher knows about stock, and being on it is what makes a train
   **known** (ADR-0039). The retry and what it says on stderr are
   `lib/documents.py`'s.
2. **The broker**, waited for the same way, because a publish made to a broker
   that is not there is dropped rather than queued (ADR-0050) — and the rows
   below are this app's opening ones.
3. **The picture this app already owns**, if the broker is holding one. On the
   in-process binding a retained value is there synchronously and the
   dispatcher reads it as it is constructed (#123); on a broker it arrives
   moments after the subscription does, so the wait is here, in the thing that
   assembles the app, and no app code learns which binding it got.

What the layout says about the supply is *not* waited for: `state/power`
arrives on the dispatcher's own filter at the first drain, and the run comes
up **held** with nothing granted until a person releases it, so there is no
window in which the dispatcher could commit a move over rails it has not yet
heard about.

Then the loop, which is a drain and a sleep. `Dispatcher` is handed a `Bus`
and nothing else changes in the package: what a run an operator drives has is
a railroad and its roster, no placement and no timetable — the trains arrive
by gesture and a train nothing places comes up off the layout (ADR-0039,
ADR-0036).
"""

import argparse
import contextlib
import signal
import sys
import threading
import time
from collections.abc import Callable

from tc49.dispatcher.dispatch import ALLOCATION, Dispatcher
from tc49.dispatcher.locking import Incremental
from tc49.lib.documents import Documents
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address

CLIENT_ID = "tc49-dispatcher"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

PERIOD_S = 0.1
"""Seconds between drains. The railroad's own pacing is elsewhere entirely —
this only bounds how long a request or a sensor reading sits in the queue the
client's network thread fills before this thread delivers it, so it stays
small."""

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

ROUTES = 2
"""The candidate route budget a launch tries, `k` (DISPATCH.md). A constant
and not a flag: a deployed railroad has no reason to run on a different one,
and varying it is `bench`'s — its sweep is what a golden number is recorded
at."""


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`documents:`, `mqtt:`)."""
    print(f"dispatcher: {line}", file=sys.stderr, flush=True)


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
    happens to be — in the loop, or in either wait above it — and `main`
    lets that out.
    """
    layout = documents.layout(railroad)
    roster = documents.roster(railroad)
    log(f"'{railroad}': {len(layout.blocks)} blocks, {len(roster.trains)} trains")
    if not _connected(bus, stop, log):
        return
    _retained(bus, ALLOCATION)
    # No placement: a run an operator drives comes up with an empty layout and
    # held, and every train arrives as a gesture (ADR-0039). Locking is
    # **incremental**, which is what the panel's two colours mean — green
    # creeping along a cyan path, and its length saying how far the train may
    # go (#165, ui/PANEL.md). Claiming a whole route up front is a measurement
    # baseline, not the behaviour to hand an operator on a shared railroad.
    Dispatcher(bus, layout, roster, {}, Incremental(layout, ROUTES))
    log(f"up on '{railroad}', draining every {period_s}s")
    while not stop.is_set():
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


def _retained(bus: MqttBus, topic: str, timeout_s: float = RETAINED_S) -> None:
    """Subscribe, and come back once the broker has handed over what it holds
    on `topic` — or once it is clear it holds nothing.

    What `Dispatcher` reads out of `last_values` as it is constructed: the
    picture a process of its own left behind, which is where a restarted
    dispatcher finds its trains standing and what it was crossing, rather
    than coming up over a railroad it believes to be empty (#123). Missing it
    would also lose the hold that same picture imposes — a restored session
    comes up held whatever the steel has been doing meanwhile.

    The value is read here only in the sense of being waited for; reading it
    is the app's, through `restored` like every payload, and this handler
    does nothing with what it is given.
    """
    bus.subscribe(topic, lambda _topic, _payload: None)
    deadline = time.monotonic() + timeout_s
    while topic not in bus.last_values and time.monotonic() < deadline:
        time.sleep(0.01)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.dispatcher",
        description="Run the dispatcher against a broker: the one grantor of"
        " moves, and the holder of the run's picture.",
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
