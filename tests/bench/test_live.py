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
