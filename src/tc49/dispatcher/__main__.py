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

The startup order is `lib/startup.py`'s, stated there with its reason. Two
documents here, the layout and the roster: the roster is the whole of what the
dispatcher knows about stock, and being on it is what makes a train **known**
(ADR-0039). The row this app adopts is the picture it already owns, waited for
there and ended by the row landing or by a stop; missing it would lose the hold
that picture imposes — a restored session comes up held whatever the steel has
been doing meanwhile.

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

import contextlib
import signal
import sys
import threading
from collections.abc import Callable

from tc49.dispatcher.dispatch import ALLOCATION, Dispatcher
from tc49.dispatcher.locking import Incremental
from tc49.lib.documents import Documents
from tc49.lib.layout import Layout
from tc49.lib.loading import Loaded, dropped
from tc49.lib.mqtt import MqttBus, address
from tc49.lib.roster import Roster
from tc49.lib.startup import (
    PERIOD_S,
    RETAINED_S,
    command_line,
    connected,
    retained,
)

CLIENT_ID = "tc49-dispatcher"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""

OWNED = ("tc49/dispatch/state/#",)
"""The retained rows this app writes, as a filter rather than a list: a topic
has one writing role (ADR-0035), so what the broker holds under this is this
app's whatever wrote it, and a reload drops the lot before rebuilding
(ADR-0060). Everything else under `tc49/dispatch/` is an event and carries no
retained value to drop."""

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
    done again — including the placement, which is nobody's: the new railroad
    comes up empty and the trains are put on it by hand.
    """
    loaded = Loaded(railroad)
    layout, roster = _documents(documents, loaded.name)
    log(f"'{loaded.name}': {len(layout.blocks)} blocks, {len(roster.trains)} trains")
    if not connected(bus, stop, log):
        return
    while not stop.is_set():
        retained(bus, ALLOCATION, stop, retained_s)
        # No placement: a run an operator drives comes up with an empty layout
        # and held, and every train arrives as a gesture (ADR-0039). Locking is
        # **incremental**, which is what the panel's two colours mean — green
        # creeping along a cyan path, and its length saying how far the train
        # may go (#165, ui/PANEL.md). Claiming a whole route up front is a
        # measurement baseline, not the behaviour to hand an operator on a
        # shared railroad.
        Dispatcher(bus, layout, roster, {}, Incremental(layout, ROUTES))
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
        layout, roster = _loading(documents, loaded, built, log)
        gone = dropped(bus, OWNED, stop, retained_s)
        log(f"loading '{loaded.name}': {len(gone)} rows of '{built}' cleared")


def _documents(documents: Documents, railroad: str) -> tuple[Layout, Roster]:
    """The pair a dispatcher is built from: the railroad's topology and the
    stock that runs on it."""
    return documents.layout(railroad), documents.roster(railroad)


def _loading(
    documents: Documents, loaded: Loaded, built: str, log: Callable[[str], None]
) -> tuple[Layout, Roster]:
    """The railroad just named, or the one still running where the store has
    no such railroad or its documents do not load. A store that is not
    answering is waited for rather than refused, which is `lib/documents.py`'s
    own retry and not a case here (ADR-0050)."""
    try:
        return _documents(documents, loaded.name)
    except (OSError, ValueError, TypeError) as refused:
        log(f"'{loaded.name}': {refused} — staying on '{built}'")
        loaded.keep(built)
        return _documents(documents, built)


def main() -> None:
    parser = command_line(
        prog="python -m tc49.dispatcher",
        description="Run the dispatcher against a broker: the one grantor of"
        " moves, and the holder of the run's picture.",
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
