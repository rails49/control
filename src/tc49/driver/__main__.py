"""`python -m tc49.driver` — the driver as a process of its own.

Every app comes up alone (ADR-0059, decision 5). Started against an empty
broker with nothing else running, this connects, subscribes and stays up; it
exits on nothing but a signal. Nothing here is ordered by anything else coming
up first, which is why compose carries no `depends_on`.

Two flags, the ones a compose service passes: where the broker is, and which
railroad it runs. **No `--store`**, because the driver reads no documents: it
holds no state and reads no assets (SYSTEM.md, driver footprint), the grant
and the two speeds being between them every field `move` needs. The railroad's
name is here because one broker runs one railroad and every app process is
given its name at start (ADR-0059, decision 2); the driver holds nothing keyed
to a railroad, so the name is what a person watching six containers reads and
nothing this app looks anything up by. The drain period is not a flag either —
nothing outside this process has an opinion about how often it takes what the
broker's network thread left waiting, and it is short enough that a grant is
commanded in the same tenth of a second whoever started the container.

The startup order is `lib/startup.py`'s, and it is shorter here at both ends.
**No documents**, so nothing to wait for from the store: an app that reads
nothing cannot be brought up in the wrong order with respect to one that
serves documents. **No rows of its own** either, so nothing retained is
published or waited for — the driver publishes exactly one topic and only ever
in answer to a grant, so a cold start is silent and the first thing anything
hears from this process is a `move`.

What is left is the broker, and `Driver` on it. Subscribing while connected is
acknowledged before the call comes back, so the app is live on `move_granted`
by the time it says it is up, where a subscription made while disconnected
would only go again with the reconnect. A grant is an **event** and the broker
holds none, so what arrives in that gap is gone rather than delivered late —
which is the same thing that happens to a grant made while this container is
being restarted, and why the dispatcher re-grants rather than the driver
remembering.

Then the loop, which is a drain and a sleep. `Driver` is handed a `Bus` and
nothing else in the package changes: which binding it got is this file's
business, and a grant that cannot be read is dropped on the broker exactly as
it was in one process (#261, SYSTEM.md rule 4) — under MQTT the publisher is
another process, and a bug there must not take this one down.
"""

import argparse
import contextlib
import signal
import sys
import threading
from collections.abc import Callable

from tc49.driver.driver import Driver
from tc49.lib.loading import Loaded
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address
from tc49.lib.startup import PERIOD_S, connected

CLIENT_ID = "tc49-driver"
"""What this app calls itself to the broker, so its log names an app rather
than a random string. Nothing in the contract reads it: a topic has one
writing role and no payload says who published (SYSTEM.md, rule 4)."""


def to_stderr(line: str) -> None:
    """The log: what is being waited for, and what came up. `lib` says its own
    piece under its own prefix (`mqtt:`)."""
    print(f"driver: {line}", file=sys.stderr, flush=True)


def serve(
    bus: MqttBus,
    railroad: str,
    stop: threading.Event,
    period_s: float = PERIOD_S,
    log: Callable[[str], None] = to_stderr,
) -> None:
    """The app and its loop: a broker, the translator on it, and a drain.

    `stop` is how a caller that is not a signal ends the loop, which is the
    suite. The deployment sets it never: a signal raises where the process
    happens to be — in the loop, or in the wait above it — and `main` lets
    that out.

    The line saying it is up is the only announcement there is. This app owns
    no row, so nothing on the bus says it has arrived, and a person reading
    the container's log is who the sentence is for.

    The outer loop is one railroad each time round. A railroad is loaded
    while the apps run (ADR-0060), so the row naming another one ends the
    inner loop and the driver is built again — with **nothing to clear**,
    this being the one app of the five that owns no retained row, and nothing
    to read either. What a rebuild drops is the transit it was in the middle
    of, which belongs to the railroad that is gone (ADR-0054).
    """
    if not connected(bus, stop, log):
        return
    loaded = Loaded(railroad)
    while not stop.is_set():
        Driver(bus)
        # After the app is built and not before: the row is retained, so
        # subscribing here is handed whatever it holds, and nothing this app
        # does on the way up moves — a grant published in the instant between
        # an app coming up and its own subscriptions is lost, and that
        # instant is not one to lengthen (ADR-0059, decision 5).
        loaded.follow(bus)
        built = loaded.name
        log(f"up on '{built}', draining every {period_s}s")
        while not stop.is_set() and not loaded.moved:
            bus.drain()
            stop.wait(period_s)
        if not loaded.moved:
            return
        bus.forget()
        log(f"loading '{loaded.name}': nothing of '{built}' to clear")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m tc49.driver",
        description="Run the driver against a broker: each granted move"
        " restated as the command that moves the train.",
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
        help="the railroad this broker runs, as the store lists it;"
        " named in the log and read for nothing, this app holding no documents",
    )
    args = parser.parse_args()
    try:
        host, port = address(args.broker)
    except ValueError as refused:
        parser.error(str(refused))
    # A signal is what ends this app, and SIGTERM is the one a container is
    # stopped with: given SIGINT's own handler it raises where the process
    # stands, so a wait for a broker that never comes up ends on it too.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    to_stderr(f"broker {host}:{port}")
    bus = MqttBus(host, port, client_id=CLIENT_ID)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            serve(bus, args.railroad, threading.Event())
    finally:
        bus.close()


if __name__ == "__main__":
    main()
