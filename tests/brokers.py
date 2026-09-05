"""A real `mosquitto`, for the suites that test against a broker.

Here rather than in `tests/harness.py`, which is the in-process assembly and
nothing else: what these build is a second process on a port of its own, and
the apps that come up alone against one (ADR-0059, decision 5) each want the
same fixture.

Where no `mosquitto` is installed the suites that take `broker` skip, so a
machine without one still runs everything else. Under CI they fail instead:
a broker is software and belongs in the gate where hardware does not (#372),
so a failed install has to redden the gate rather than quietly delete every
suite built on the bus (#423). `CI` in the environment tells the two apart.
"""

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NoReturn

import pytest

from tc49.lib.mqtt import MqttBus


def free_port() -> int:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        return int(held.getsockname()[1])


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def drained(bus: MqttBus, predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Drain until the test's condition holds, or give up. Draining is the
    only thing that delivers, so waiting for a delivery means draining."""

    def once() -> bool:
        bus.drain()
        return predicate()

    return until(once, timeout)


def settle(bus: MqttBus, seconds: float = 0.5) -> None:
    """Long enough that anything the broker was going to send has arrived and
    been drained. What it takes to assert a negative."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        bus.drain()
        time.sleep(0.01)


class Broker:
    """A `mosquitto` on a port of its own, stoppable and startable again on
    the same one: what a broker going away and coming back looks like from a
    client's side.

    `persistence false`, as the deployed one has it, so what it held is gone
    when it returns: a broker keeps retained values while it runs and nothing
    across its own restart, which is the railroad coming up at rest
    (ADR-0059, decision 3).
    """

    def __init__(self, conf: Path) -> None:
        self.port = free_port()
        self._conf = conf
        self._conf.write_text(
            f"listener {self.port} 127.0.0.1\n"
            "allow_anonymous true\npersistence false\n"
        )
        self._running: subprocess.Popen[bytes] | None = None

    def start(self) -> bool:
        self._running = subprocess.Popen(
            ["mosquitto", "-c", str(self._conf)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return until(lambda: listening(self.port))

    def stop(self) -> None:
        if self._running is not None:
            self._running.terminate()
            self._running.wait(timeout=5)
            self._running = None


def no_broker(reason: str) -> NoReturn:
    """End the test for want of a broker: a skip on a developer's machine, a
    failure under CI, where a missing broker is the gate's business and not
    the test's."""
    if os.environ.get("CI", "").lower() in ("", "0", "false"):
        pytest.skip(reason)
    pytest.fail(reason)


@pytest.fixture
def broker(tmp_path: Path) -> Iterator[Broker]:
    if shutil.which("mosquitto") is None:
        no_broker("no mosquitto installed")
    running = Broker(tmp_path / "mosquitto.conf")
    if not running.start():
        running.stop()
        no_broker("mosquitto would not start")
    try:
        yield running
    finally:
        running.stop()


@pytest.fixture
def buses(broker: Broker) -> Iterator[Callable[[], MqttBus]]:
    """Make a client on this test's broker, connected before it comes back.
    Every one is closed when the test ends, whatever it did with them."""
    made: list[MqttBus] = []

    def make() -> MqttBus:
        bus = MqttBus(port=broker.port)
        assert bus.wait_connected(), "client never reached the broker"
        made.append(bus)
        return bus

    try:
        yield make
    finally:
        for bus in made:
            bus.close()
