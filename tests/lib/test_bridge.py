"""The bridge, driven by a real WebSocket client over an in-process bus.

The relay's seam is its entire spec (#71): every `tc49/#` event goes out as
a frame carrying topic and payload, and a frame on one of the inbound topics
comes in as the event. The bus stays single-threaded — the test thread drains
it, the way the simulator's loop does in a live session — so inbound
assertions poll drain-and-check rather than sleep and hope.
"""

import json
import logging
import socket
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.lib.bridge import Bridge
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import INBOUND, is_state_topic

WANTED = "tc49/ui/request_wanted"
REVERSAL = "tc49/ui/reversal_wanted"
RUN = "tc49/ui/run_wanted"
PLACEMENT = "tc49/ui/placement_wanted"

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
    bus.publish("tc49/layout/boundary", {"boundary": 3})
    bus.publish("tc49/dispatch/lock_granted", {"train": "t1", "resources": ["a"]})
    bus.drain()
    assert receive(client) == {
        "topic": "tc49/layout/boundary",
        "payload": {"boundary": 3},
    }
    assert receive(client) == {
        "topic": "tc49/dispatch/lock_granted",
        "payload": {"train": "t1", "resources": ["a"]},
    }


def test_a_request_wanted_frame_becomes_the_event(
    bus: Bus, client: ClientConnection
) -> None:
    seen: list[Payload] = []
    bus.subscribe(WANTED, lambda topic, payload: seen.append(payload))
    wanted = {"train": "t1", "dest": ["b.A"]}
    client.send(json.dumps({"topic": WANTED, "payload": wanted}))
    drain_until(bus, lambda: bool(seen))
    assert seen == [wanted]


def test_a_reversal_wanted_frame_becomes_the_event(
    bus: Bus, client: ClientConnection
) -> None:
    """The second leaf a page may write (#124): the relay publishes the topic
    the frame names rather than the one topic it used to know."""
    seen: list[Payload] = []
    bus.subscribe(REVERSAL, lambda topic, payload: seen.append(payload))
    client.send(json.dumps({"topic": REVERSAL, "payload": {"train": "t1"}}))
    drain_until(bus, lambda: bool(seen))
    assert seen == [{"train": "t1"}]


def test_the_inbound_topics_are_the_ui_roles_own_event_leaves() -> None:
    """What a broker's ACL would grant a page is `tc49/ui/#`, and the role is
    what says so (ADR-0035): the set is read off the inventory rather than
    listed, so a leaf added there is inbound without a second edit.

    The equality below is where that stops being silent (#158). Deriving the
    set means a new `tc49/ui` row widens the browser's write surface with no
    diff line saying so; pinning it exactly means the row fails here instead,
    and whoever adds it grants the write deliberately by naming it. Do not
    relax this to a subset check.

    Event leaves only. A role with concurrent instances may not write a state
    topic, and the bridge relies on it: a client's frame is published from
    that client's own handler thread, and a state topic would write the bus's
    last-value map from there."""
    assert INBOUND == {WANTED, REVERSAL, RUN, PLACEMENT}
    assert not any(is_state_topic(topic) for topic in INBOUND)
    assert is_state_topic("tc49/ui/state/throttle")  # what the filter keeps out


def test_the_bridge_refuses_every_topic_outside_the_ui_role(
    bus: Bus, client: ClientConnection
) -> None:
    """The `tc49/ui` leaves are the only inbound path (#67): a client that
    tries to drive a train or fake a sensor gets a refusal frame naming the
    topic and what it may write instead, and nothing reaches the bus."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    client.send(json.dumps({"topic": "tc49/drive/move", "payload": {"train": "t1"}}))
    refusal = receive(client)
    assert "tc49/drive/move" in refusal["error"]
    assert WANTED in refusal["error"] and REVERSAL in refusal["error"]
    bus.drain()
    assert seen == []


def test_a_topic_that_is_not_a_string_is_refused_rather_than_raised(
    bus: Bus, client: ClientConnection
) -> None:
    """A browser may send anything, and a membership test against a set is
    not total: an unhashable topic would raise in the handler thread instead
    of answering the client."""
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: seen.append((topic, payload)))
    client.send(json.dumps({"topic": ["tc49/ui/request_wanted"], "payload": {}}))
    assert "error" in receive(client)
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
        bus.publish("tc49/layout/boundary", {"boundary": 0})
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
        bus.publish("tc49/layout/boundary", {"boundary": 7})
        bus.drain()
        assert receive(late)["topic"] == "tc49/dispatch/state/aspects"
        assert receive(late)["payload"] == {"boundary": 7}


def test_an_event_topic_is_not_replayed_to_a_joining_client(
    bus: Bus, bridge: Bridge
) -> None:
    """State topics excepted, there is no replay for a late subscriber
    (SYSTEM.md): the relay forwards frames it would have forwarded had the
    client been there, and holds no backlog."""
    bus.publish("tc49/layout/boundary", {"boundary": 1})
    bus.publish("tc49/dispatch/state/aspects", {"aspects": {}})
    bus.drain()
    with connect(f"ws://127.0.0.1:{bridge.port}") as late:
        settled(bridge, 1)
        assert receive(late)["topic"] == "tc49/dispatch/state/aspects"
        bus.publish("tc49/layout/boundary", {"boundary": 2})
        bus.drain()
        assert receive(late)["payload"] == {"boundary": 2}


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
        # The socket goes, no close frame sent. Shut it down first: the client
        # reads on a background thread, and on Linux closing an fd another
        # thread is blocked in recv() on sends no FIN, so the bridge would
        # never see the departure. macOS tears the socket down either way.
        client.socket.shutdown(socket.SHUT_RDWR)
        client.socket.close()
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
        bus.publish("tc49/layout/boundary", {"boundary": 1})
        bus.drain()  # the gone client is skipped, the live one served
        assert receive(survivor)["payload"] == {"boundary": 1}
