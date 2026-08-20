"""The live-session assembly (#71), at the assembly-over-the-bus seam.

`assemble_live` is the wiring `tc49 live` runs: the timetable off, the bridge
the only way in. The tests here attach a real bridge and client to that
assembly and walk the whole loop — a gesture in, the request the scheduler
composes from it, the dispatcher's answer and the run's events back out over
the same socket — pacing the simulator with an injected time source, never
the wall clock.

The client sends `{train, dest}` and nothing else: the id and the departure
end are the scheduler's (ADR-0036), so a test that wants to name a request
reads the id off the trace rather than choosing one.
"""

import json
import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bridge import Bridge
from tc49.lib.bus import Payload
from tc49.lib.inventory import INBOUND
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


def drag(
    client: ClientConnection, assembly: Assembly, train: str, dest: list[str]
) -> str:
    """Send a gesture frame, drain until the request it composes lands on the
    bus, and answer with the id the scheduler minted for it — the client
    writes from its own thread, so arrival is a wait, not a given."""
    before = len(events(assembly.trace, "request_submitted"))
    client.send(
        json.dumps({"topic": INBOUND, "payload": {"train": train, "dest": dest}})
    )
    deadline = time.monotonic() + TIMEOUT
    while len(events(assembly.trace, "request_submitted")) == before:
        assert time.monotonic() < deadline, "the gesture composed nothing"
        assembly.bus.drain()
        time.sleep(0.01)
    return cast(str, events(assembly.trace, "request_submitted")[-1]["id"])


# Every shape ADR-0036 drops: read rather than trusted, and dropped in
# silence, a gesture carrying no id to address an answer to.
UNCOMPOSABLE: list[object] = [
    "freight_1 to yard_e",  # not an object at all
    {},  # neither field
    {"train": None, "dest": ["yard_e.A"]},  # no train
    {"train": "freight_1", "dest": "yard_e.A"},  # dest a string, not ends
    {"train": "freight_1", "dest": ["yard_e.A", 7]},  # not all ends
    {"train": "ghost", "dest": ["yard_e.A"]},  # a train it holds no facing for
]


def test_the_timetable_is_off_and_facing_is_still_published(
    assembly: Assembly,
) -> None:
    """crossover-yard/meet schedules three workings from tick 0; a live
    session runs the same scheduler with the timetable off (ADR-0036), so
    nothing is submitted and the railroad just ticks. Facing is not off with
    it: it is the scenario's placement, and a joining page has no other
    source for a direction arrow."""
    tick_until(assembly, lambda: False, limit=10)
    assert events(assembly.trace, "tick")
    assert events(assembly.trace, "request_submitted") == []
    assert events(assembly.trace, "route_chosen") == []
    [placed] = events(assembly.trace, "facing")
    assert placed["facing"] == {"express_2": "up_e.A", "freight_1": "yard_w.B"}


def test_the_session_survives_every_gesture_it_cannot_compose(
    assembly: Assembly,
) -> None:
    """#107's lesson at the scheduler (ADR-0036): anything at all can be
    published where a person's page writes, so each uncomposable shape in
    turn, then an honest drag that runs to completion — the railroad ticked
    through all of it, nothing was published in answer, and every frame is a
    line in the trace by virtue of having been published."""
    assembly.bus.drain()  # the startup cascade, so what follows is the answer
    before = len(events(assembly.trace))
    for payload in UNCOMPOSABLE:
        assembly.bus.publish(INBOUND, cast(Payload, payload))
        assembly.bus.drain()
    assert events(assembly.trace, "request_submitted") == []
    assert len(events(assembly.trace)) == before + len(UNCOMPOSABLE)

    assembly.bus.publish(INBOUND, {"train": "freight_1", "dest": ["yard_e.A"]})
    assembly.bus.drain()
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_completed", rid="freight_1-1")),
    )
    assert events(assembly.trace, "request_completed", rid="freight_1-1")


def test_a_gesture_is_composed_answered_and_run_over_the_same_socket(
    assembly: Assembly, client: ClientConnection
) -> None:
    """The whole loop from a drag: the frame names a train and a block's two
    ends, the scheduler supplies the id and the departure end off facing, and
    everything the dispatcher then says comes back over the same socket."""
    rid = drag(client, assembly, "freight_1", ["yard_e.A", "yard_e.B"])
    assert rid == "freight_1-1"
    [composed] = events(assembly.trace, "request_submitted", rid=rid)
    assert composed["depart"] == "yard_w.B"  # facing, which the drag never named

    tick_until(
        assembly, lambda: bool(events(assembly.trace, "request_completed", rid=rid))
    )
    received = frames_until(client, "request_completed")
    leaves = [frame["topic"].rsplit("/", 1)[-1] for frame in received]
    assert "request_submitted" in leaves  # what the gesture became
    assert "request_admitted" in leaves  # the dispatcher's answer
    assert "route_chosen" in leaves  # then the committed route
    assert received[-1]["payload"] == {"id": rid}


def test_a_rejection_comes_back_with_its_reason(
    assembly: Assembly, client: ClientConnection
) -> None:
    """Dropped on the outer third of a terminal block's blind end: yard_e.B
    is an end nothing connects to, so no train can enter through it. The
    filter-free drag (#67) relies on this answer arriving rather than on the
    panel pre-judging it, and the scheduler judges nothing either."""
    rid = drag(client, assembly, "freight_1", ["yard_e.B"])
    tick_until(
        assembly, lambda: bool(events(assembly.trace, "request_rejected", rid=rid))
    )
    [rejection] = [
        frame
        for frame in frames_until(client, "request_rejected")
        if frame["topic"].rsplit("/", 1)[-1] == "request_rejected"
    ]
    assert rejection["payload"]["reason"] == "no_entry"


def test_a_drag_on_a_moving_train_is_answered_and_the_session_lives(
    assembly: Assembly, client: ClientConnection
) -> None:
    """`wrong_origin` still stands (ADR-0021). A grant names the next block a
    tick before the sensor does, and facing follows the grant, so a drag on a
    train that is not idle composes a departure end in a block the dispatcher
    does not yet have it in. The scheduler judges none of that — it composes
    and submits like any other gesture — and the dispatcher answers, the
    railroad ticking on around it (#73)."""
    first = drag(client, assembly, "freight_1", ["yard_e.A"])
    tick_until(
        assembly, lambda: bool(events(assembly.trace, "move_granted", rid=first))
    )
    second = drag(client, assembly, "freight_1", ["dn_w.A"])
    [composed] = events(assembly.trace, "request_submitted", rid=second)
    assert composed["depart"] == "dn_w.B"  # where the grant is taking it
    [rejected] = events(assembly.trace, "request_rejected", rid=second)
    assert rejected["reason"] == "wrong_origin"
    ticks = len(events(assembly.trace, "tick"))
    tick_until(assembly, lambda: False, limit=3)
    assert len(events(assembly.trace, "tick")) > ticks


def test_a_reloaded_page_is_served_the_picture_and_answered_again(
    assembly: Assembly, bridge: Bridge, client: ClientConnection
) -> None:
    """#106's own reproduction, over the socket.

    A page drags and goes away. The page that replaces it joins a session
    already running, so it is served the run's picture — where the train
    stands and what it is running — instead of nothing, and its own drag is
    answered. Ids are no longer the page's business at all (ADR-0036): a
    reload cannot re-use one the dispatcher has seen because it mints none,
    which is what left the marker stuck in "requested" for good.
    """
    rid = drag(client, assembly, "freight_1", ["yard_e.A"])
    tick_until(assembly, lambda: bool(events(assembly.trace, "route_chosen", rid=rid)))
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
        assert [request["id"] for request in picture["requests"]] == [rid]

        again = drag(reloaded, assembly, "freight_1", ["dn_w.A"])
    assert again != rid  # the counter is the scheduler's and never rewinds
    answered = [
        line["event"]
        for line in events(assembly.trace, rid=again)
        if line["event"] in ("request_admitted", "request_rejected")
    ]
    assert answered, "the drag got no answer at all"
