"""What a suite against a real broker does with an `MqttBus`, and the
promises the bus keeps there.

The broker itself, a `mosquitto` on a port of its own, and the `broker`
fixture come from `rails49_testing.broker`, which `tests/conftest.py` loads.
Here rather than in `tests/harness.py`, which is the in-process assembly and
nothing else: the apps that come up alone against a broker (ADR-0059,
decision 5) each want the same helpers.
"""

import itertools
import time
from collections.abc import Callable, Iterator

import pytest
from rails49_testing.broker import Broker, until

from tc49.lib.mqtt import MqttBus


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


def beats(port: int, topic: str, seconds: float = 4.5) -> list[float]:
    """When `topic` arrived over a stretch of wall time, by the monotonic
    clock, heard by a client of its own and counted from when it subscribed:
    what an app saying it is up is held to is a rate, so the seconds have to
    pass rather than a condition come true (#1113)."""
    witness = MqttBus(port=port)
    assert witness.wait_connected(), "the witness never reached the broker"
    began = time.monotonic()
    heard: list[float] = []
    witness.subscribe(topic, lambda _topic, _payload: heard.append(time.monotonic()))
    deadline = began + seconds
    while time.monotonic() < deadline:
        witness.drain()
        time.sleep(0.01)
    witness.close()
    return [at - began for at in heard]


def at_least_once_in_any_two_seconds(heard: list[float], seconds: float) -> bool:
    """Whether arrivals at `heard`, seconds into a stretch of `seconds`, leave
    no gap of two seconds: from the start, between two, or before the end."""
    edges = [0.0, *heard, seconds]
    return all(later - earlier < 2.0 for earlier, later in itertools.pairwise(edges))


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
