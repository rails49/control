"""Tests at the MqttBus seam: the bus contract kept over a real broker.

Against a `mosquitto` on a free port, one per test, so no test sees another's
retained values. Skipped where no `mosquitto` is installed: a machine without
one still runs everything else, and CI installs it (#369).
"""

import json
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from paho.mqtt import client as paho
from paho.mqtt.enums import CallbackAPIVersion

from tc49.lib.bus import Bus, Payload
from tc49.lib.mqtt import MqttBus

POWER = "tc49/layout/state/power"
OCCUPIED = "tc49/layout/block_occupied"


def _free_port() -> int:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        return int(held.getsockname()[1])


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


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
        self.port = _free_port()
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
        return _until(lambda: _listening(self.port))

    def stop(self) -> None:
        if self._running is not None:
            self._running.terminate()
            self._running.wait(timeout=5)
            self._running = None


@pytest.fixture
def broker(tmp_path: Path) -> Iterator[Broker]:
    if shutil.which("mosquitto") is None:
        pytest.skip("no mosquitto installed")
    running = Broker(tmp_path / "mosquitto.conf")
    if not running.start():
        running.stop()
        pytest.skip("mosquitto would not start")
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


@pytest.fixture
def raw(broker: Broker) -> Iterator[paho.Client]:
    """A client on this test's broker that is not ours: what any other
    participant can send and see, the bus contract being JSON on named topics
    and nothing about who is speaking (SYSTEM.md, rule 4)."""
    client = paho.Client(CallbackAPIVersion.VERSION2, protocol=paho.MQTTv311)
    client.connect("127.0.0.1", broker.port)
    client.loop_start()
    assert _until(client.is_connected), "raw client never reached the broker"
    try:
        yield client
    finally:
        client.disconnect()
        client.loop_stop()


def _until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _drained(bus: MqttBus, predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Drain until the test's condition holds, or give up. Draining is the
    only thing that delivers, so waiting for a delivery means draining."""

    def once() -> bool:
        bus.drain()
        return predicate()

    return _until(once, timeout)


def _through(writer: MqttBus, witness: MqttBus, topic: str, payload: Payload) -> None:
    """Publish, and come back once the broker has passed it on.

    What it takes to say a subscription is *late*: a publish is handed to the
    client's network thread, so without this a test would be racing its own
    writer rather than showing what a subscriber gets.
    """
    heard: list[Payload] = []
    witness.subscribe(topic, lambda topic, payload: heard.append(payload))
    writer.publish(topic, payload)
    assert _drained(witness, lambda: len(heard) == 1), f"nothing reached {topic}"


def _settle(bus: MqttBus, seconds: float = 0.5) -> None:
    """Long enough that anything the broker was going to send has arrived and
    been drained. What it takes to assert a negative."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        bus.drain()
        time.sleep(0.01)


def test_the_binding_is_a_bus(buses: Callable[[], MqttBus]) -> None:
    """Checked where it matters, which is at type-check time: an app is
    handed `Bus` and cannot name which binding it got (ADR-0059)."""
    bus: Bus = buses()

    assert bus.last_values == {}


def test_state_published_before_a_subscriber_reaches_it(
    buses: Callable[[], MqttBus],
) -> None:
    writer, witness, reader = buses(), buses(), buses()
    _through(writer, witness, POWER, {"power": "on"})

    seen: list[Payload] = []
    reader.subscribe(POWER, lambda topic, payload: seen.append(payload))

    assert _drained(reader, lambda: len(seen) == 1)
    assert seen[0]["power"] == "on"


def test_event_published_before_a_subscriber_does_not(
    buses: Callable[[], MqttBus],
) -> None:
    writer, witness, reader = buses(), buses(), buses()
    _through(writer, witness, OCCUPIED, {"block": "a"})

    seen: list[str] = []
    reader.subscribe("tc49/#", lambda topic, payload: seen.append(payload["block"]))
    _settle(reader)

    assert seen == []

    # And the subscription is live, so the silence above is the event topic
    # not being replayed rather than nothing working.
    writer.publish(OCCUPIED, {"block": "b"})
    assert _drained(reader, lambda: seen == ["b"])


def test_a_handler_runs_on_the_thread_that_drained(
    buses: Callable[[], MqttBus],
) -> None:
    writer, reader = buses(), buses()
    threads: list[threading.Thread] = []
    reader.subscribe(
        POWER, lambda topic, payload: threads.append(threading.current_thread())
    )

    writer.publish(POWER, {"power": "off"})
    # The value has reached the client — it is in `last_values`, which the
    # network thread writes — and no handler has run.
    assert _until(lambda: POWER in reader.last_values)
    assert threads == []

    drainer = threading.Thread(target=reader.drain)
    drainer.start()
    drainer.join()

    assert threads == [drainer]


def test_a_state_payload_is_stamped_from_wall_time(
    buses: Callable[[], MqttBus],
) -> None:
    writer, reader = buses(), buses()
    seen: list[Payload] = []
    reader.subscribe(POWER, lambda topic, payload: seen.append(payload))

    before = time.time()
    writer.publish(POWER, {"at": 1.0, "power": "on"})
    assert _drained(reader, lambda: len(seen) == 1)

    # The stamp the caller supplied is gone, and what stands is this instant
    # on the clock every process on the broker shares.
    assert before <= seen[0]["at"] <= time.time()
    assert list(seen[0]) == ["at", "power"]


def test_an_event_payload_is_not_stamped(buses: Callable[[], MqttBus]) -> None:
    writer, reader = buses(), buses()
    seen: list[Payload] = []
    reader.subscribe(OCCUPIED, lambda topic, payload: seen.append(payload))

    writer.publish(OCCUPIED, {"block": "a"})
    assert _drained(reader, lambda: len(seen) == 1)
    assert seen[0] == {"block": "a"}


def test_filters_deliver_as_the_bus_matches(buses: Callable[[], MqttBus]) -> None:
    writer, reader = buses(), buses()
    seen: dict[str, list[str]] = {"exact": [], "plus": [], "hash": []}
    reader.subscribe(OCCUPIED, lambda topic, payload: seen["exact"].append(topic))
    reader.subscribe("tc49/layout/+", lambda topic, payload: seen["plus"].append(topic))
    reader.subscribe(
        "tc49/dispatch/#", lambda topic, payload: seen["hash"].append(topic)
    )

    writer.publish(OCCUPIED, {"block": "a"})
    writer.publish("tc49/dispatch/request_completed", {"id": "r-1"})

    assert _drained(reader, lambda: all(len(one) == 1 for one in seen.values()))
    assert seen["exact"] == [OCCUPIED]
    assert seen["plus"] == [OCCUPIED]
    assert seen["hash"] == ["tc49/dispatch/request_completed"]


def test_an_invalid_filter_is_refused(buses: Callable[[], MqttBus]) -> None:
    bus = buses()
    with pytest.raises(ValueError):
        bus.subscribe("tc49/layout/dispatch#", lambda topic, payload: None)


def test_last_values_holds_the_state_topics_heard(
    buses: Callable[[], MqttBus],
) -> None:
    writer, reader = buses(), buses()
    writer.publish(POWER, {"power": "on"})
    writer.publish(OCCUPIED, {"block": "a"})
    reader.subscribe("tc49/#", lambda topic, payload: None)

    assert _until(lambda: POWER in reader.last_values)
    _settle(reader)

    # The event topic is nowhere in the picture: only a state topic keeps a
    # last value, and it is the writer's own row too.
    assert list(reader.last_values) == [POWER]
    assert reader.last_values[POWER]["power"] == "on"
    assert list(writer.last_values) == [POWER]


def test_an_unreadable_payload_is_dropped(
    buses: Callable[[], MqttBus], raw: paho.Client
) -> None:
    writer, reader = buses(), buses()
    seen: list[Payload] = []
    reader.subscribe("tc49/#", lambda topic, payload: seen.append(payload))

    # What any other participant on the broker can send: a payload proves
    # nothing about its sender, and a handler is given nothing it cannot read.
    raw.publish(OCCUPIED, b"{not json", qos=0)
    _settle(reader)
    assert seen == []

    writer.publish(OCCUPIED, {"block": "a"})
    assert _drained(reader, lambda: len(seen) == 1)
    assert seen[0] == {"block": "a"}


def test_a_cleared_retained_value_leaves_the_picture(
    buses: Callable[[], MqttBus], raw: paho.Client
) -> None:
    writer, reader = buses(), buses()
    writer.publish(POWER, {"power": "on"})
    reader.subscribe(POWER, lambda topic, payload: None)
    assert _until(lambda: POWER in reader.last_values)

    raw.publish(POWER, b"", qos=0, retain=True)

    assert _until(lambda: POWER not in reader.last_values)


def test_the_payload_on_the_wire_is_json(
    buses: Callable[[], MqttBus], raw: paho.Client
) -> None:
    """One shape, so a client that is not ours reads what we publish and we
    read what it sends: the bus is JSON on named topics (SYSTEM.md)."""
    bus = buses()
    wire: list[bytes] = []
    raw.on_message = lambda client, userdata, message: wire.append(message.payload)

    bus.publish(POWER, {"power": "on"})
    # A state topic, so the broker has it waiting whenever the raw client's
    # subscription lands and there is no race to lose.
    raw.subscribe(POWER, qos=0)

    assert _until(lambda: len(wire) == 1)
    sent = json.loads(wire[0])
    assert sent["power"] == "on"
    assert isinstance(sent["at"], float)


def test_a_lost_connection_is_said_and_retried(
    broker: Broker, buses: Callable[[], MqttBus], capsys: pytest.CaptureFixture[str]
) -> None:
    """The one thing an app does about its broker going away: keep running,
    and let a person watching the container see it (ADR-0050, ADR-0059)."""
    bus = buses()
    bus.subscribe(POWER, lambda topic, payload: None)

    broker.stop()
    assert _until(lambda: not bus.connected)
    assert "lost" in capsys.readouterr().err

    assert broker.start()
    # Reconnected on the client's own backoff, whose first step is a second.
    assert bus.wait_connected(timeout=30.0)
