"""The bridge, driven by a real WebSocket client over an in-process bus.

The relay's seam is its entire spec (#71): every `tc49/#` event goes out as
a frame carrying topic and payload, and a `request_wanted` frame comes in as
the event. The bus stays single-threaded — the test thread drains it, the
way the simulator's loop does in a live session — so inbound assertions poll
drain-and-check rather than sleep and hope.
"""

import json
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.lib.bridge import Bridge
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import INBOUND

TIMEOUT = 5.0  # generous: a loaded CI box, not a slow relay


@pytest.fixture
def bus() -> Bus:
    return Bus()


@pytest.fixture
def bridge(bus: Bus) -> Iterator[Bridge]:
    bridge = Bridge(bus)  # port 0: the OS picks a free one
    yield bridge
    bridge.close()


def settled(bridge: Bridge, clients: int) -> None:
    """Wait for the bridge to register `clients` connections: a handshake
    completes client-side moments before the server registers it, so a test
    that publishes straight after connecting would race the relay."""
    deadline = time.monotonic() + TIMEOUT
    while bridge.connections != clients:
        if time.monotonic() > deadline:
            raise TimeoutError(f"never saw {clients} client(s) registered")
        time.sleep(0.01)


@pytest.fixture
def client(bridge: Bridge) -> Iterator[ClientConnection]:
    with connect(f"ws://127.0.0.1:{bridge.port}") as connection:
        settled(bridge, 1)
        yield connection


def receive(client: ClientConnection) -> dict[str, Any]:
    return json.loads(client.recv(timeout=TIMEOUT))


def drain_until(bus: Bus, done: Callable[[], bool]) -> None:
    """Drain the bus the way the live loop would, until `done` or timeout."""
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        bus.drain()
        if done():
            return
        time.sleep(0.01)
    raise TimeoutError("the frame never reached the bus")


def test_every_bus_event_arrives_as_a_frame(bus: Bus, client: ClientConnection) -> None:
    bus.publish("tc49/layout/tick", {"tick": 3})
    bus.publish("tc49/dispatch/lock_granted", {"train": "t1", "resources": ["a"]})
    bus.drain()
    assert receive(client) == {"topic": "tc49/layout/tick", "payload": {"tick": 3}}
    assert receive(client) == {
        "topic": "tc49/dispatch/lock_granted",
        "payload": {"train": "t1", "resources": ["a"]},
    }


def test_a_request_wanted_frame_becomes_the_event(
    bus: Bus, client: ClientConnection
) -> None:
    seen: list[Payload] = []
    bus.subscribe(INBOUND, lambda topic, payload: seen.append(payload))
    wanted = {"train": "t1", "dest": ["b.A"]}
    client.send(json.dumps({"topic": INBOUND, "payload": wanted}))
    drain_until(bus, lambda: bool(seen))
    assert seen == [wanted]


def test_the_bridge_refuses_everything_but_request_wanted(
    bus: Bus, client: ClientConnection
) -> None:
    """`request_wanted` is the only inbound path (#67): a client that
    tries to drive a train or fake a sensor gets a refusal frame naming the
    topic, and nothing reaches the bus."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    client.send(json.dumps({"topic": "tc49/drive/cross", "payload": {"train": "t1"}}))
    refusal = receive(client)
    assert "tc49/drive/cross" in refusal["error"]
    bus.drain()
    assert seen == []


def test_a_request_submitted_frame_is_refused_like_any_other(
    bus: Bus, client: ClientConnection
) -> None:
    """The browser writes gestures and never requests (ADR-0036). A page
    that submitted one directly would be a second minter of ids and a second
    holder of facing, which is the whole of what moving the scheduler out of
    the browser removes — so the single-minter claim stops being an intention
    and becomes something the topic check enforces."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    request = {"id": "t1-1", "train": "t1", "depart": "a.B", "dest": ["b.A"]}
    client.send(
        json.dumps({"topic": "tc49/schedule/request_submitted", "payload": request})
    )
    refusal = receive(client)
    assert "tc49/schedule/request_submitted" in refusal["error"]
    bus.drain()
    assert seen == []


def test_a_frame_that_is_not_json_gets_an_error_back(
    bus: Bus, client: ClientConnection
) -> None:
    client.send("not json")
    assert "error" in receive(client)


def test_a_second_client_hears_the_same_events(
    bus: Bus, bridge: Bridge, client: ClientConnection
) -> None:
    with connect(f"ws://127.0.0.1:{bridge.port}") as second:
        settled(bridge, 2)
        bus.publish("tc49/layout/tick", {"tick": 0})
        bus.drain()
        assert receive(client) == receive(second)


def test_a_client_connecting_late_is_served_each_state_topics_last_value(
    bus: Bus, bridge: Bridge
) -> None:
    """A panel joining a running session sees nothing until something moves,
    unless the relay hands it what a late subscriber is owed (ADR-0032). The
    bus promises a state topic delivers its last value; a real broker delivers
    it the moment a client subscribes, and the relay must not be weaker."""
    bus.publish("tc49/dispatch/state/aspects", {"aspects": {"a.B": "stop"}})
    bus.publish("tc49/dispatch/state/allocation", {"trains": {"t1": "a"}})
    bus.drain()
    with connect(f"ws://127.0.0.1:{bridge.port}") as late:
        settled(bridge, 1)
        assert receive(late) == {
            "topic": "tc49/dispatch/state/aspects",
            "payload": {"aspects": {"a.B": "stop"}},
        }
        assert receive(late) == {
            "topic": "tc49/dispatch/state/allocation",
            "payload": {"trains": {"t1": "a"}},
        }


def test_the_last_values_come_before_any_live_frame(bus: Bus, bridge: Bridge) -> None:
    """Order is the whole point: a picture arriving after the events that
    have already moved on from it would undo them."""
    bus.publish("tc49/dispatch/state/aspects", {"aspects": {"a.B": "clear"}})
    bus.drain()
    with connect(f"ws://127.0.0.1:{bridge.port}") as late:
        settled(bridge, 1)
        bus.publish("tc49/layout/tick", {"tick": 7})
        bus.drain()
        assert receive(late)["topic"] == "tc49/dispatch/state/aspects"
        assert receive(late)["payload"] == {"tick": 7}


def test_an_event_topic_is_not_replayed_to_a_joining_client(
    bus: Bus, bridge: Bridge
) -> None:
    """State topics excepted, there is no replay for a late subscriber
    (SYSTEM.md): the relay forwards frames it would have forwarded had the
    client been there, and holds no backlog."""
    bus.publish("tc49/layout/tick", {"tick": 1})
    bus.publish("tc49/dispatch/state/aspects", {"aspects": {}})
    bus.drain()
    with connect(f"ws://127.0.0.1:{bridge.port}") as late:
        settled(bridge, 1)
        assert receive(late)["topic"] == "tc49/dispatch/state/aspects"
        bus.publish("tc49/layout/tick", {"tick": 2})
        bus.drain()
        assert receive(late)["payload"] == {"tick": 2}


def test_a_client_that_vanishes_leaves_quietly(
    bus: Bus, bridge: Bridge, caplog: pytest.LogCaptureFixture
) -> None:
    """A reloaded or discarded browser tab goes without a close handshake.
    That is a client leaving, and it must not put a traceback in the session's
    log — the log is what an operator running `tc49 live` reads. It can go
    while it is being served the last values, too, which is why that send sits
    inside the same guard."""
    bus.publish("tc49/dispatch/state/aspects", {"aspects": {}})
    bus.drain()
    with caplog.at_level(logging.ERROR):
        client = connect(f"ws://127.0.0.1:{bridge.port}")
        settled(bridge, 1)
        client.socket.close()  # the socket goes, no close frame sent
        settled(bridge, 0)
    assert caplog.records == []


def test_a_departed_client_does_not_take_the_bridge_down(
    bus: Bus, bridge: Bridge
) -> None:
    with connect(f"ws://127.0.0.1:{bridge.port}"):
        settled(bridge, 1)  # connect, say nothing, hang up
    settled(bridge, 0)
    with connect(f"ws://127.0.0.1:{bridge.port}") as survivor:
        settled(bridge, 1)
        bus.publish("tc49/layout/tick", {"tick": 1})
        bus.drain()  # the gone client is skipped, the live one served
        assert receive(survivor)["payload"] == {"tick": 1}
