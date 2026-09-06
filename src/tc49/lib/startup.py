"""The shape every app's process comes up in: its order, its waits, and its
numbers.

Every app comes up alone (ADR-0059, decision 5), and coming up is the same
three steps whichever app it is. Six command lines written one after another
said all of that six times over, byte for byte, and two of them had already
drifted (#430); six docstrings then stated the order again in their own
words, so a reader had no one place to learn it and a change to it had six
places to miss (#440). **The order is stated here.** It is settled, and it is
what the code does (#432):

1. **The documents, first and blocking.** An app with no layout has nothing
   to do, and the store is the thing most likely not to be up yet. The retry
   and what it says on stderr are `lib/documents.py`'s.
2. **The broker**, waited for the same way (`connected` below), because a
   publish made to a broker that is not there is dropped rather than queued
   (ADR-0050) — and what an app publishes first are its opening rows, so the
   wait comes before them.
3. **The rows this app already owns**, if the broker is holding any
   (`retained` below), and then the loop. A row a process of its own left
   behind is what an app restarted under a running railroad adopts rather
   than coming up as if the railroad were new (#123).

An app's `__main__` says only where it differs from this: `driver` and
`dccex` read no documents, `layout` answers the picker rather than following
the row, and `simulator` has no rows of a previous process to adopt.

Here rather than in an app, for the reason `lib.mqtt.address` is here: an app
imports `lib` and itself and never another app (ADR-0013), so `lib` is the
only place a shape six of them share can live. Beside `loading.py` rather
than inside it — what an app does when the railroad moves under it is that
module's whole subject, and the way in is this one's.

**Not every wait that looks alike is here, and the reason they differ is.**
`retained` below names the row it is waiting for and comes back the instant
that row lands. An app whose rows are keyed by address holds no list of which
addresses a railroad has, so there is nothing for it to name: a broker holding
nothing and a broker still sending look alike from there, and the only way to
have the whole picture is to wait the window out whole. That is a difference
in behaviour and it has an app's own `_retained` — `layout`, waiting out the
traction rows a previous process left, and `dccex`, waiting out the desired
picture before it opens a link those values could go out over. Each of those
says what it is waiting for and why a second is worth spending on it; why a
wait with nothing to name lasts the whole window is written here, once (#456).
"""

import argparse
import threading
import time
from collections.abc import Callable

from tc49.lib.bus import Payload
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus

PERIOD_S = 0.1
"""Seconds between turns of an app's loop, which for most of them is a drain.
The railroad's own pacing is elsewhere entirely — this only bounds how long
what arrives sits in the queue the client's network thread fills before the
app's own thread delivers it, so it stays small. An app whose loop has
something to be early for waits less: the simulator cuts a turn short to the
next scheduled event, and the layout interface reads a settled level at this
resolution."""

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person
watching the container is told, and how long a signal takes to be noticed
while the broker is missing."""

RETAINED_S = 1.0
"""How long the broker is given to hand over the rows an app owns. A bound and
not a promise: the broker sends a retained value as the subscription lands,
and a broker holding none would otherwise be waited for forever. Overrunning
it is a cold start, which is what a railroad with no such row is."""

TICK_S = 0.01
"""How often the wait below looks for a row that has landed. Nothing announces
one — the client's network thread puts a retained value in `last_values` and
`drain` is what delivers it to a handler later — so a wait for a named row
looks rather than being woken, and the looking is what this paces."""


def connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. An app whose broker is missing has nowhere to publish and nothing
    to read, so there is nothing else for it to be doing meanwhile.

    `False` only where `stop` was set, which is the caller being ended before
    its opening rows were ever published.
    """
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False


def retained(
    bus: MqttBus, topic: str, stop: threading.Event, timeout_s: float = RETAINED_S
) -> None:
    """Subscribe, and come back once the broker has handed over what it holds
    on `topic` — or once it is clear it holds nothing.

    What an app reads out of `last_values` as it is constructed: the row a
    process of its own left behind, which is what an app restarted under a
    running railroad adopts rather than coming up as if the railroad were new
    (#123). On the in-process binding a retained value is there synchronously;
    on a broker it arrives moments after the subscription does, so the wait is
    here, in the thing that assembles the app, and no app code learns which
    binding it got.

    **Waited on `stop`**, which is the rule `dropped` states and this keeps:
    a signal arriving inside the window ends the process rather than being sat
    on for the rest of it. The row is looked for a tick at a time because
    nothing wakes a waiter when one lands, and a stop ends the wait between
    two of those looks.

    The value is read here only in the sense of being waited for; reading it
    is the app's, through `lib.payload` like every payload, and the handler
    below does nothing with what it is given.
    """
    bus.subscribe(topic, _nothing)
    deadline = time.monotonic() + timeout_s
    while topic not in bus.last_values:
        left = deadline - time.monotonic()
        if left <= 0 or stop.wait(min(TICK_S, left)):
            return


def _nothing(topic: str, payload: Payload) -> None:
    """What a row is subscribed with while it is being waited for. Nothing
    reads it here: the app is built afterwards and reads the value itself."""


def command_line(
    prog: str, description: str, railroad: bool = True, store: bool = True
) -> argparse.ArgumentParser:
    """The flags a compose service passes an app: where the broker is, which
    railroad it runs, and where the store serves the documents that railroad
    is built from.

    **All six start here**, and the two arguments say which of the three an
    app takes rather than which apps write a parser of their own. Every app
    is given a broker, having nowhere to publish and nothing to read without
    one. `railroad=False` is the translator's, which is told about no
    railroad at all — hardware needs no layout, and an address is the string
    the hardware answers to rather than something looked up (ADR-0059,
    decisions 5 and 6). `store=False` is the driver's as well, which reads no
    documents (SYSTEM.md, driver footprint). What an app adds on top of what
    it is handed here — a station, a startup file, an id — it adds to the
    parser this returns.

    Taking fewer flags was what let two apps declare their own and drift from
    the words here while a commit said six of them shared these (#430, #456).
    An app's own flags are a difference; `--broker` spelled out a second time
    is a repetition.

    A period is not a flag anywhere: nothing outside a process has an opinion
    about how often it takes what the broker's network thread left waiting.
    """
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument(
        "--broker",
        required=True,
        metavar="HOST:PORT",
        help=f"the broker to run on, e.g. {BROKER_EXAMPLE}",
    )
    if railroad:
        parser.add_argument(
            "--railroad",
            required=True,
            help="the railroad this broker runs, as the store lists it",
        )
    if store:
        parser.add_argument(
            "--store",
            required=True,
            metavar="URL",
            help="where the store serves the documents, e.g."
            " http://127.0.0.1:8765; waited for until it answers",
        )
    return parser
