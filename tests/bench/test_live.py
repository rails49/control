"""The live-session assembly (#71), at the assembly-over-the-bus seam.

`assemble_live` is the wiring `tc49 live` runs: no file scheduler, the
bridge the only way in. The tests here attach a real bridge and client to
that assembly and walk the whole loop — a frame in, the dispatcher's answer
and the run's events back out over the same socket — pacing the simulator
with an injected time source, never the wall clock.
"""

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bridge import INBOUND, Bridge
from tests.harness import events, load

TIMEOUT = 5.0


@pytest.fixture
def assembly() -> Assembly:
    layout, scenario = load("crossover-yard/meet")
    return assemble_live(layout, scenario)


@pytest.fixture
def bridge(assembly: Assembly) -> Iterator[Bridge]:
    bridge = Bridge(assembly.bus)
    yield bridge
    bridge.close()


@pytest.fixture
def client(bridge: Bridge) -> Iterator[ClientConnection]:
    with connect(f"ws://127.0.0.1:{bridge.port}") as connection:
        deadline = time.monotonic() + TIMEOUT
        while bridge.connections == 0:  # registration follows the handshake
            assert time.monotonic() < deadline
            time.sleep(0.01)
        yield connection


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 50) -> None:
    """Run the live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def frames_until(client: ClientConnection, leaf: str) -> list[dict[str, Any]]:
    """Received frames up to and including the first with that event leaf."""
    received: list[dict[str, Any]] = []
    while True:
        frame = json.loads(client.recv(timeout=TIMEOUT))
        received.append(frame)
        if frame["topic"].rsplit("/", 1)[-1] == leaf:
            return received


def submit(
    client: ClientConnection, assembly: Assembly, payload: dict[str, Any]
) -> None:
    """Send a request frame and drain until it lands on the bus — the client
    writes from its own thread, so arrival is a wait, not a given."""
    client.send(json.dumps({"topic": INBOUND, "payload": payload}))
    deadline = time.monotonic() + TIMEOUT
    while not events(assembly.trace, "request_submitted", rid=payload["id"]):
        assert time.monotonic() < deadline, "the frame never reached the bus"
        assembly.bus.drain()
        time.sleep(0.01)


def test_the_file_requests_are_never_released(assembly: Assembly) -> None:
    """crossover-yard/meet schedules three workings from tick 0; in a live
    session the scenario contributes stock, placement, and facing only
    (ADR-0016), so nothing is submitted and the railroad just ticks."""
    tick_until(assembly, lambda: False, limit=10)
    assert events(assembly.trace, "tick")
    assert events(assembly.trace, "request_submitted") == []
    assert events(assembly.trace, "route_chosen") == []


def test_a_submitted_frame_is_answered_and_run_over_the_same_socket(
    assembly: Assembly, client: ClientConnection
) -> None:
    submit(
        client,
        assembly,
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A", "yard_e.B"],
        },
    )
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_completed", rid="freight_1-1")),
    )
    received = frames_until(client, "request_completed")
    leaves = [frame["topic"].rsplit("/", 1)[-1] for frame in received]
    assert "request_admitted" in leaves  # the dispatcher's answer
    assert "route_chosen" in leaves  # then the committed route
    assert received[-1]["payload"] == {"id": "freight_1-1"}


def test_a_rejection_comes_back_with_its_reason(
    assembly: Assembly, client: ClientConnection
) -> None:
    """Departing through yard_w.A, the terminal's outer end: no route can
    exist, and the panel's filter-free drag (#67) relies on this answer
    arriving rather than on the panel pre-judging it."""
    submit(
        client,
        assembly,
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.A",
            "dest": ["dn_e.A"],
        },
    )
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_rejected", rid="freight_1-1")),
    )
    [rejection] = [
        frame
        for frame in frames_until(client, "request_rejected")
        if frame["topic"].rsplit("/", 1)[-1] == "request_rejected"
    ]
    assert rejection["payload"]["reason"] == "unreachable"


def test_a_stale_departure_is_answered_and_the_session_lives(
    assembly: Assembly, client: ClientConnection
) -> None:
    """A drag composed while a train is moving can still name a block it has
    left by the time the request lands (ADR-0021), and a client is untrusted
    besides. That is an ordinary bad request: the dispatcher answers it and
    the railroad keeps ticking (#73)."""
    submit(
        client,
        assembly,
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_completed", rid="freight_1-1")),
    )
    submit(  # the stale drag: freight_1 stands in yard_e now, not yard_w
        client,
        assembly,
        {
            "id": "freight_1-2",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_w.A"],
        },
    )
    [rejected] = events(assembly.trace, "request_rejected", rid="freight_1-2")
    assert rejected["reason"] == "wrong_origin"
    ticks = len(events(assembly.trace, "tick"))
    tick_until(assembly, lambda: False, limit=3)
    assert len(events(assembly.trace, "tick")) > ticks


def test_a_reloaded_page_is_served_the_picture_and_answered_again(
    assembly: Assembly, bridge: Bridge, client: ClientConnection
) -> None:
    """#106's own reproduction, over the socket.

    A page submits and goes away. The page that replaces it joins a session
    already running, so it is served the run's picture — where the train
    stands and what it is running — instead of nothing, and its own drag is
    answered. The id it mints is its own (ADR-0033): the same one again would
    be dropped at the top of admission, which is what left the marker stuck in
    "requested" for good.
    """
    submit(
        client,
        assembly,
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "route_chosen", rid="freight_1-1")),
    )
    client.close()  # the tab is reloaded: no close handshake, just gone

    with connect(f"ws://127.0.0.1:{bridge.port}") as reloaded:
        deadline = time.monotonic() + TIMEOUT
        while bridge.connections == 0:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        [picture] = [
            frame["payload"]
            for frame in frames_until(reloaded, "allocation")
            if frame["topic"].rsplit("/", 1)[-1] == "allocation"
        ]
        assert picture["trains"]["freight_1"]  # somewhere, and the page knows it
        assert [request["id"] for request in picture["requests"]] == ["freight_1-1"]

        submit(  # the same train, dragged again from a page that minted afresh
            reloaded,
            assembly,
            {
                "id": "freight_1-9f31c0a2-1",
                "train": "freight_1",
                "depart": f"{picture['trains']['freight_1']}.B",
                "dest": ["dn_w.A"],
            },
        )
    answered = [
        line["event"]
        for line in events(assembly.trace, rid="freight_1-9f31c0a2-1")
        if line["event"] in ("request_admitted", "request_rejected")
    ]
    assert answered, "the drag got no answer at all"
