"""The shape every app's process comes up in: its waits, and its numbers.

Every app comes up alone (ADR-0059, decision 5), and coming up is the same
few steps whichever app it is — wait for the broker, because a publish made
to a broker that is not there is dropped rather than queued (ADR-0050); give
that broker its moment to hand back the row this app already owns; then the
loop. Six command lines written one after another said all of that six times
over, byte for byte, and two of them had already drifted (#430).

Here rather than in an app, for the reason `lib.mqtt.address` is here: an app
imports `lib` and itself and never another app (ADR-0013), so `lib` is the
only place a shape six of them share can live. Beside `loading.py` rather
than inside it — what an app does when the railroad moves under it is that
module's whole subject, and the way in is this one's.

**Not every wait that looks alike is here.** A binding holding no list of the
addresses to key on waits its window out whole and cannot come back the
instant a row lands, an empty broker and a broker still sending looking alike
from there (`layout`, `dccex`). That is a difference in behaviour, and it
stays written where it happens.
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


def command_line(prog: str, description: str) -> argparse.ArgumentParser:
    """The three flags a compose service passes an app that reads documents:
    where the broker is, which railroad it runs, and where the store serves
    the documents that railroad is built from.

    Four of the six take exactly these and differed only in `prog` and
    `description`. The other two build their own, their flags being a
    difference and not a repetition: the driver reads no documents and so
    takes no `--store` (SYSTEM.md, driver footprint), and the translator is
    told about no railroad at all — hardware needs no layout — and takes the
    station it speaks to instead (ADR-0059, decisions 5 and 6).

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
    return parser
