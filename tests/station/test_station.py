"""Tests at the mirror seam, with a pty standing in for the command station.

The app opens the pty's slave by name, exactly as it opens `/dev/dccex`, and
the test is the device on the master side. Nothing here needs a command
station: what is asserted is the mirror — framing, fan-out, and what a client
gets while the device is away — and none of that is DCC-EX (#217).

The suite has no asyncio plugin, so each test is a coroutine handed to
`asyncio.run`, and the injected log is what the test waits on: the app says
`serial open` when it has the device, which is the only moment from which a
client's message is expected to arrive.
"""

import asyncio
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tc49.station.station import Station

SETTLE_S = 0.2
TIMEOUT_S = 5.0


class Pty:
    """A pty standing in for the device: the app opens `path`, the test is `master`."""

    def __init__(self) -> None:
        self.master, self._slave = os.openpty()
        self.path = os.ttyname(self._slave)
        os.set_blocking(self.master, False)
        self._open = True

    def close(self) -> None:
        """Pull the cable. Idempotent, so a test may do it before the fixture."""
        if not self._open:
            return
        self._open = False
        os.close(self.master)
        os.close(self._slave)


class Log:
    """The injected log, and the test's window onto what the app is doing."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.times: list[float] = []
        self._appended = asyncio.Event()

    def __call__(self, line: str) -> None:
        self.lines.append(line)
        self.times.append(time.monotonic())
        self._appended.set()

    def said(self, prefix: str) -> list[float]:
        """When each line starting with `prefix` was said, in order."""
        return [
            at for at, line in zip(self.times, self.lines) if line.startswith(prefix)
        ]

    async def wait_for(self, prefix: str, timeout: float = TIMEOUT_S) -> str:
        deadline = time.monotonic() + timeout
        while True:
            self._appended.clear()
            for line in self.lines:
                if line.startswith(prefix):
                    return line
            left = deadline - time.monotonic()
            if left <= 0:
                raise AssertionError(f"no log line {prefix!r} in {self.lines}")
            await asyncio.wait_for(self._appended.wait(), left)

    async def wait_for_count(
        self, prefix: str, count: int, timeout: float = TIMEOUT_S
    ) -> None:
        """Wait until `prefix` has been said `count` times."""
        deadline = time.monotonic() + timeout
        while len(self.said(prefix)) < count:
            self._appended.clear()
            if len(self.said(prefix)) >= count:
                return
            left = deadline - time.monotonic()
            if left <= 0:
                raise AssertionError(
                    f"{prefix!r} said {len(self.said(prefix))} times, not {count},"
                    f" in {self.lines}"
                )
            await asyncio.wait_for(self._appended.wait(), left)


@pytest.fixture
def pty() -> Iterator[Pty]:
    device = Pty()
    yield device
    device.close()


def station(device: str, log: Log) -> Station:
    """A station on an OS-chosen port, with outages measured in milliseconds."""
    return Station(device, 0, log=log, first_backoff_s=0.005, max_backoff_s=0.02)


async def connect(app: Station) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection("127.0.0.1", app.port)


async def send(writer: asyncio.StreamWriter, data: bytes) -> None:
    writer.write(data)
    await writer.drain()


async def arriving(fd: int, count: int, timeout: float = TIMEOUT_S) -> bytes:
    """Read from the device side until `count` bytes are there, or time runs out."""
    got = b""
    deadline = time.monotonic() + timeout
    while len(got) < count and time.monotonic() < deadline:
        try:
            got += os.read(fd, 4096)
        except BlockingIOError:
            await asyncio.sleep(0.005)
    return got


async def nothing_arriving(fd: int) -> bytes:
    """What reaches the device side while nothing is supposed to."""
    await asyncio.sleep(SETTLE_S)
    try:
        return os.read(fd, 4096)
    except BlockingIOError:
        return b""


def open_fds() -> int:
    """How many descriptors this process holds."""
    return len(os.listdir("/dev/fd"))


def test_two_clients_interleaved_produce_two_whole_messages(pty: Pty) -> None:
    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            _, one = await connect(app)
            _, two = await connect(app)
            await log.wait_for("serial open")
            first, second = b"<t 3 50 1>", b"<a 12 1>"
            for at in range(max(len(first), len(second))):
                if at < len(first):
                    await send(one, first[at : at + 1])
                if at < len(second):
                    await send(two, second[at : at + 1])

            got = await arriving(pty.master, len(first) + len(second))

            assert got in (first + second, second + first)
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_serial_write_reaches_every_client(pty: Pty) -> None:
    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            one, one_writer = await connect(app)
            two, two_writer = await connect(app)
            await log.wait_for("serial open")

            os.write(pty.master, b"<p1>")

            for client in (one, two):
                heard = await asyncio.wait_for(client.readexactly(4), TIMEOUT_S)
                assert heard == b"<p1>"
            one_writer.close()
            two_writer.close()
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_client_disconnecting_mid_message_leaves_the_device_untouched(
    pty: Pty,
) -> None:
    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            _, writer = await connect(app)
            await log.wait_for("serial open")
            await send(writer, b"<t 3 50")

            writer.close()
            await log.wait_for("client disconnected")

            assert await nothing_arriving(pty.master) == b""
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_doubled_start_yields_one_message(pty: Pty) -> None:
    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            _, writer = await connect(app)
            await log.wait_for("serial open")

            await send(writer, b"<<t 3 0 1>")

            assert await arriving(pty.master, len(b"<t 3 0 1>")) == b"<t 3 0 1>"
            assert await nothing_arriving(pty.master) == b""
        finally:
            await app.close()

    asyncio.run(scenario())


def test_what_a_client_sends_while_the_device_is_away_is_dropped(
    pty: Pty, tmp_path: Path
) -> None:
    """The device appears only after the client has spoken, and hears nothing of it."""

    async def scenario() -> None:
        log = Log()
        absent = tmp_path / "dccex"
        app = station(str(absent), log)
        await app.start()
        try:
            _, writer = await connect(app)
            await send(writer, b"<t 3 50 1>")
            await log.wait_for("device away")

            absent.symlink_to(pty.path)
            await log.wait_for("serial open")

            assert await nothing_arriving(pty.master) == b""

            # And the client is still connected, so what it sends now arrives.
            await send(writer, b"<a 12 1>")
            assert await arriving(pty.master, len(b"<a 12 1>")) == b"<a 12 1>"
        finally:
            await app.close()

    asyncio.run(scenario())


class Flapping(Station):
    """A station whose device session ends the moment the device is open.

    A real one is a command station that answers the open and then says
    nothing — the end of file the mirror reads as the device going away
    again. The watcher's pacing is what is under test, not the mirror.
    """

    async def _mirror(self, fd: int) -> bool:
        await asyncio.sleep(0)
        return False


def test_a_device_that_will_not_configure_keeps_the_watcher_retrying(
    pty: Pty, tmp_path: Path
) -> None:
    """A path that opens but is no tty is an outage like any other, not the end.

    Setting the line discipline on it raises `termios.error`, which is not an
    `OSError`. The watcher survives it, holds no descriptor from the attempt,
    and is still there to take the device when it appears.
    """

    async def scenario() -> None:
        log = Log()
        not_a_tty = tmp_path / "dccex"
        not_a_tty.write_bytes(b"")
        app = station(str(not_a_tty), log)
        await app.start()
        try:
            _, writer = await connect(app)
            await send(writer, b"<t 3 50 1>")
            await log.wait_for("device away")

            held = open_fds()
            await asyncio.sleep(SETTLE_S)
            assert open_fds() == held

            not_a_tty.unlink()
            not_a_tty.symlink_to(pty.path)
            await log.wait_for("serial open")
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_session_that_ends_at_once_waits_before_reopening(pty: Pty) -> None:
    """A device that is open and gone again is not reopened in a hot loop."""

    async def scenario() -> None:
        log = Log()
        backoff = 0.1
        app = Flapping(pty.path, 0, log=log, first_backoff_s=backoff, max_backoff_s=0.2)
        await app.start()
        try:
            await log.wait_for_count("serial open", 2)

            assert log.said("serial open")[1] - log.said("serial closed")[0] >= backoff
        finally:
            await app.close()

    asyncio.run(scenario())


def test_the_dropped_notice_is_said_again_in_a_later_outage(
    pty: Pty, tmp_path: Path
) -> None:
    """Each outage says it once: the second one is news as much as the first."""

    async def scenario() -> None:
        log = Log()
        cable = tmp_path / "dccex"
        app = station(str(cable), log)
        await app.start()
        try:
            _, writer = await connect(app)
            await send(writer, b"<t 3 50 1>")
            await log.wait_for_count("device away", 1)

            cable.symlink_to(pty.path)
            await log.wait_for("serial open")
            cable.unlink()
            pty.close()
            await log.wait_for("serial closed")

            await send(writer, b"<a 12 1>")

            await log.wait_for_count("device away", 2)
        finally:
            await app.close()

    asyncio.run(scenario())
