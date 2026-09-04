"""Tests at the MqttBus seam: the bus contract kept over a real broker.

Against a `mosquitto` on a free port, one per test, so no test sees another's
retained values (`tests/brokers.py`). Skipped where no `mosquitto` is
installed: a machine without one still runs everything else, and CI installs
it (#369).
"""

import json
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from paho.mqtt import client as paho
from paho.mqtt.enums import CallbackAPIVersion

from tc49.lib.bus import Bus, Payload
from tc49.lib.mqtt import MqttBus, address
from tests.brokers import Broker, drained, settle, until

POWER = "tc49/layout/state/power"
OCCUPIED = "tc49/layout/block_occupied"


@pytest.fixture
def raw(broker: Broker) -> Iterator[paho.Client]:
    """A client on this test's broker that is not ours: what any other
    participant can send and see, the bus contract being JSON on named topics
    and nothing about who is speaking (SYSTEM.md, rule 4)."""
    client = paho.Client(CallbackAPIVersion.VERSION2, protocol=paho.MQTTv311)
    client.connect("127.0.0.1", broker.port)
    client.loop_start()
    assert until(client.is_connected), "raw client never reached the broker"
    try:
        yield client
    finally:
        client.disconnect()
        client.loop_stop()


def _through(writer: MqttBus, witness: MqttBus, topic: str, payload: Payload) -> None:
    """Publish, and come back once the broker has passed it on.

    What it takes to say a subscription is *late*: a publish is handed to the
    client's network thread, so without this a test would be racing its own
    writer rather than showing what a subscriber gets.
    """
    heard: list[Payload] = []
    witness.subscribe(topic, lambda topic, payload: heard.append(payload))
    writer.publish(topic, payload)
    assert drained(witness, lambda: len(heard) == 1), f"nothing reached {topic}"


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

    assert drained(reader, lambda: len(seen) == 1)
    assert seen[0]["power"] == "on"


def test_event_published_before_a_subscriber_does_not(
    buses: Callable[[], MqttBus],
) -> None:
    writer, witness, reader = buses(), buses(), buses()
    _through(writer, witness, OCCUPIED, {"block": "a"})

    seen: list[str] = []
    reader.subscribe("tc49/#", lambda topic, payload: seen.append(payload["block"]))
    settle(reader)

    assert seen == []

    # And the subscription is live, so the silence above is the event topic
    # not being replayed rather than nothing working.
    writer.publish(OCCUPIED, {"block": "b"})
    assert drained(reader, lambda: seen == ["b"])


def test_a_handler_runs_on_the_thread_thatdrained(
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
    assert until(lambda: POWER in reader.last_values)
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
    assert drained(reader, lambda: len(seen) == 1)

    # The stamp the caller supplied is gone, and what stands is this instant
    # on the clock every process on the broker shares.
    assert before <= seen[0]["at"] <= time.time()
    assert list(seen[0]) == ["at", "power"]


def test_an_event_payload_is_not_stamped(buses: Callable[[], MqttBus]) -> None:
    writer, reader = buses(), buses()
    seen: list[Payload] = []
    reader.subscribe(OCCUPIED, lambda topic, payload: seen.append(payload))

    writer.publish(OCCUPIED, {"block": "a"})
    assert drained(reader, lambda: len(seen) == 1)
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

    assert drained(reader, lambda: all(len(one) == 1 for one in seen.values()))
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

    assert until(lambda: POWER in reader.last_values)
    settle(reader)

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
    settle(reader)
    assert seen == []

    writer.publish(OCCUPIED, {"block": "a"})
    assert drained(reader, lambda: len(seen) == 1)
    assert seen[0] == {"block": "a"}


def test_a_cleared_retained_value_leaves_the_picture(
    buses: Callable[[], MqttBus], raw: paho.Client
) -> None:
    writer, reader = buses(), buses()
    writer.publish(POWER, {"power": "on"})
    reader.subscribe(POWER, lambda topic, payload: None)
    assert until(lambda: POWER in reader.last_values)

    raw.publish(POWER, b"", qos=0, retain=True)

    assert until(lambda: POWER not in reader.last_values)


def test_clearing_takes_the_row_off_the_broker(
    buses: Callable[[], MqttBus], broker: Broker
) -> None:
    """The other half of the row above, from our side: what a reload does to
    the rows of the railroad that left. A client connecting afterwards is
    handed nothing on that topic, which is the whole point — a retained value
    outlives the process that wrote it (ADR-0059 decision 3, ADR-0060)."""
    writer = buses()
    writer.publish(POWER, {"power": "on"})
    assert until(lambda: POWER in writer.last_values)

    writer.clear(POWER)
    assert POWER not in writer.last_values

    late = buses()
    late.subscribe("tc49/#", lambda topic, payload: None)
    settle(late)
    assert POWER not in late.last_values, "the broker still holds the row"


def test_an_event_topic_has_nothing_to_clear(buses: Callable[[], MqttBus]) -> None:
    """Only a state topic is retained, so asking for an event topic is a bug
    in the caller rather than a no-op to absorb."""
    with pytest.raises(ValueError):
        buses().clear(OCCUPIED)


def test_forgetting_drops_the_subscriptions_at_the_broker_too(
    buses: Callable[[], MqttBus],
) -> None:
    """What a reload does to the app that was running: its handlers go, and
    the filters go at the broker with them, so nothing arrives for a railroad
    nobody is running. Subscribing again is also what makes the broker send
    its retained values a second time, which is how what comes next reads
    them."""
    writer, reader = buses(), buses()
    heard: list[str] = []
    reader.subscribe("tc49/#", lambda topic, payload: heard.append(topic))
    writer.publish(OCCUPIED, {"block": "yard_w"})
    assert drained(reader, lambda: heard == [OCCUPIED])

    reader.forget()
    writer.publish(OCCUPIED, {"block": "yard_e"})
    settle(reader)
    assert heard == [OCCUPIED], "a forgotten filter still delivered"

    # And the retained picture comes again to whatever subscribes next.
    writer.publish(POWER, {"power": "on"})
    again: list[str] = []
    reader.subscribe("tc49/#", lambda topic, payload: again.append(topic))
    assert drained(reader, lambda: POWER in again)


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

    assert until(lambda: len(wire) == 1)
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
    assert until(lambda: not bus.connected)
    assert "lost" in capsys.readouterr().err

    assert broker.start()
    # Reconnected on the client's own backoff, whose first step is a second.
    assert bus.wait_connected(timeout=30.0)


def test_a_broker_address_is_a_host_and_a_port() -> None:
    assert address("broker:1883") == ("broker", 1883)


def test_an_ipv6_broker_address_keeps_its_colons_and_loses_its_brackets() -> None:
    """What a connection is opened on is the name, not the written form:
    `getaddrinfo` resolves `::1` and refuses `[::1]`."""
    assert address("[::1]:1883") == ("::1", 1883)


@pytest.mark.parametrize("written", ("broker", "broker:", ":1883", "broker:mqtt"))
def test_an_address_that_is_not_one_is_refused_in_words(written: str) -> None:
    """A person mistyping a flag reads what to write instead, which is what
    the app's command line prints back."""
    with pytest.raises(ValueError, match="<host>:<port>"):
        address(written)
