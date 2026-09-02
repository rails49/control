"""The harness a suite on the physical binding drives it through (#314).

A plain TCP listener stands in for `dccex-usb`, so the station is reached by
**address** — an address is what `--station` gives and opening it is what a
session has to get right — and nothing needs hardware, which is the rule the
whole gate sits under.

Beside the suites rather than inside one of them because there are two of
them: what a run does on the steel (`test_physical.py`) and where its readings
come from (`test_detector.py`), and both stand a station up and wait on a
thread.
"""

import socket
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Self

from tc49.bench.runner import railroad
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.store import AssetStore
from tests.harness import ASSETS, railroads

HOST = "127.0.0.1"

TIMEOUT_S = 5.0

PERIOD_S = 0.01
"""The pacer's turn, far shorter than a session's own 0.1s: what these tests
wait on is a socket, and every turn is another look at whether it happened."""


class Station:
    """A command station's end of the port, on loopback.

    One connection, answered with a status line so that the app has heard the
    station *speak* — `device/link` goes `up` on an answer and not on an open
    socket — and everything it is sent kept for the test to read.
    """

    def __init__(self) -> None:
        self._listener = socket.socket()
        self._listener.bind((HOST, 0))
        self._listener.listen(1)
        self.port = int(self._listener.getsockname()[1])
        self._heard = bytearray()
        self._lock = threading.Lock()
        threading.Thread(target=self._serve, name="station", daemon=True).start()

    def _serve(self) -> None:
        try:
            connection, _ = self._listener.accept()
        except OSError:
            return  # closed before anything connected, which is a test ending
        with connection:
            try:
                connection.sendall(b"<p0>")  # answering: the rails are dark
                while True:
                    arrived = connection.recv(4096)
                    if not arrived:
                        return
                    with self._lock:
                        self._heard += arrived
            except OSError:
                return

    def heard(self) -> bytes:
        with self._lock:
            return bytes(self._heard)

    def waits_for(self, message: bytes, limit_s: float = TIMEOUT_S) -> bool:
        """Whether that message has arrived, waiting up to `limit_s` for it:
        the wire between the app writing and this end reading is a thread
        boundary, so arrival is a wait and never a given."""
        deadline = time.monotonic() + limit_s
        while message not in self.heard():
            if time.monotonic() > deadline:
                return False
            time.sleep(0.01)
        return True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._listener.close()


def closed_port() -> int:
    """A port nothing is listening on: a station that is not there."""
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def waits_until(done: Callable[[], bool], limit_s: float = TIMEOUT_S) -> bool:
    """Whether it happened inside the limit: what a test on the other side of
    a thread has instead of an assumption."""
    deadline = time.monotonic() + limit_s
    while not done():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def until(done: Callable[[], bool], limit_s: float = TIMEOUT_S) -> Callable[[], bool]:
    """A `stop` that ends the loop once `done`, or once the test has waited
    long enough — a run that never finishes is a hang and not a failure."""
    deadline = time.monotonic() + limit_s
    return lambda: done() or time.monotonic() > deadline


def a_railroad() -> tuple[Layout, Roster]:
    """Some railroad this checkout has: its layout and the stock it owns."""
    return railroad(AssetStore(ASSETS), railroads()[0])
