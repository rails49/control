"""The mirror as a process: what the entrypoint does when the mirror ends.

`mirroring` is the loop `python -m tc49.dccex_usb` runs — the mirror on a
task of its own and the bus drained beside it — and what is asserted here is
its side of that arrangement: a mirror that cannot serve ends the process
rather than leaving it draining a bus with no TCP port and no device (#526).
A box whose 2560 is already taken, or whose command station is not enumerated
yet, depends on the exit: `restart: unless-stopped` is what tries again.

There is no device here and no broker. The station is a stand-in whose `run()`
the test writes, because what is under test is the entrypoint's observation of
a mirror rather than the mirror — that is `test_station.py`'s — and the flash
ordering the teardown owes a half-written station is `test_firmware.py`'s.
"""

import asyncio
import errno
import socket
import subprocess
import sys
import threading

import pytest

from tc49.dccex_usb.__main__ import mirroring
from tc49.dccex_usb.firmware import Flasher
from tc49.dccex_usb.station import HOST, Station
from tc49.lib.bus import Bus, InProcessBus
from tc49.lib.clock import Clock
from tests.brokers import free_port

DEVICE = "/dev/dccex-that-is-not-there"
PORT = 2560
PERIOD_S = 0.01
TIMEOUT_S = 5.0
DRAINS = 3
"""Turns of the loop a test waits out before it ends one: enough that the
drain is going round rather than having run once."""


class Counted(InProcessBus):
    """The bus, with its drains counted — the loop's other half, and the only
    thing about it these tests read."""

    def __init__(self) -> None:
        super().__init__(Clock())
        self.drains = 0

    def drain(self) -> None:
        self.drains += 1
        super().drain()


class Failing(Station):
    """A mirror that cannot serve: `run()` raises where binding the port on a
    box that already has something on it raises."""

    def __init__(self) -> None:
        super().__init__(DEVICE, PORT)

    async def run(self) -> None:
        raise OSError(errno.EADDRINUSE, "address already in use")


class Endless(Station):
    """A mirror that serves until it is cancelled, which is the live one."""

    def __init__(self) -> None:
        super().__init__(DEVICE, PORT)
        self.cancelled = False

    async def run(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class Settling(Flasher):
    """A flasher with a flash in flight: `settled()` says when the teardown
    reached it, and comes back only once the test lets the flash finish."""

    def __init__(self, bus: Bus, device: Station) -> None:
        super().__init__(bus, device, log=lambda line: None)
        self.reached = asyncio.Event()
        self.let_go = asyncio.Event()

    async def settled(self) -> None:
        self.reached.set()
        await self.let_go.wait()


def quiet(bus: Bus, device: Station) -> Flasher:
    """The real flasher with nothing in flight, which is every moment but a
    flash: it subscribes and then has nothing to say to these tests."""
    return Flasher(bus, device, log=lambda line: None)


def test_a_mirror_that_cannot_serve_ends_the_loop() -> None:
    """The port is taken, so `run()` raises at once and there is no mirror to
    drain beside. Before #526 the task's failure was never looked at and the
    loop went round forever: a live process with no TCP server, no device and
    nothing logged, which `restart: unless-stopped` cannot help."""

    async def refused() -> None:
        bus = Counted()
        station = Failing()
        stop = threading.Event()  # the deployment sets it never, and nor does this
        looping = asyncio.create_task(
            mirroring(station, quiet(bus, station), bus, stop, PERIOD_S)
        )
        # Waited on rather than cancelled after: a loop cancelled from outside
        # carries the failure out anyway, and what is asserted is that nothing
        # outside had to.
        ended, _ = await asyncio.wait({looping}, timeout=TIMEOUT_S)
        assert ended, "the loop went round with no mirror behind it"
        await looping

    with pytest.raises(OSError) as carried:
        asyncio.run(refused())
    assert carried.value.errno == errno.EADDRINUSE


def test_a_mirror_that_serves_is_drained_beside_until_stop() -> None:
    """The live arrangement, unchanged: the drain goes round on its period
    for as long as the mirror is up, and `stop` — the suite's way out, where
    the deployment's is a signal — is what ends it."""

    async def serving() -> tuple[Endless, Counted]:
        bus = Counted()
        station = Endless()
        stop = threading.Event()
        looping = asyncio.create_task(
            mirroring(station, quiet(bus, station), bus, stop, PERIOD_S)
        )
        while bus.drains < DRAINS:
            await asyncio.sleep(PERIOD_S)
        stop.set()
        await looping
        return station, bus

    station, bus = asyncio.run(asyncio.wait_for(serving(), TIMEOUT_S))
    assert bus.drains >= DRAINS
    assert station.cancelled, "the mirror was left running behind the loop"


def test_a_flash_in_flight_is_waited_out_before_the_mirror_is_cancelled() -> None:
    """The one thing the teardown is for: the mirror gives the device back
    when the flash is done with it, so ending in the middle of one leaves the
    station half written (ADR-0065)."""

    async def flashing() -> Endless:
        bus = Counted()
        station = Endless()
        flasher = Settling(bus, station)
        stop = threading.Event()
        looping = asyncio.create_task(mirroring(station, flasher, bus, stop, PERIOD_S))
        while bus.drains < DRAINS:
            await asyncio.sleep(PERIOD_S)
        stop.set()
        await flasher.reached.wait()
        assert not station.cancelled, "the mirror went while the flash was writing"
        flasher.let_go.set()
        await looping
        return station

    assert asyncio.run(asyncio.wait_for(flashing(), TIMEOUT_S)).cancelled


def test_a_port_already_in_use_exits_non_zero() -> None:
    """The whole of it as the container runs it. What the box does with the
    exit is the deploy's business; what this app owes it is a process that is
    gone and a reason on stderr (ADR-0050).

    The port is held on `HOST` and not on loopback, which is what the app asks
    for: asyncio binds with `SO_REUSEADDR`, and BSD lets a wildcard bind walk
    past a socket on `127.0.0.1` when it is set — so on a Mac the mirror came
    up beside the holder and this test waited out its timeout instead.
    """
    with socket.socket() as taken:
        taken.bind((HOST, 0))
        taken.listen()
        port = int(taken.getsockname()[1])
        with socket.socket() as probe:
            # The holder really holds it, asked the way the app asks. A
            # platform that answered otherwise would leave the mirror up and
            # this test waiting on a process that is not going to end.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError):
                probe.bind((HOST, port))
        ran = subprocess.run(
            [
                sys.executable,
                "-m",
                "tc49.dccex_usb",
                "--broker",
                f"127.0.0.1:{free_port()}",  # nothing there: the mirror waits for none
                "--device",
                DEVICE,
                "--port",
                str(port),
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S * 4,
            check=False,  # the non-zero exit is the assertion, not a failure here
        )

    assert ran.returncode != 0
    assert "address already in use" in ran.stderr.lower()
