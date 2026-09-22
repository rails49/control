"""The port a test's server listens on, picked so nothing else can take it.

Here rather than in `tests/brokers.py`, which is the second process the apps
come up against, or `tests/apps.py`, which is one container's worth of app:
what a number is wanted for is the same in both and in the suites that serve
a store on a thread.

Every one of those is told its number before anything binds it. A store's
URL is handed to an app that goes looking for it first, which is the order
those suites exist to hold (ADR-0059, decision 5), and mosquitto reads its
port out of a config file written before the process starts. So a number
picked by binding `:0` and closing the socket is a number nobody holds, and
the kernel is free to hand the same one to the next outbound connection —
it draws them from that same ephemeral range. That is what reddened `ci` on
a change touching no Python the suite runs (#560): an MQTT client
reconnecting in a loop took the port a store was about to be started on.

So the numbers come from below that range, where no outbound socket is given
one, and from a cursor that offers each of them once, so no two fixtures are
given the same. Each is offered to the kernel first, which leaves one caller
this cannot speak for — a program outside this run, holding a number in the
band — and steps over what it is holding rather than into it.
"""

import random
import socket
from pathlib import Path

LOCAL_RANGE = Path("/proc/sys/net/ipv4/ip_local_port_range")
"""Where Linux says which numbers it hands out by itself. A Mac says it
through `sysctl` and keeps IANA's, which is the fallback below."""

BAND = 4096
"""How many numbers a run may be given, counting down from the ephemeral
range. Wide enough that no suite exhausts it and narrow enough to stay clear
of the registered ports a developer's machine is actually serving."""


def ephemeral_first() -> int:
    """The bottom of the range the kernel draws outbound connections from."""
    try:
        first, _last = LOCAL_RANGE.read_text().split()
    except OSError:
        return 49152  # IANA's, and what a Mac uses
    return int(first)


EPHEMERAL_FIRST = ephemeral_first()


def bindable(port: int) -> bool:
    """Whether the kernel will give this number to a server asking for it.
    Loopback, because that is where everything the suite starts listens."""
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


class Ports:
    """The numbers one run hands out: a cursor over a band of them, walking
    from a start nobody else's run is likely to share.

    Instantiated once below. It is a class so the walking can be tested over
    a band of three.
    """

    def __init__(self, first: int, last: int, start: int | None = None) -> None:
        self._first = first
        self._last = last
        self._next = random.randint(first, last) if start is None else start
        self._given: set[int] = set()

    def take(self) -> int:
        for _ in range(self._last - self._first + 1):
            port = self._next
            self._next = self._first if port >= self._last else port + 1
            if port in self._given or not bindable(port):
                continue
            self._given.add(port)
            return port
        raise RuntimeError(f"no free port between {self._first} and {self._last}")


_ports = Ports(max(1024, EPHEMERAL_FIRST - BAND), EPHEMERAL_FIRST - 1)


def free_port() -> int:
    """A port this run has not given out and nothing is listening on."""
    return _ports.take()
