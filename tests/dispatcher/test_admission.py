"""Admission as the sole payload authority (ADR-0034, #107).

Anything at all can arrive on the topic requests are written to — the file
scheduler is one publisher, and after the relay is deleted nothing stands in
front of the dispatcher anyway. It therefore never raises on a bus payload:
what it can address it answers, what it cannot it drops to the trace, and the
railroad keeps ticking either way. A browser no longer reaches it: the panel
writes gestures and the scheduler composes (ADR-0036), which hardens the path
rather than replacing this.

Driven at the bus: `publish(REQUESTS, payload)` and nothing else.
"""

from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, assemble_live, placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib import durable
from tc49.lib.bus import Bus, Payload
from tc49.lib.scenario import Scenario, TrainSpec
from tests.harness import events, load, stock

REQUESTS = "tc49/dispatch/request_submitted"

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
]


@pytest.fixture
def assembly() -> Assembly:
    layout, roster, scenario = load("crossover-yard/meet")
    return assemble_live(layout, roster, scenario.trains)


def submit(assembly: Assembly, payload: Payload) -> None:
    """A request as a publisher puts it on the bus, unchanged."""
    assembly.bus.publish(REQUESTS, payload)
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
    submit(assembly, {"id": None, "train": "freight_1", "dest": ["yard_e.A"]})
    assert events(assembly.trace, "request_rejected") == []
    assert len(events(assembly.trace)) == before + 2  # the two frames, no answer


def test_a_payload_that_is_not_an_object_at_all_is_dropped() -> None:
    """Read rather than trusted, to the bottom: nothing in admission
    subscripts a payload it has not read first. Driven without the trace tap,
    which holds the apps to the inventory and would refuse this line — an
    honest publisher cannot produce it, and the one that can is a client, on
    the topic the tap records verbatim."""
    layout, roster, scenario = load("crossover-yard/meet")
    bus = Bus()
    seen: list[Payload] = []
    bus.subscribe("tc49/dispatch/request_rejected", lambda _, p: seen.append(p))
    Dispatcher(
        bus, layout, roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    bus.publish(REQUESTS, cast(Payload, "freight_1 to yard_e"))
    bus.drain()
    assert seen == []


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


def test_a_request_for_a_train_off_the_layout_is_answered(tmp_path: Path) -> None:
    """A known train that stands nowhere has no origin to depart from, so the
    request is answered rather than indexed for (ADR-0039, #175).

    Adoption takes the picture a train at a time (#164), so a train whose
    picture block *and* whose starting block are both taken comes up off the
    layout. That is the first state in which a known train has no block, and
    every launch lookup reads `block_of` expecting one — so without this the
    answer is a `KeyError` on a payload a browser can send, which is the one
    thing this module exists to rule out.

    `leviathan` was added to the roster since the picture was taken and
    stands where the picture left `freight_1`; `railcar_3` sits in
    `freight_1`'s own starting block.
    """
    state = tmp_path / "session.json"
    durable.write(
        state,
        {
            "tc49/dispatch/state/allocation": {
                "trains": {"freight_1": "dn_e", "railcar_3": "yard_w"},
                "crossing": {},
                "locks": {},
                "requests": [],
            }
        },
    )
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        name="unplaced",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec("yard_w", "B"),
            "railcar_3": TrainSpec("dn_w", "A"),
            "leviathan": TrainSpec("dn_e", "A"),
        },
        requests=(),
    )
    assembly = assemble_live(
        layout,
        stock(freight_1=1100, railcar_3=600, leviathan=2000),
        scenario.trains,
        state=state,
    )
    assembly.bus.drain()

    submit(assembly, GOOD)

    assert reason(assembly, "freight_1-1") == "no_origin"
