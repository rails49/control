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
from tc49.lib.inventory import OFF, ON
from tests.harness import events, live, load, power, press, run


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
    assert first["time"] == 0.0
    assert first["trains"] == {"express_2": "up_e", "freight_1": "yard_w"}
    assert first["locks"] == {"up_e": "express_2", "yard_w": "freight_1"}
    assert first["requests"] == []


def test_a_live_request_carries_what_the_panel_marks_it_with() -> None:
    """A pending request renders as its departure end and its surviving
    arrival ends, so the picture carries both — a snapshot without them draws
    no markers. freight_1's return working is the one that waits: its first
    working launches on admission (ADR-0047), so the return is the request
    the picture holds queued and routeless."""
    trace = run(*load("crossover-yard/meet"))
    live = carried(trace, "freight_1-2")
    assert live
    assert live[0] == {
        "id": "freight_1-2",
        "train": "freight_1",
        "depart": "yard_e.A",
        # dn_w.A survives admission nowhere: entering dn_w through A means
        # coming off yard_w, and yard_w is unreachable from yard_e.
        "dest": ["dn_w.B"],
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
        json.dumps({key: value for key, value in picture.items() if key != "time"})
        for picture in pictures(trace)
    ]
    assert said and all(before != after for before, after in pairwise(said))


def test_the_locks_are_the_lock_table_as_the_dispatcher_holds_it() -> None:
    """The picture is a projection, not a second copy: at every point in the
    run it agrees with the lock and release events that made it."""
    layout, _roster, scenario = load("crossover-yard/meet")
    trace = run(layout, _roster, scenario, Incremental)
    held: dict[str, str] = {}
    for line in events(trace):
        if line["event"] == "lock_granted":
            held.update({resource: line["train"] for resource in line["resources"]})
        elif line["event"] == "lock_released":
            for resource in line["resources"]:
                held.pop(resource, None)
        elif line["event"] == "allocation":
            assert line["locks"] == dict(sorted(held.items()))


def test_a_standing_train_is_crossing_nothing() -> None:
    """`crossing` is the picture's answer to "which trains are between two
    blocks": empty while everything is parked, so an idle railroad draws no
    train on a connection (#151)."""
    trace = run(*load("crossover-yard/meet"))
    assert pictures(trace)[0]["crossing"] == {}
    assert pictures(trace)[-1]["crossing"] == {}


def test_a_crossing_train_is_named_by_the_transit_it_is_on() -> None:
    """A train with a granted move is in the picture twice over: standing in
    the block it has yet to leave, and crossing the transit that takes it out
    of it. The transit is the whole of what marks it as being between blocks
    — a restarted session draws it on the connection and sends a person to
    look (#123) — and `trains` goes on naming the block the sensors last
    confirmed, which is what the dispatcher's own lock table says.
    """
    trace = run(*load("crossover-yard/meet"))
    granted: dict[str, Any] | None = None
    standing: dict[str, str] = {}
    for line in events(trace):
        if line["event"] == "allocation" and granted is None:
            standing = line["trains"]
        elif line["event"] == "move_granted" and granted is None:
            granted = line
        elif line["event"] == "allocation" and granted is not None:
            train = granted["train"]
            assert line["crossing"][train] == granted["transit"]
            assert line["trains"][train] == standing[train] != granted["into"]
            return
    raise AssertionError("no picture followed a granted move")


def picture_after(trace: str, line: dict[str, Any]) -> dict[str, Any]:
    """The first picture published after one trace line."""
    lines = events(trace)
    after = lines[lines.index(line) + 1 :]
    return next(each for each in after if each["event"] == "allocation")


def one(picture: dict[str, Any], rid: str) -> dict[str, Any]:
    [request] = [each for each in picture["requests"] if each["id"] == rid]
    return request


def test_a_request_refused_at_launch_carries_why_until_it_launches() -> None:
    """A page that connects after a `grant_refused` is told why the train
    waits all the same (#1117): the refusal rides on the request in the
    retained picture, as the event carried it, and goes once it launches.
    In the starvation scenario waiter is refused `unsafe` while squatter
    sits idle in the block it wants, and launches once squatter leaves."""
    trace = run(*load("single-track-meet/starvation"), Incremental)
    refused = events(trace, "grant_refused", rid="waiter-1")[0]
    assert refused["reason"] == "unsafe"

    assert one(picture_after(trace, refused), "waiter-1")["refused"] == {
        "reason": "unsafe",
        "obstacles": refused["obstacles"],
    }
    [chosen] = events(trace, "route_chosen", rid="waiter-1")
    assert "refused" not in one(picture_after(trace, chosen), "waiter-1")


def test_an_underway_request_refused_its_next_move_carries_why_until_granted() -> None:
    """The same for a train stopped mid-route: refused its next move, it
    carries the refusal, and the move granted takes it away."""
    trace = run(*load("reversing-loops/saturation"), Incremental)
    lines = events(trace)
    started: set[str] = set()
    for at, line in enumerate(lines):
        if line["event"] == "route_chosen":
            started.add(line["id"])
        if line["event"] == "grant_refused" and line["id"] in started:
            break
    else:
        raise AssertionError("no underway request was refused a move")
    rid = line["id"]
    assert "route" in one(picture_after(trace, line), rid)
    assert one(picture_after(trace, line), rid)["refused"] == {
        "reason": line["reason"],
        "obstacles": line["obstacles"],
    }
    granted = next(
        each
        for each in lines[at:]
        if each["event"] == "move_granted" and each["id"] == rid
    )
    assert "refused" not in one(picture_after(trace, granted), rid)


def test_a_refusal_repeated_with_the_same_obstacles_publishes_no_picture() -> None:
    """A sweep that refuses a request again for the same reason moves
    nothing in the picture, so it publishes none: express_2 wants the block
    freight_1 stands idle in, and the power coming back `on` sweeps it into
    the same refusal."""
    assembly = live("crossover-yard/meet")
    press(
        assembly,
        "tc49/schedule/request_wanted",
        {"train": "express_2", "dest": ["yard_w.B"]},
    )
    [first] = events(assembly.trace, "grant_refused")
    pictured = len(pictures(assembly.trace))

    press(assembly, *power(OFF))
    press(assembly, *power(ON))

    [_, again] = events(assembly.trace, "grant_refused")
    assert (again["reason"], again["obstacles"]) == (
        first["reason"],
        first["obstacles"],
    )
    assert len(pictures(assembly.trace)) == pictured
