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
import socket
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tc49.dccex_usb.station import READ_SIZE, Station

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


BEHIND_BYTES = 4096

QUICK_BACKOFF_S = 0.005
PATIENT_BACKOFF_S = 0.2
"""A backoff a test can act inside: the grace is two of it, so a test that
has to speak to an away device before its clients are dropped asks for this
one and still finishes in under a second."""

PATIENT_GRACE_S = 2 * PATIENT_BACKOFF_S
"""The grace at that backoff: two reopens of it, which is what GRACE_REOPENS
counts."""


def station(device: str, log: Log, *, backoff_s: float = QUICK_BACKOFF_S) -> Station:
    """A station on an OS-chosen port, with outages measured in milliseconds.

    A client falls behind in kilobytes rather than the megabyte of the real
    bound, so a test can put one behind by not reading for a moment. The
    backoff is the grace as well — two reopens of it — so an outage is over,
    and the clients of one are gone, in milliseconds too.
    """
    return Station(
        device,
        0,
        log=log,
        first_backoff_s=backoff_s,
        max_backoff_s=4 * backoff_s,
        max_outstanding_bytes=BEHIND_BYTES,
    )


async def connect(app: Station) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.open_connection("127.0.0.1", app.port)


async def connect_deaf(
    app: Station,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A client that will never be read from, and cannot take much unread.

    Its receive buffer is set small before it connects, so the kernels either
    side hold kilobytes rather than the megabytes they will size themselves
    up to on loopback. What the app sees is the same client either way — one
    that stops taking bytes — reached in a fraction of the traffic.
    """
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)
    sock.setblocking(False)
    await asyncio.get_running_loop().sock_connect(sock, ("127.0.0.1", app.port))
    return await asyncio.open_connection(sock=sock)


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


class Talking:
    """The device saying more than a client can take, and a record of it.

    Every chunk names the offset it starts at, so what a client heard can be
    compared with what was said and a gap in the middle cannot pass for the
    whole stream.
    """

    def __init__(self, fd: int) -> None:
        self._fd = fd
        self.said = bytearray()

    async def run(self) -> None:
        while True:
            chunk = f"<p{len(self.said)}>".encode().ljust(64, b".")
            rest = memoryview(chunk)
            while rest:
                try:
                    written = os.write(self._fd, rest)
                except BlockingIOError:
                    await asyncio.sleep(0.001)
                    continue
                self.said += rest[:written]
                rest = rest[written:]
            await asyncio.sleep(0)


class Listening:
    """A client that keeps reading, and everything it has heard."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        self._reader = reader
        self.heard = bytearray()

    async def run(self) -> None:
        while True:
            arrived = await self._reader.read(READ_SIZE)
            if not arrived:
                return
            self.heard += arrived

    async def hears(self, count: int, timeout: float = TIMEOUT_S) -> None:
        deadline = time.monotonic() + timeout
        while len(self.heard) < count:
            if time.monotonic() > deadline:
                raise AssertionError(f"heard {len(self.heard)} bytes, not {count}")
            await asyncio.sleep(0.005)


async def released(held: int, timeout: float = TIMEOUT_S) -> int:
    """Wait for this process to be back down to `held` descriptors."""
    deadline = time.monotonic() + timeout
    while open_fds() > held and time.monotonic() < deadline:
        await asyncio.sleep(0.005)
    return open_fds()


def test_a_client_that_stops_reading_is_cut_off_and_its_bytes_released(
    pty: Pty,
) -> None:
    """The buffer for a client that takes nothing is not the railroad's to hold.

    Its descriptor going with it is what says the bytes went too: closing a
    connection waits for what is outstanding to be written, which for a
    client that never reads is forever, so a descriptor that is back is a
    buffer that was let go rather than one still waiting to drain.
    """

    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            _, deaf = await connect_deaf(app)
            await log.wait_for("serial open")
            await asyncio.sleep(SETTLE_S)
            held = open_fds()
            device = asyncio.create_task(Talking(pty.master).run())
            try:
                line = await log.wait_for("client disconnected")
            finally:
                device.cancel()

            assert "too far behind" in line
            # The client's own socket is still open and still unread, so what
            # came back is the station's side of it.
            assert await released(held - 1) == held - 1
            deaf.close()
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_client_that_reads_hears_the_whole_stream_across_a_deaf_one(
    pty: Pty,
) -> None:
    """One client walking out of range costs the others nothing."""

    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log)
        await app.start()
        try:
            reader, keeping_up = await connect(app)
            _, deaf = await connect_deaf(app)
            await log.wait_for("serial open")
            listening = Listening(reader)
            heard = asyncio.create_task(listening.run())
            talking = Talking(pty.master)
            device = asyncio.create_task(talking.run())
            try:
                assert "too far behind" in await log.wait_for("client disconnected")
            finally:
                device.cancel()
            await listening.hears(len(talking.said))

            assert bytes(listening.heard) == bytes(talking.said)
            # And the client that kept up was never the one cut off.
            assert len(log.said("client disconnected")) == 1

            heard.cancel()
            keeping_up.close()
            deaf.close()
        finally:
            await app.close()

    asyncio.run(scenario())


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
    """The device appears only after the client has spoken, and hears nothing of it.

    The client here connects to an outage already past its grace, whose
    clients are gone, so the grace it meets is the one its own arrival starts.
    What it meets meanwhile is the outage itself: its bytes dropped, because a
    command is honored now or ignored.
    """

    async def scenario() -> None:
        log = Log()
        absent = tmp_path / "dccex"
        app = station(str(absent), log)
        await app.start()
        try:
            _, early = await connect(app)
            await log.wait_for("client disconnected")
            early.close()

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
            # And once the grace has taken the client with it and that has
            # settled, so what is counted is the watcher's descriptors.
            await log.wait_for("client disconnected")
            await asyncio.sleep(SETTLE_S)

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
        app = station(str(cable), log, backoff_s=PATIENT_BACKOFF_S)
        await app.start()
        try:
            # A grace the test stays inside: the first outage is recovered
            # before it ends and the second is spoken into, so the one client
            # is still there to speak into each of them.
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


def test_the_device_is_let_go_for_the_block_and_taken_back_after(pty: Pty) -> None:
    """The handover a flash needs: nothing of the mirror's is on the port
    while the block runs, and the device is open again after it (ADR-0065).

    What a client sees inside it is the ordinary outage — what it sends
    dropped, and its connection closed once the grace passes — because for
    that while the device genuinely is away, and a flash lasts tens of
    seconds. The flash path drops its clients by the rule every outage drops
    them by and has no rule of its own (ADR-0066).
    """

    async def scenario() -> None:
        log = Log()
        app = station(pty.path, log, backoff_s=PATIENT_BACKOFF_S)
        await app.start()
        try:
            _, writer = await connect(app)
            await log.wait_for("serial open")

            async with app.released():
                assert not app.held
                assert log.said("serial closed"), "the device is still open"

                await send(writer, b"<t 3 50 1>")
                await log.wait_for("device away")
                assert await nothing_arriving(pty.master) == b""

                await log.wait_for("client disconnected")
                writer.close()

            await log.wait_for_count("serial open", 2)
            assert app.held
            _, after = await connect(app)
            await send(after, b"<a 12 1>")
            assert await arriving(pty.master, len(b"<a 12 1>")) == b"<a 12 1>"
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_device_away_past_the_grace_disconnects_every_client(
    tmp_path: Path,
) -> None:
    """The outage this app is the one to report: the station is switched off,
    the cable is out, or the flash is running, and the reopens do not recover.

    A client cannot tell an away device from a quiet one, so one held through
    an outage is a translator publishing `device/link: up` over a railroad
    that cannot move. The socket closing is the whole signal: the translator's
    session ends the way it already ends and the row goes `down` (ADR-0066).

    Both clients here are on the outage before its grace begins, and both
    leave on the one deadline: the grace is the outage's, not each client's.
    """

    async def scenario() -> None:
        log = Log()
        absent = tmp_path / "dccex"
        app = station(str(absent), log)
        await app.start()
        try:
            one, first = await connect(app)
            two, second = await connect(app)

            assert await asyncio.wait_for(one.read(READ_SIZE), TIMEOUT_S) == b""
            assert await asyncio.wait_for(two.read(READ_SIZE), TIMEOUT_S) == b""

            await log.wait_for_count("client disconnected", 2)
            first.close()
            second.close()
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_client_arriving_into_a_running_grace_leaves_with_it(
    tmp_path: Path,
) -> None:
    """The grace is the outage's, not each client's (ADR-0066).

    The late client here arrives half a grace into one already being waited
    out, and is disconnected on that deadline rather than on one of its own:
    it lives the remainder. A grace per client would keep it a full one past
    its arrival, which is what the margin below separates.
    """

    async def scenario() -> None:
        log = Log()
        absent = tmp_path / "dccex"
        app = station(str(absent), log, backoff_s=PATIENT_BACKOFF_S)
        await app.start()
        try:
            early, first = await connect(app)
            # The grace starts where this line is said, so the sleep under it
            # is measured from the grace and not from the connect.
            await log.wait_for("client connected")
            await asyncio.sleep(PATIENT_GRACE_S / 2)

            late, second = await connect(app)
            joined = time.monotonic()

            assert await asyncio.wait_for(late.read(READ_SIZE), TIMEOUT_S) == b""
            assert await asyncio.wait_for(early.read(READ_SIZE), TIMEOUT_S) == b""
            await log.wait_for_count("client disconnected", 2)

            lived = max(log.said("client disconnected")) - joined
            assert lived < 0.75 * PATIENT_GRACE_S, lived
            first.close()
            second.close()
        finally:
            await app.close()

    asyncio.run(scenario())


def test_a_device_back_inside_the_first_reopen_keeps_its_clients(
    pty: Pty, tmp_path: Path
) -> None:
    """What the grace is for: a blip costs no throttle a reconnect.

    The device goes and is back before the watcher has asked for it twice —
    a USB stutter, not a station switched off — and what a client notices is
    what it has always noticed, that a command sent meanwhile did nothing.
    """

    async def scenario() -> None:
        log = Log()
        cable = tmp_path / "dccex"
        cable.symlink_to(pty.path)
        app = station(str(cable), log, backoff_s=PATIENT_BACKOFF_S)
        await app.start()
        again = Pty()
        try:
            _, writer = await connect(app)
            await log.wait_for("serial open")

            cable.unlink()
            pty.close()
            await log.wait_for("serial closed")
            cable.symlink_to(again.path)
            await log.wait_for_count("serial open", 2)

            assert log.said("client disconnected") == []
            await send(writer, b"<a 12 1>")
            assert await arriving(again.master, len(b"<a 12 1>")) == b"<a 12 1>"
        finally:
            await app.close()
            again.close()

    asyncio.run(scenario())
