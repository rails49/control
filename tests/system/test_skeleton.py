"""The walking skeleton: crossover-yard/meet end-to-end under FullRoute."""

import json

from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout
from tc49.lib.rejection import Reason
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tests.harness import events, load, run


def test_meet_completes_all_requests_and_quiesces() -> None:
    trace = run(*load("crossover-yard/meet"))
    completed = {line["id"] for line in events(trace, "request_completed")}
    assert completed == {"freight_1-1", "express_2-1", "freight_1-2"}


def test_meet_trace_carries_each_lifecycle_correlated_by_id() -> None:
    trace = run(*load("crossover-yard/meet"))
    for rid in ("freight_1-1", "express_2-1", "freight_1-2"):
        leaves = [line["event"] for line in events(trace, rid=rid)]
        assert leaves[0] == "request_submitted"
        assert leaves[1] == "request_admitted"
        assert leaves.index("route_chosen") < leaves.index("move_granted")
        assert leaves[-1] == "request_completed"
    startup = [line for line in events(trace, "lock_granted") if line["boundary"] == 0]
    assert {line["train"] for line in startup} >= {"freight_1", "express_2"}


def test_meet_traced_twice_is_byte_identical() -> None:
    layout, scenario = load("crossover-yard/meet")
    assert run(layout, scenario).encode() == run(layout, scenario).encode()


def test_two_stage_admission_records_no_entry_pruning() -> None:
    trace = run(*load("crossover-yard/meet"))
    [admitted] = events(trace, "request_admitted", rid="freight_1-1")
    assert admitted["dest"] == ["yard_e.A"]
    assert admitted["pruned"] == [{"end": "yard_e.B", "reason": "no_entry"}]


def test_no_fit_pruning_rejects_at_admission() -> None:
    layout, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "long",
        "crossover-yard",
        {"leviathan": TrainSpec(2000, "up_w", "B")},
        (RequestSpec("leviathan", "up_w.B", ("yard_e",), 0),),
    )
    trace = run(layout, scenario)
    [rejected] = events(trace, "request_rejected")
    assert rejected["id"] == "leviathan-1" and rejected["reason"] == "no_fit"


def test_unreachable_rejection_at_first_launch_attempt() -> None:
    layout = Layout.from_document(
        {
            "layout": "mini",
            "blocks": {"a": {"length": 1000}, "b": {"length": 1000}},
            "connections": {"j": {"transits": {"ab": ["a.B", "b.A"]}}},
        }
    )
    scenario = Scenario(
        "stuck",
        "mini",
        {"t1": TrainSpec(500, "a", "A")},
        # Departing through a.A, the unconnected end: no route can exist.
        (RequestSpec("t1", "a.A", ("b.A",), 0),),
    )
    trace = run(layout, scenario)
    leaves = [line["event"] for line in events(trace, rid="t1-1")]
    assert leaves == ["request_submitted", "request_admitted", "request_rejected"]
    [rejected] = events(trace, "request_rejected")
    assert rejected["reason"] == "unreachable"


def test_a_stated_departure_the_train_is_not_at_is_rejected() -> None:
    """A departure block that disagrees with where the train stands is an
    ordinary bad request, answered rather than raised, and the run carries on
    around it (#73)."""
    layout, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "stale",
        "crossover-yard",
        {
            "freight": TrainSpec(600, "yard_w", "B"),
            "express": TrainSpec(600, "up_e", "A"),
        },
        (
            # freight stands in yard_w; this states the far yard.
            RequestSpec("freight", "yard_e.A", ("dn_w.B",), 0),
            RequestSpec("express", "up_e.A", ("dn_w.B",), 0),
        ),
    )
    trace = run(layout, scenario)
    leaves = [line["event"] for line in events(trace, rid="freight-1")]
    assert leaves == ["request_submitted", "request_rejected"]
    [rejected] = events(trace, "request_rejected")
    assert rejected["reason"] == "wrong_origin"
    assert events(trace, "request_completed", rid="express-1")


def second_working(layout: Layout, depart: str, dest: tuple[str, ...], at: int) -> str:
    """The trace of freight — placed in yard_w, routed to yard_e at boundary
    0, and given a second working `freight-2` at boundary `at`, departing
    `depart` for `dest`. #99's repro, with the boundary of that second
    working and the ends it names left to the caller: at 0 it is queued
    behind one still pending, later it is a drag on a train under way."""
    scenario = Scenario(
        "midroute",
        "crossover-yard",
        {"freight": TrainSpec(600, "yard_w", "B")},
        (
            RequestSpec("freight", "yard_w.B", ("yard_e.A",), 0),
            RequestSpec("freight", depart, dest, at),
        ),
    )
    return run(layout, scenario)


def admission_answer(trace: str, rid: str) -> tuple[str, str | None]:
    """Admission's answer to a working, with the reason where it rejected.

    The first of the two events that answer a submission and no more: a
    working admitted mid-route is launched only once the active route
    completes, and the launch stage judges it again from the origin the train
    has by then (DISPATCH.md), so anything later is that second stage's.
    """
    [answer, *_] = [
        line
        for line in events(trace, rid=rid)
        if line["event"] in ("request_admitted", "request_rejected")
    ]
    return answer["event"], answer.get("reason")


def test_a_mid_route_drag_is_judged_against_where_the_train_stands() -> None:
    """The departure block is checked against where the train stands, active
    route or not (#99). freight launches at boundary 1 and is standing in dn_w
    when the second working is released at boundary 2, so dn_w is the one block
    that working may state: not the block the train has left, not a block
    further along its route, and not the block the route arrives at.
    """
    layout, _ = load("crossover-yard/meet")
    fates = {
        "dn_w.B": "request_admitted",  # where it stands
        "yard_w.B": "request_rejected",  # the block it has left
        "dn_e.B": "request_rejected",  # a block further along its route
        "yard_e.A": "request_rejected",  # where the route arrives
    }
    for depart, fate in fates.items():
        answer, reason = admission_answer(
            second_working(layout, depart, ("dn_w.A",), 2), "freight-2"
        )
        assert answer == fate, depart
        if fate == "request_rejected":
            assert reason == Reason.WRONG_ORIGIN, depart


def test_a_mid_route_drag_before_the_train_has_moved_states_its_origin() -> None:
    """The same rule at the tick #99 reported it from (#134). freight commits
    to yard_e in boundary 1's grant phase and crosses only on the tick after,
    so a working released that same boundary is read while the train is still
    standing in yard_w, active route and all: the repro's four departures,
    with yard_w as where the train stands rather than the block it has left.

    Both faces of the fault are here. yard_w.B — the string a correct panel
    composes, facing moving only on `block_occupied` — was the departure the
    check refused, and yard_e.A, where the route arrives, was the one it let
    through, on the reading that the train was already standing there.
    """
    layout, _ = load("crossover-yard/meet")
    fates = {
        "yard_w.B": "request_admitted",  # where it stands, not yet moved
        "dn_w.B": "request_rejected",  # the next block of its route
        "dn_e.B": "request_rejected",  # a block further along its route
        "yard_e.A": "request_rejected",  # where the route arrives
    }
    for depart, fate in fates.items():
        answer, reason = admission_answer(
            second_working(layout, depart, ("dn_w.A",), 1), "freight-2"
        )
        assert answer == fate, depart
        if fate == "request_rejected":
            assert reason == Reason.WRONG_ORIGIN, depart


def assert_routes_leave_by_their_departure_end(layout: Layout, trace: str) -> None:
    """Every committed route's first transit is one its departure end
    actually reaches.

    The enumerator walks from the departure end while recording the origin as
    the route's first block, so an end on any other block yields a route that
    claims to start where the train stands and leaves somewhere else (#146).
    Read off the trace alone: the origin is the route's first block, and a
    bare end letter resolves against it exactly as `resolve_depart` does.
    """
    departs = {
        line["id"]: line["depart"] for line in events(trace, "request_submitted")
    }
    for chosen in events(trace, "route_chosen"):
        route = chosen["route"]
        if len(route) == 1:  # degenerate: an empty route crosses nothing
            continue
        origin, first = route[0], route[1]
        depart = departs[chosen["id"]]
        end = depart if "." in depart else f"{origin}.{depart}"
        reachable = [transit for transit, _ in layout.transits_at(end)]
        assert first in reachable, chosen


def test_a_working_queued_behind_another_never_routes_from_a_stale_block() -> None:
    """Both workings are queued at boundary 0, so admission cannot judge the
    second: while an earlier request for the train is pending, the block it
    will depart from is a future dispatcher choice. freight-1 takes the train
    to yard_e and freight-2 still states yard_w.B, the block the train has by
    then left, so the launch stage answers `wrong_origin`.

    Before #146 that end went to the enumerator, which walked the west ladder
    while recording yard_e as the route's first block: a committed route whose
    first transit is nowhere near the train, locks held on it, and
    `request_completed` for a working the layout could not have run.
    """
    layout, _ = load("crossover-yard/meet")
    trace = second_working(layout, "yard_w.B", ("up_w.A",), 0)
    assert admission_answer(trace, "freight-2") == ("request_admitted", None)
    [rejected] = events(trace, "request_rejected", rid="freight-2")
    assert rejected["reason"] == Reason.WRONG_ORIGIN
    assert events(trace, "route_chosen", rid="freight-2") == []
    # The train's earlier working is untouched and the run carries on.
    assert events(trace, "request_completed", rid="freight-1")
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_a_drag_admitted_mid_route_is_judged_again_where_it_launches() -> None:
    """Admission let this one through and was right to: dn_w is where the
    train stood at boundary 2. It goes stale while it waits — freight-1 runs
    on to yard_e — and the launch stage, the only stage holding the origin,
    refuses it there rather than routing from it (#135's drag, answered
    honestly).
    """
    layout, _ = load("crossover-yard/meet")
    trace = second_working(layout, "dn_w.B", ("up_w.A",), 2)
    assert admission_answer(trace, "freight-2") == ("request_admitted", None)
    [rejected] = events(trace, "request_rejected", rid="freight-2")
    assert rejected["reason"] == Reason.WRONG_ORIGIN
    assert events(trace, "route_chosen", rid="freight-2") == []
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_a_chained_working_resolves_its_bare_end_against_the_origin() -> None:
    """A bare end letter states no block, so it cannot go stale: it resolves
    against whatever origin the launch stage finds, which is the whole reason
    a chained working writes one. freight-2 departs `A` — yard_e.A, once the
    train is there — and routes as before."""
    layout, _ = load("crossover-yard/meet")
    trace = second_working(layout, "A", ("up_e.B",), 0)
    [chosen] = events(trace, "route_chosen", rid="freight-2")
    assert chosen["route"] == ["yard_e", "east_ladder.from_up", "up_e"]
    assert events(trace, "request_completed", rid="freight-2")
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_an_arrival_end_in_the_routes_arrival_block_is_still_checked() -> None:
    """The block a destination is compared against is the degenerate test of
    the pruning loop, and #99 repointed it at where the train stands (#134).
    So an arrival end in the block the active route arrives at — yard_e,
    while freight is still standing in yard_w — no longer bypasses: it is
    pruned for fit and entry like any other, where it used to be waved
    through on the grounds that the train was already there.

    Entry is the whole of what a case here can show. A route is only
    committed to a block the train fit at admission, so `no_fit` cannot
    arise at the block it arrives at; yard_e.B, the end of that block
    nothing connects to, is the one the loop can refuse. The other
    direction, an end in the block the train stands in, is the case below.
    """
    layout, _ = load("crossover-yard/meet")
    answer, reason = admission_answer(
        second_working(layout, "yard_w.B", ("yard_e.B",), 1), "freight-2"
    )
    assert (answer, reason) == ("request_rejected", Reason.NO_ENTRY)
    # Named beside the end that can be entered, it is pruned and the working
    # lives on the survivor — the ends of that block judged one by one.
    trace = second_working(layout, "yard_w.B", ("yard_e.A", "yard_e.B"), 1)
    [admitted] = events(trace, "request_admitted", rid="freight-2")
    assert admitted["dest"] == ["yard_e.A"]
    assert admitted["pruned"] == [{"end": "yard_e.B", "reason": Reason.NO_ENTRY}]


def test_degenerate_request_completes_without_moving_whichever_end() -> None:
    layout, _ = load("crossover-yard/meet")
    for end in ("yard_w.A", "yard_w.B"):
        scenario = Scenario(
            "stay",
            "crossover-yard",
            {"parked": TrainSpec(600, "yard_w", "B")},
            (RequestSpec("parked", "yard_w.B", (end,), 0),),
        )
        trace = run(layout, scenario)
        assert events(trace, "request_completed", rid="parked-1")
        assert events(trace, "move_granted") == []
        assert events(trace, "cross") == []
        [chosen] = events(trace, "route_chosen")
        assert chosen["route"] == ["yard_w"] and chosen["k_tried"] == 0


def test_a_refused_working_is_not_overtaken_by_the_trains_next_one() -> None:
    # Found by the Hypothesis differential (#28): a train's chained workings
    # must run in order. freight's first working is refused — express is
    # parked in dn_w and an idle train's block is permanently unavailable —
    # and its second working, to a free block, must not launch past it and
    # move the train out from under the request still waiting.
    layout, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "queued",
        "crossover-yard",
        {
            "freight": TrainSpec(600, "yard_w", "B"),
            "express": TrainSpec(600, "dn_w", "A"),
        },
        (
            RequestSpec("freight", "yard_w.B", ("dn_w.A",), 0),
            RequestSpec("freight", "B", ("up_e.A",), 0),
        ),
    )
    trace = run(layout, scenario)
    assert events(trace, "grant_refused", rid="freight-1")
    assert events(trace, "route_chosen", rid="freight-2") == []
    assert events(trace, "request_completed") == []


def test_grants_are_a_pure_function_of_the_buffered_sensor_set() -> None:
    layout, scenario = load("crossover-yard/meet")

    def drive(order: list[int]) -> list[str]:
        bus = Bus()
        seen: list[str] = []
        bus.subscribe(
            "tc49/dispatch/#",
            lambda topic, payload: seen.append(json.dumps([topic, payload])),
        )
        Dispatcher(bus, layout, scenario, FullRoute(layout, 2))
        for submitted in (
            {
                "id": "freight_1-1",
                "train": "freight_1",
                "depart": "yard_w.B",
                "dest": ["yard_e.A"],
            },
            {
                "id": "express_2-1",
                "train": "express_2",
                "depart": "up_e.A",
                "dest": ["yard_w.B"],
            },
        ):
            bus.publish("tc49/schedule/request_submitted", dict(submitted))
        bus.publish("tc49/layout/boundary", {"boundary": 0})
        bus.publish("tc49/layout/boundary", {"boundary": 1})  # freight launches
        bus.publish("tc49/layout/block_vacated", {"block": "yard_w"})
        bus.publish("tc49/layout/block_occupied", {"block": "dn_w"})
        bus.publish("tc49/layout/boundary", {"boundary": 2})  # express too
        # Both trains move this boundary: four sensors, in any order.
        sensors: list[tuple[str, Payload]] = [
            ("tc49/layout/block_vacated", {"block": "dn_w"}),
            ("tc49/layout/block_occupied", {"block": "dn_e"}),
            ("tc49/layout/block_vacated", {"block": "up_e"}),
            ("tc49/layout/block_occupied", {"block": "up_w"}),
        ]
        for i in order:
            bus.publish(*sensors[i])
        bus.publish("tc49/layout/boundary", {"boundary": 3})
        bus.drain()
        return seen

    baseline = drive([0, 1, 2, 3])
    for order in ([3, 2, 1, 0], [1, 3, 0, 2], [2, 0, 3, 1]):
        assert drive(order) == baseline


def points_layout(*points: dict[str, str]) -> Layout:
    """Two blocks joined by one transit, whose way crosses `points`."""
    return Layout.from_document(
        {
            "layout": "mini",
            "blocks": {"a": {"length": 1000}, "b": {"length": 1000}},
            "connections": {
                "j": {
                    "transits": {"ab": ["a.B", "b.A"]},
                    **({"points": {"ab": list(points)}} if points else {}),
                }
            },
        }
    )


def one_crossing(layout: Layout) -> str:
    scenario = Scenario(
        "cross",
        layout.name,
        {"t1": TrainSpec(500, "a", "B")},
        (RequestSpec("t1", "a.B", ("b.A",), 0),),
    )
    return run(layout, scenario)


def test_the_dispatcher_aligns_the_route_and_carries_its_points() -> None:
    """Setting the route is the dispatcher's, so `align` is its command, and
    it carries the points the transit needs as address-and-position pairs
    (ADR-0031)."""
    thrown = {"addr": "12", "position": "thrown"}
    [align] = events(one_crossing(points_layout(thrown)), "align")
    assert (align["connection"], align["transit"]) == ("j", "ab")
    assert align["points"] == [thrown]


def test_a_transit_with_nothing_to_throw_still_says_so_on_the_wire() -> None:
    """Quiet in the document, explicit on the wire: the key is absent where a
    connection has none, and the payload always carries one."""
    [align] = events(one_crossing(points_layout()), "align")
    assert align["points"] == []


def test_the_route_is_set_before_the_train_is_moved() -> None:
    """Two publishers on two topics promise nothing under MQTT, so the layout
    interface must not act on a `cross` before the `align` naming the same
    transit. The simulator holds that by batching commands to the tick; under
    the milestone binding the `align` is in the queue first as well."""
    trace = one_crossing(points_layout({"addr": "12", "position": "thrown"}))
    leaves = [line["event"] for line in events(trace)]
    assert leaves.index("align") < leaves.index("cross")
