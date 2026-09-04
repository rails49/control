"""`python -m tc49.dccex` — the translator as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with nothing else running and no command station on the other end of
the port, this connects, publishes its own two retained rows — the railroad
dark and the station unreached — and stays up, retrying the mirror on a
backoff of its own; it exits on nothing but a signal. Nothing here is ordered
by anything else coming up first, which is why compose carries no
`depends_on`.

**No railroad and no store.** Hardware needs no layout: this app reads the
wanted rows and writes what it observes, and it does not know that layouts
exist (ADR-0059, decision 5). Where the other five processes are told which
railroad they run, there is nothing here for the name to select — no document
is read, and an address is the string the hardware answers to rather than
something looked up (decision 6). So the flags are where the broker is, where
the mirror is, and the two values that are this deployment's rather than the
railroad's:

- `--station <host:port>`, the `dccex-usb` that serves the command station
  (docs/dccex_usb/README.md). Not the USB device: this app is one client of
  that port beside JMRI and the hand-held throttles.
- `--startup <file>`, the raw station commands sent on powering the rails —
  the per-district trip currents, in the station's own language, which is the
  one place those values appear (#217). Optional: a railroad with none comes
  up at whatever the firmware defaults to.
- `--id`, the name its link row is keyed by (#368, decision 7), defaulting to
  the package's. A value and not a contract: it appears in no drawing, no
  configuration and no list of ours, and it is a key only because one railroad
  may have several participants and the second's `up` would otherwise erase
  the first's `down`.

Neither the drain period nor the poll nor the backoff is a flag — nothing
outside this process has an opinion about how often it takes what the broker's
network thread left waiting, and what the station is asked and how often a
lost link is retried are the translator's own (translator.py).

**The id names the broker's client too**, `tc49-<id>`, where the other apps
name themselves after the package. This is the one app a railroad may run
twice — two stations, two translators, decision 7 — and two clients sharing
one client id take turns disconnecting each other on the broker for as long as
both are up.

The startup order is what a cold start needs, and it has no store in it:

1. **No documents.** An app that reads nothing cannot be brought up in the
   wrong order with respect to one that serves documents.
2. **The broker**, waited for, and then `DccEx` on it. The constructor states
   this app's two opening rows — `device/link/<id>: down` and a dark
   `device/track` carrying why — and a publish made to a broker that is not
   there is dropped rather than queued (ADR-0050), so the wait comes first.
3. **No rows of a previous process to adopt**, and none of this app's own to
   read back: the two it owns are stated by the constructor. What it does wait
   for is the *desired* picture, which is `layout`'s to write and the broker's
   to retain — and it is waited for **before the link is opened**, so that the
   whole of it is held when the first connection is handed it. That is what
   keeps the track row first: `_applied()` orders a connect's picture, where a
   value arriving over a link that is already up is acted on as it arrives, and
   a speed reaching the station ahead of the power is a locomotive that rolls
   the moment somebody makes the rails live (#333, ADR-0054). On the in-process
   binding the retained values were there synchronously; on a broker they
   arrive moments after the subscription, so the wait is here, in the thing
   that assembles the app, and no app code learns which binding it got.

Then the loop: `DccEx.run()` keeping the link, and a drain beside it.

**asyncio owns this process.** `DccEx._send` writes to an
`asyncio.StreamWriter` from inside a bus subscriber, so whichever thread
drains the bus is the thread that writes to the station. With the loop owning
the process every subscriber runs on the loop thread and that write is already
where it belongs; the MQTT client's callback only appends to a queue on its
own network thread, and the drain here is what hands those frames to the loop
(lib/mqtt.py). A daemon thread under a synchronous owner would mean
marshalling a cross-thread write that does not exist today.

The railroad is stood down before the process ends, on the signal as well as
on the stop: zero to every locomotive this app has commanded and then the
track off, because the station goes on running whatever it was last told and
an exit over a rolling locomotive leaves it rolling. It comes **before** the
link is let go — cancelling `DccEx.run` closes the writer, and zeros sent
after that have nowhere to go.

`DccEx` is handed a `Bus` and nothing else in the package changes: which
binding it got is this file's business, and a desired value that cannot be
read is dropped exactly as it was in one process (#289, SYSTEM.md rule 4) —
under MQTT whoever published it is another container, and a bug there must not
take the thing that drives the railroad down with it.
"""

import argparse
import asyncio
import contextlib
import signal
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from tc49.dccex.translator import (
    FIRST_BACKOFF_S,
    ID,
    MAX_BACKOFF_S,
    DccEx,
)
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address

CLIENT_PREFIX = "tc49-"
"""What this app calls itself to the broker, in front of its id, so the log
names a translator rather than a random string and two of them on one railroad
are two clients. Nothing in the contract reads it: a topic has one writing
role and no payload says who published (SYSTEM.md, rule 4)."""

STATION_EXAMPLE = "dccex-usb:2560"
"""What a station address looks like, for the help and for a refusal. The
`dccex-usb` mirror serves the command station on 2560 (docs/dccex_usb), and
the compose service of a box with a station plugged into it names that."""

PERIOD_S = 0.1
"""Seconds between drains. The railroad's own pacing is elsewhere entirely —
this only bounds how long a desired value sits in the queue the client's
network thread fills before the loop thread delivers it, and writes it to the
station — so it stays small."""

BROKER_S = 5.0
"""How long one wait for the broker lasts before it is said again. The wait is
resumed until the connection lands, so this is only how often a person
watching the container is told, and how long a signal takes to be noticed
while the broker is missing."""

RETAINED_S = 1.0
"""How long the desired rows are waited for before the link is opened. A bound
and not a promise: the broker sends a retained value as the subscription lands,
and a broker holding none would otherwise be waited for forever.

Waited out **whole**, where an app waiting for one named row comes back the
instant it lands. There is nothing to key on: a row exists for each address
`layout` has written to and this app holds no list of which, so an empty broker
and a broker still sending look alike from here. A second on the way up, once,
against a locomotive commanded ahead of the power it needs."""


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`mqtt:`), and the link to the station is said
    on the bus rather than here — `device/link` is where a participant that
    cannot reach its hardware reports it (ADR-0050)."""
    print(f"dccex: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    station: tuple[str, int],
    stop: threading.Event,
    startup: Path | None = None,
    id: str = ID,
    period_s: float = PERIOD_S,
    retained_s: float = RETAINED_S,
    first_backoff_s: float = FIRST_BACKOFF_S,
    max_backoff_s: float = MAX_BACKOFF_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """The app, and the asyncio loop it runs in.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in the wait above it — and `main` lets
    that out.

    The two backoffs are the translator's own and are here for the suite,
    which has a station appear on a port seconds after the app went looking
    for it and no reason to wait out a deployed retry to see it.
    """
    if not _connected(bus, stop, log):
        return
    host, port = station
    app = DccEx(
        bus,
        host,
        port,
        id=id,
        startup=startup,
        first_backoff_s=first_backoff_s,
        max_backoff_s=max_backoff_s,
    )
    _retained(bus, stop, retained_s)
    log(f"up as '{id}' on {host}:{port}, draining every {period_s}s")
    asyncio.run(_driving(app, bus, stop, period_s))


def _connected(bus: MqttBus, stop: threading.Event, log: Callable[[str], None]) -> bool:
    """Wait for the broker, saying so, until it is there or the caller has
    stopped. An app whose broker is missing has nowhere to publish and nothing
    to read, so there is nothing else for it to be doing meanwhile — the
    station is somewhere to write to and not somewhere to be told what to
    write."""
    while not stop.is_set():
        if bus.wait_connected(BROKER_S):
            return True
        log("waiting for the broker")
    return False


def _retained(bus: MqttBus, stop: threading.Event, timeout_s: float) -> None:
    """Give the broker its moment to hand over the desired rows it holds, and
    deliver them, before anything opens a link they could go out over.

    Delivered here on this thread, which is the one thread there is until
    `asyncio.run` starts: `DccEx` remembers a desired value and acts on it
    only where a writer is open, so what arrives now is held whole and applied
    in `_applied()`'s order — the track first — by the first connection.

    One drain and not a loop of them, because a drain delivers what is waiting
    when it starts and the window is what the waiting was for.
    """
    stop.wait(timeout_s)
    bus.drain()


async def _driving(
    app: DccEx, bus: MqttBus, stop: threading.Event, period_s: float
) -> None:
    """The link and the drain, on the one loop, until the process ends.

    Ctrl-C arrives here as a cancellation, `asyncio.run` cancelling the task
    it is waiting on, so the stand-down is in a `finally` and the interrupt
    goes on out to `main`. It is the same `finally` the stop event reaches,
    because a railroad left driving is left driving however the process was
    ended.
    """
    link = asyncio.create_task(app.run())
    try:
        while not stop.is_set():
            bus.drain()
            await asyncio.sleep(period_s)
    finally:
        await app.shutdown()
        link.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await link


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.dccex",
        description="Run the dccex translator against a broker: the device"
        " vocabulary turned into a command station's own language.",
    )
    parser.add_argument(
        "--broker",
        required=True,
        metavar="HOST:PORT",
        help=f"the broker to run on, e.g. {BROKER_EXAMPLE}",
    )
    parser.add_argument(
        "--station",
        required=True,
        metavar="HOST:PORT",
        help=f"where dccex-usb serves the command station, e.g."
        f" {STATION_EXAMPLE}; retried until it answers",
    )
    parser.add_argument(
        "--startup",
        type=Path,
        metavar="FILE",
        help="raw station commands sent on powering the rails, one per line:"
        " this railroad's per-district trip currents",
    )
    parser.add_argument(
        "--id",
        default=ID,
        help=f"what this translator calls itself on its link row,"
        f" '{ID}' by default",
    )
    args = parser.parse_args()
    try:
        host, port = address(args.broker)
    except ValueError as refused:
        parser.error(str(refused))
    try:
        # The same parse as the broker's, so the subtlety in it — a bracketed
        # IPv6 host keeps its colons and loses its brackets (#335) — lives in
        # one place. The refusal is written here instead, because what a
        # person mistyped was a station and `lib` would tell them about a
        # broker.
        station = address(args.station)
    except ValueError:
        parser.error(
            f"'{args.station}' is not a station address — write it"
            f" <host>:<port>, e.g. {STATION_EXAMPLE}"
        )
    # A signal is what ends this app, and SIGTERM is the one a container is
    # stopped with: given SIGINT's own handler it raises where the process
    # stands, so a wait for a broker that never comes up ends on it too, and
    # the railroad is stood down on the way out either way.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    to_stderr(f"broker {host}:{port}, station {station[0]}:{station[1]}")
    bus = MqttBus(host, port, client_id=f"{CLIENT_PREFIX}{args.id}")
    try:
        with contextlib.suppress(KeyboardInterrupt):
            serve(bus, station, threading.Event(), args.startup, args.id)
    finally:
        bus.close()


if __name__ == "__main__":
    main()
