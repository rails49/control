"""The command station's serial device, mirrored on a TCP port.

The command station is reached over USB only and one process can own the
device, so that process is this app and everything else is a client of the
port it serves (ADR-0043): the translator, JMRI, hand-held throttles. They
coexist, and DecoderPro keeps working with every app of ours down.

It is a mirror, not a protocol. Every byte read from the device is written to
every connected client unchanged, because one serial stream cannot say who
asked — a reply to one client and a broadcast to all look alike on it. The
only reading it does is `<` and `>`, and only the other way: a client's bytes
are held until its message is whole and then written in one write, so two
clients never interleave a command (framing.py). A client that goes away
mid-message takes its partial message with it.

**While the device is away a client's messages are dropped**, not queued, and
the client stays connected. A command is honored now or ignored: a queue that
flushes on reconnect is a train that moves minutes after someone asked for
it. Reopening the device is this app's own business — it goes away when the
command station is switched off — so it retries with backoff, and a client
notices only that what it sent meanwhile did nothing.

There is no client limit beyond the OS's and no authentication: the LAN is
the trust boundary (ADR-0042), and the port is published to it by the
container. The server binds every interface for the same reason.

It speaks no bus topic and imports nothing of ours.
"""

import asyncio
import contextlib
import os
import sys
import termios
from collections.abc import Callable

from tc49.station.framing import frame

# Every interface: the container publishes the port and JMRI reaches it by
# the service name, so what limits the reach is the LAN, not a bind address
# (ADR-0042). One socket rather than one per address family, so the port the
# OS chooses when asked for 0 is one port.
HOST = "0.0.0.0"

BAUD = termios.B115200
READ_SIZE = 4096

FIRST_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0


def to_stderr(line: str) -> None:
    """The default log: connects, disconnects and the device, and nothing else."""
    print(line, file=sys.stderr, flush=True)


class Station:
    """The serial device on `device`, served on `port`.

    `run()` is the whole process. Tests drive the same thing through the
    `start()` / `close()` split, ask `port` which port the OS chose, and pass
    their own `log` and backoff bounds so an outage is over in milliseconds.
    """

    def __init__(
        self,
        device: str,
        port: int,
        *,
        log: Callable[[str], None] = to_stderr,
        first_backoff_s: float = FIRST_BACKOFF_S,
        max_backoff_s: float = MAX_BACKOFF_S,
    ) -> None:
        self._device = device
        self._port = port
        self._log = log
        self._first_backoff_s = first_backoff_s
        self._max_backoff_s = max_backoff_s
        self._clients: set[asyncio.StreamWriter] = set()
        self._fd: int | None = None
        self._dropped = False
        self._server: asyncio.Server | None = None
        self._watcher: asyncio.Task[None] | None = None
        self._writing = asyncio.Lock()

    async def run(self) -> None:
        """Serve until cancelled — the whole of `python -m tc49.station`."""
        await self.start()
        try:
            await self.serve_forever()
        finally:
            await self.close()

    async def start(self) -> None:
        """Bind the port and start watching for the device."""
        self._server = await asyncio.start_server(self._client, HOST, self._port)
        self._watcher = asyncio.create_task(self._watch())

    @property
    def port(self) -> int:
        """The port being served: the one the OS chose, when asked for 0."""
        return int(self._serving().sockets[0].getsockname()[1])

    async def serve_forever(self) -> None:
        await self._serving().serve_forever()

    async def close(self) -> None:
        """Stop serving, drop the clients and let the device go."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
        # Before waiting on the server, which does not return while a handler
        # is still running, and a handler runs until its client is gone.
        for writer in tuple(self._clients):
            writer.close()
        if server is not None:
            await server.wait_closed()
        watcher, self._watcher = self._watcher, None
        if watcher is not None:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher

    async def _client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """One connected client: its bytes framed, its partial message its own."""
        peer = writer.get_extra_info("peername")
        self._clients.add(writer)
        self._log(f"client connected {peer}")
        partial = b""
        try:
            while True:
                arrived = await reader.read(READ_SIZE)
                if not arrived:
                    break
                partial, messages = frame(partial, arrived)
                for message in messages:
                    await self._to_device(message)
        except ConnectionError:
            pass
        finally:
            self._clients.discard(writer)
            self._log(f"client disconnected {peer}")
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()

    async def _to_device(self, message: bytes) -> None:
        """Write one whole message, or drop it because the device is away."""
        fd = self._fd
        if fd is None:
            self._drop()
            return
        # One writer at a time, so a message that takes more than one write
        # is still the only thing between the device and the previous `>`.
        async with self._writing:
            if self._fd != fd:
                self._drop()
                return
            try:
                await write_all(fd, message)
            except OSError:
                # The device went away mid-message. `_mirror` sees the same
                # thing and the watcher reopens it; this message is dropped
                # like anything else sent into an outage.
                self._drop()

    def _drop(self) -> None:
        """One line per outage: after it, the outage is the news, not the loss."""
        if not self._dropped:
            self._dropped = True
            self._log(f"device away, dropping what clients send to {self._device}")

    async def _watch(self) -> None:
        """Keep the device open, retrying with backoff while it is away."""
        backoff = self._first_backoff_s
        while True:
            try:
                fd = open_device(self._device)
            except OSError:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_s)
                continue
            backoff = self._first_backoff_s
            self._fd = fd
            self._log(f"serial open {self._device}")
            try:
                await self._mirror(fd)
            finally:
                self._fd = None
                self._dropped = False
                os.close(fd)
                self._log(f"serial closed {self._device}")

    async def _mirror(self, fd: int) -> None:
        """Fan every byte the device sends to every client, until it goes away."""
        loop = asyncio.get_running_loop()
        gone: asyncio.Future[None] = loop.create_future()

        def readable() -> None:
            try:
                arrived = os.read(fd, READ_SIZE)
            except BlockingIOError:
                return
            except OSError:
                arrived = b""
            if not arrived:
                if not gone.done():
                    gone.set_result(None)
                return
            for writer in tuple(self._clients):
                if not writer.is_closing():
                    writer.write(arrived)

        loop.add_reader(fd, readable)
        try:
            await gone
        finally:
            loop.remove_reader(fd)

    def _serving(self) -> asyncio.Server:
        if self._server is None:
            raise RuntimeError("the station is not started")
        return self._server


def open_device(path: str) -> int:
    """Open the serial device raw at 115200 8N1 and return its descriptor."""
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure(fd)
    except OSError:
        os.close(fd)
        raise
    return fd


def configure(fd: int) -> None:
    """115200 8N1, raw: no echo, no line editing, no flow control.

    The whole line configuration is set rather than adjusted, so the device
    behaves the same however the last program that held it left the port.
    """
    cc = termios.tcgetattr(fd)[6]
    cc[termios.VMIN] = 1
    cc[termios.VTIME] = 0
    iflag = termios.IGNPAR
    oflag = 0
    cflag = termios.CS8 | termios.CLOCAL | termios.CREAD
    lflag = 0
    termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, BAUD, BAUD, cc])


async def write_all(fd: int, data: bytes) -> None:
    """Write every byte, waiting for the device when it is not ready for more."""
    loop = asyncio.get_running_loop()
    rest = memoryview(data)
    while rest:
        try:
            written = os.write(fd, rest)
        except BlockingIOError:
            await writable(loop, fd)
            continue
        rest = rest[written:]


async def writable(loop: asyncio.AbstractEventLoop, fd: int) -> None:
    ready: asyncio.Future[None] = loop.create_future()

    def wake() -> None:
        if not ready.done():
            ready.set_result(None)

    loop.add_writer(fd, wake)
    try:
        await ready
    finally:
        loop.remove_writer(fd)
