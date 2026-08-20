"""The picture a joining client is served (ADR-0032, #106).

`tc49/dispatch/state/allocation` is a projection of the lock table, published
beside its source exactly as `state/aspects` is: where each train stands, what
is locked and to whom, and the live requests with the route each committed
one is running. A client that connects to an idle railroad draws from this
and from nothing else, so what it says has to be true the moment it is said
and complete enough to draw.
"""

import json
from itertools import pairwise
from typing import Any

from tc49.dispatcher import Incremental
from tests.harness import events, load, run


def pictures(trace: str) -> list[dict[str, Any]]:
    return events(trace, "allocation")


def carried(trace: str, rid: str) -> list[dict[str, Any]]:
    """Every appearance of one request across the run's pictures."""
    found: list[dict[str, Any]] = []
    for picture in pictures(trace):
        live: list[dict[str, Any]] = picture["requests"]
        found += [request for request in live if request["id"] == rid]
    return found


def test_the_picture_opens_on_the_scenario_placement() -> None:
    """A client joining before anything has moved still draws the trains:
    placement is standing locks, and the first picture carries them."""
    trace = run(*load("crossover-yard/meet"))
    first = pictures(trace)[0]
    assert first["boundary"] == 0
    assert first["trains"] == {"express_2": "up_e", "freight_1": "yard_w"}
    assert first["locks"] == {"up_e": "express_2", "yard_w": "freight_1"}
    assert first["requests"] == []


def test_a_live_request_carries_what_the_panel_marks_it_with() -> None:
    """A pending request renders as its departure end and its surviving
    arrival ends, so the picture carries both — a snapshot without them draws
    no markers."""
    trace = run(*load("crossover-yard/meet"))
    live = carried(trace, "freight_1-1")
    assert live
    assert live[0] == {
        "id": "freight_1-1",
        "train": "freight_1",
        "depart": "yard_w.B",
        "dest": ["yard_e.A"],
    }


def test_a_committed_request_carries_the_route_it_is_running() -> None:
    """The panel renders a committed route from the request that owns it
    (ADR-0032), so the route rides in the picture beside the request."""
    trace = run(*load("crossover-yard/meet"))
    committed = [
        request for request in carried(trace, "freight_1-1") if "route" in request
    ]
    [chosen] = events(trace, "route_chosen", rid="freight_1-1")
    assert committed[0]["route"] == chosen["route"]


def test_a_completed_request_leaves_the_picture() -> None:
    trace = run(*load("crossover-yard/meet"))
    last = pictures(trace)[-1]
    assert last["requests"] == []


def test_the_picture_is_republished_only_when_it_changes() -> None:
    """Same discipline as the aspects topic: a last value that repeats itself
    is a line in every trace and a frame to every client, for no news."""
    trace = run(*load("crossover-yard/meet"), Incremental)
    said = [
        json.dumps({key: value for key, value in picture.items() if key != "boundary"})
        for picture in pictures(trace)
    ]
    assert said and all(before != after for before, after in pairwise(said))


def test_the_locks_are_the_lock_table_as_the_dispatcher_holds_it() -> None:
    """The picture is a projection, not a second copy: at every point in the
    run it agrees with the lock and release events that made it."""
    layout, scenario = load("crossover-yard/meet")
    trace = run(layout, scenario, Incremental)
    held: dict[str, str] = {}
    for line in events(trace):
        if line["event"] == "lock_granted":
            held.update({resource: line["train"] for resource in line["resources"]})
        elif line["event"] == "lock_released":
            for resource in line["resources"]:
                held.pop(resource, None)
        elif line["event"] == "allocation":
            assert line["locks"] == dict(sorted(held.items()))
