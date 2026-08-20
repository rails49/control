"""Admission as the sole payload authority (ADR-0034, #107).

A browser publishes on the one inbound topic and the relay checks the topic
and nothing else, so anything at all can arrive on the bus — and after the
relay is deleted nothing stands in front of the dispatcher anyway. It
therefore never raises on a bus payload: what it can address it answers,
what it cannot it drops to the trace, and the railroad keeps ticking either
way.

Driven at the bus, which is exactly what the bridge does with a client's
frame: `publish(INBOUND, payload)` and nothing else.
"""

from collections.abc import Callable
from typing import cast

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bus import Payload
from tc49.lib.inventory import INBOUND
from tests.harness import events, load

GOOD: Payload = {
    "id": "freight_1-1",
    "train": "freight_1",
    "depart": "yard_w.B",
    "dest": ["yard_e.A"],
}

# The shapes that used to end a live session, one of each (#107).
UNREADABLE: list[Payload] = [
    {**GOOD, "id": "bad-1", "train": "ghost"},  # a train the session lacks
    {**GOOD, "id": "bad-2", "dest": ["siding_9.A"]},  # a block the layout lacks
    {"id": "bad-3", "train": "freight_1", "dest": ["yard_e.A"]},  # no depart
    {**GOOD, "id": "bad-4", "dest": "yard_e.A"},  # dest a string, not ends
    cast(Payload, "freight_1 to yard_e"),  # not an object at all
]


@pytest.fixture
def assembly() -> Assembly:
    layout, scenario = load("crossover-yard/meet")
    return assemble_live(layout, scenario)


def submit(assembly: Assembly, payload: Payload) -> None:
    """A client's frame as the bridge puts it on the bus, unchanged."""
    assembly.bus.publish(INBOUND, payload)
    assembly.bus.drain()


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 50) -> None:
    """Run the live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def reason(assembly: Assembly, rid: str) -> str:
    [rejected] = events(assembly.trace, "request_rejected", rid=rid)
    return cast(str, rejected["reason"])


def test_a_train_the_session_does_not_have_is_answered(assembly: Assembly) -> None:
    """Which trains are in the run is a fact only the dispatcher holds, so
    the answer is its own word rather than a crash off the roster."""
    submit(assembly, {**GOOD, "train": "ghost"})
    assert reason(assembly, "freight_1-1") == "unknown_train"


def test_an_arrival_block_the_layout_does_not_have_is_answered(
    assembly: Assembly,
) -> None:
    submit(assembly, {**GOOD, "dest": ["yard_e.A", "siding_9.A"]})
    assert reason(assembly, "freight_1-1") == "unknown_block"


def test_a_departure_block_the_layout_does_not_have_is_answered(
    assembly: Assembly,
) -> None:
    """Not `wrong_origin`: the train is not standing there, but neither is
    anything else — the request names track that does not exist."""
    submit(assembly, {**GOOD, "depart": "siding_9.B"})
    assert reason(assembly, "freight_1-1") == "unknown_block"


def test_a_payload_that_is_not_a_request_is_answered_malformed(
    assembly: Assembly,
) -> None:
    """A readable id and nothing else readable: the one structural reason,
    for a frame that can be addressed but not read."""
    payloads = {
        "bad-1": {"id": "bad-1"},  # the id and nothing else
        "bad-2": {**GOOD, "id": "bad-2", "depart": None},  # no departure end
        "bad-3": {**GOOD, "id": "bad-3", "dest": "yard_e.A"},  # a string, not ends
        "bad-4": {**GOOD, "id": "bad-4", "dest": ["yard_e.A", 7]},  # not all ends
    }
    for rid, payload in payloads.items():
        submit(assembly, cast(Payload, payload))
        assert reason(assembly, rid) == "malformed", payload


def test_a_payload_with_no_readable_id_publishes_nothing(assembly: Assembly) -> None:
    """Every rejection is addressed by id, and a broadcast one that names no
    request is uncorrelatable by construction (ADR-0034)."""
    assembly.bus.drain()  # the startup cascade, so what follows is the answer
    before = len(events(assembly.trace))
    submit(assembly, {"train": "freight_1", "depart": "yard_w.B", "dest": ["yard_e.A"]})
    submit(assembly, cast(Payload, "freight_1 to yard_e"))
    assert events(assembly.trace, "request_rejected") == []
    assert len(events(assembly.trace)) == before + 2  # the two frames, no answer


def test_a_dropped_payload_is_still_verifiable_in_the_trace(
    assembly: Assembly,
) -> None:
    """Dropping is not losing it: the tap subscribes `tc49/#`, so the frame
    is a line by virtue of having been published, and a client bug stays
    diagnosable."""
    submit(assembly, cast(Payload, ["yard_e.A"]))
    [dropped] = events(assembly.trace, "request_submitted")
    assert dropped["payload"] == ["yard_e.A"]


def test_the_session_survives_every_unreadable_payload(assembly: Assembly) -> None:
    """The whole of #107 in one run: each shape in turn, then an honest
    request that runs to completion — the railroad ticked through all of it."""
    for payload in UNREADABLE:
        submit(assembly, payload)
    submit(assembly, GOOD)
    tick_until(
        assembly,
        lambda: bool(events(assembly.trace, "request_completed", rid="freight_1-1")),
    )
    assert events(assembly.trace, "request_completed", rid="freight_1-1")
