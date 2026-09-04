"""The walking skeleton: crossover-yard/meet end-to-end under FullRoute."""

import json
from typing import cast

from tc49.bench.runner import placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout, block_of, departure_end, end_on
from tc49.lib.rejection import Reason
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tests.harness import events, load, run, stock


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
    startup = [line for line in events(trace, "lock_granted") if line["time"] == 0.0]
    assert {line["train"] for line in startup} >= {"freight_1", "express_2"}


def test_meet_traced_twice_is_byte_identical() -> None:
    layout, _roster, scenario = load("crossover-yard/meet")
    assert (
        run(layout, _roster, scenario).encode()
        == run(layout, _roster, scenario).encode()
    )


def test_two_stage_admission_records_no_entry_pruning() -> None:
    trace = run(*load("crossover-yard/meet"))
    [admitted] = events(trace, "request_admitted", rid="freight_1-1")
    assert admitted["dest"] == ["yard_e.A"]
    assert admitted["pruned"] == [{"end": "yard_e.B", "reason": "no_entry"}]


def test_no_fit_pruning_rejects_at_admission() -> None:
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "long",
        "crossover-yard",
        {"leviathan": TrainSpec("up_w", "A-to-B")},
        (RequestSpec("leviathan", "up_w.B", ("yard_e",)),),
    )
    trace = run(layout, stock(leviathan=2000), scenario)
    [rejected] = events(trace, "request_rejected")
    assert rejected["id"] == "leviathan-1" and rejected["reason"] == "no_fit"


def test_unreachable_rejection_where_the_origin_is_known_at_admission() -> None:
    """An idle train has no queue of its own ahead of it, so the block it
    departs from is not a future dispatcher choice and reachability is
    settled where the request arrives (#135) rather than a boundary later."""
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
        {"t1": TrainSpec("a", "B-to-A")},
        # Departing through a.A, the unconnected end: no route can exist.
        (RequestSpec("t1", "a.A", ("b.A",)),),
    )
    trace = run(layout, stock(t1=500), scenario)
    leaves = [line["event"] for line in events(trace, rid="t1-1")]
    assert leaves == ["request_submitted", "request_rejected"]
    [rejected] = events(trace, "request_rejected")
    assert rejected["reason"] == "unreachable"


def test_a_stated_departure_the_train_is_not_at_is_rejected() -> None:
    """A departure block that disagrees with where the train stands is an
    ordinary bad request, answered rather than raised, and the run carries on
    around it (#73)."""
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "stale",
        "crossover-yard",
        {
            "freight": TrainSpec("yard_w", "A-to-B"),
            "express": TrainSpec("up_e", "B-to-A"),
        },
        (
            # freight stands in yard_w; this states the far yard.
            RequestSpec("freight", "yard_e.A", ("dn_w.B",)),
            RequestSpec("express", "up_e.A", ("dn_w.B",)),
        ),
    )
    trace = run(layout, stock(freight=600, express=600), scenario)
    leaves = [line["event"] for line in events(trace, rid="freight-1")]
    assert leaves == ["request_submitted", "request_rejected"]
    [rejected] = events(trace, "request_rejected")
    assert rejected["reason"] == "wrong_origin"
    assert events(trace, "request_completed", rid="express-1")


def second_request(layout: Layout, depart: str, dest: tuple[str, ...]) -> str:
    """The trace of freight — placed in yard_w, routed to yard_e, and given a
    second request `freight-2` departing `depart` for `dest`. Requests go in
    at the start of a run (ADR-0047) and the first launches on admission, so
    the second is always a drag on a train under way."""
    scenario = Scenario(
        "midroute",
        "crossover-yard",
        {"freight": TrainSpec("yard_w", "A-to-B")},
        (
            RequestSpec("freight", "yard_w.B", ("yard_e.A",)),
            RequestSpec("freight", depart, dest),
        ),
    )
    return run(layout, stock(freight=600), scenario)


def admission_answer(trace: str, rid: str) -> tuple[str, str | None]:
    """Admission's answer to a request, with the reason where it rejected.

    The first of the two events that answer a submission and no more: a
    request admitted mid-route is launched only once the active route
    completes, and the launch stage judges it again from the origin the train
    has by then (DISPATCH.md), so anything later is that second stage's.
    """
    [answer, *_] = [
        line
        for line in events(trace, rid=rid)
        if line["event"] in ("request_admitted", "request_rejected")
    ]
    return answer["event"], answer.get("reason")


def test_a_mid_route_drags_stated_block_is_corrected_at_the_launch() -> None:
    """A drag on a train under way states a block composed against a
    snapshot — where the train stood when the panel drew it — and admission
    does not judge it (ADR-0047): whichever block it states, the launch
    supplies the end the committed route leaves the train facing (#135), and
    the working runs from where the train actually arrives.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    for depart in ("dn_w.B", "yard_w.B", "dn_e.B", "yard_e.A"):
        trace = second_request(layout, depart, ("up_e.B",))
        assert admission_answer(trace, "freight-2") == ("request_admitted", None)
        [chosen] = events(trace, "route_chosen", rid="freight-2")
        assert chosen["route"][0] == "yard_e", depart
        assert events(trace, "request_completed", rid="freight-2"), depart


def assert_routes_leave_by_their_departure_end(layout: Layout, trace: str) -> None:
    """Every committed route's first transit is one the end it was found
    from actually reaches.

    The enumerator walks from the departure end while recording the origin as
    the route's first block, so an end on any other block yields a route that
    claims to start where the train stands and leaves somewhere else (#146).
    Which end that was is read off the trace alone. A request that states the
    origin, or no block at all, was routed from the end it stated; one that
    states another block had its end supplied by the dispatcher, and the
    train's previous committed route says which — it leaves the train facing
    away from the end it entered through, or, into a terminal block, by the
    one end it can leave by (#135).
    """
    submitted = {line["id"]: line for line in events(trace, "request_submitted")}
    ran: dict[str, list[str]] = {}  # train -> the last route committed for it
    for chosen in events(trace, "route_chosen"):
        route, line = chosen["route"], submitted[chosen["id"]]
        train, depart = line["train"], line["depart"]
        previous = ran.get(train)
        if len(route) == 1:  # degenerate: an empty route crosses nothing
            continue
        ran[train] = route
        origin, first = route[0], route[1]
        if "." not in depart:
            end = f"{origin}.{depart}"
        elif block_of(depart) == origin:
            end = depart
        else:
            assert previous is not None, chosen
            entered = end_on(layout, previous[-1], previous[-2])
            end = departure_end(layout, entered)
        reachable = [transit for transit, _ in layout.transits_at(end)]
        assert first in reachable, chosen


def test_a_request_queued_behind_a_pending_one_settles_reachability_late() -> None:
    """While an earlier request for the train is pending — refused, not yet
    running — the block it will depart from is a future dispatcher choice,
    so admission can judge neither the second's origin nor its reachability.
    freight-1 wants dn_w, which express is parked in, so it waits until
    express's own working clears the block; freight then arrives in dn_w
    entering through A, the launch stage supplies dn_w.B as the end
    freight-2 leaves by, and up_w.A — enterable only off the west ladder —
    is out of reach from there, so the answer comes at the launch stage as
    DISPATCH.md says.

    The end freight-2 states, yard_w.B, is the block the train has by then
    left and is no part of the answer: before #146 it went to the enumerator,
    which walked the west ladder while recording the origin as the route's
    first block — a committed route whose first transit is nowhere near the
    train.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "late",
        "crossover-yard",
        {
            "freight": TrainSpec("yard_w", "A-to-B"),
            "express": TrainSpec("dn_w", "A-to-B"),
        },
        (
            RequestSpec("freight", "yard_w.B", ("dn_w.A",)),
            RequestSpec("freight", "yard_w.B", ("up_w.A",)),
            RequestSpec("express", "dn_w.B", ("dn_e.A",)),
        ),
    )
    trace = run(layout, stock(freight=600, express=600), scenario)
    assert admission_answer(trace, "freight-2") == ("request_admitted", None)
    [rejected] = events(trace, "request_rejected", rid="freight-2")
    assert rejected["reason"] == Reason.UNREACHABLE
    assert events(trace, "route_chosen", rid="freight-2") == []
    # The train's earlier request is untouched and the run carries on.
    assert events(trace, "request_completed", rid="freight-1")
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_a_drag_mid_route_runs_from_the_block_its_train_arrives_in() -> None:
    """#135's ruling: a drag on a moving train means "finish what you are
    doing, then go there". The request queues behind the one in flight and
    the dispatcher supplies its departure end from the route the train
    arrives on — nobody else could, the origin having been a future
    dispatcher choice at the moment of the drag.

    The end the drag states is dn_w.B, correct for where the train stood at
    boundary 2 and meaningless for yard_e. The end it launches by is yard_e.A:
    yard_e is a terminal block, so the pass-through rule alone would face the
    train at the wall and `lib`'s `departure_end` gives back the one end it
    can leave by — the same rule the scheduler asks of facing (#145).
    """
    layout, _roster, _ = load("crossover-yard/meet")
    trace = second_request(layout, "dn_w.B", ("yard_w.B",))
    [chosen] = events(trace, "route_chosen", rid="freight-2")
    assert chosen["route"] == [
        "yard_e",
        "east_ladder.from_dn",
        "dn_e",
        "crossover.dn_straight",
        "dn_w",
        "west_ladder.to_dn",
        "yard_w",
    ]
    assert events(trace, "request_completed", rid="freight-2")
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_a_drag_mid_route_to_an_end_out_of_reach_is_answered_at_admission() -> None:
    """The same drag to up_w.A instead. Behind an **active** route the origin
    is not a future choice at all — a route is fixed once chosen (ADR-0002) —
    so admission derives yard_e, derives the end, and finds no route: the
    operator is answered as the request arrives rather than later, when the
    train has finished a request nobody can now redirect.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    trace = second_request(layout, "dn_w.B", ("up_w.A",))
    assert admission_answer(trace, "freight-2") == (
        "request_rejected",
        Reason.UNREACHABLE,
    )
    assert events(trace, "route_chosen", rid="freight-2") == []
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_an_idle_trains_request_departs_by_the_end_it_states() -> None:
    """A train with no work ahead of it states its own departure end and
    keeps it, including one that contradicts facing: facing is a scheduler
    discipline and not a system invariant (ADR-0019), and reversal at rest is
    exactly the change routes do not account for.

    freight runs yard_w -> dn_e, entering through A, and its next request
    departs dn_e.A — the block the first arrives in, back the way it came.
    A stated end on the origin block is kept, active route or not; had the
    dispatcher supplied it, it would be dn_e.B and the route would leave by
    the east ladder.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "reversal",
        "crossover-yard",
        {"freight": TrainSpec("yard_w", "A-to-B")},
        (
            RequestSpec("freight", "yard_w.B", ("dn_e.A",)),
            RequestSpec("freight", "dn_e.A", ("yard_w.B",)),
        ),
    )
    trace = run(layout, stock(freight=600), scenario)
    [chosen] = events(trace, "route_chosen", rid="freight-2")
    assert chosen["route"][:2] == ["dn_e", "crossover.dn_straight"]
    assert events(trace, "request_completed", rid="freight-2")


def test_a_request_behind_work_that_moved_nothing_keeps_its_stated_end() -> None:
    """There is an end to supply only where the dispatcher chose a route.
    freight-1 is degenerate — it names the block the train is already in — so
    it completes without moving anything, and freight-2, queued behind it,
    has nothing but the end it stated. That end names yard_e, the train is in
    yard_w, and the launch stage refuses it rather than routing from it
    (#146). Its arrival end is degenerate too, and the departure is judged
    first: a stale request is refused, not completed on the grounds that the
    train happens to be there already.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "moved-nothing",
        "crossover-yard",
        {"freight": TrainSpec("yard_w", "A-to-B")},
        (
            RequestSpec("freight", "yard_w.B", ("yard_w.A",)),
            RequestSpec("freight", "yard_e.A", ("yard_w.B",)),
        ),
    )
    trace = run(layout, stock(freight=600), scenario)
    assert events(trace, "request_completed", rid="freight-1")
    [rejected] = events(trace, "request_rejected", rid="freight-2")
    assert rejected["reason"] == Reason.WRONG_ORIGIN
    assert events(trace, "route_chosen", rid="freight-2") == []


def test_a_chained_request_resolves_its_bare_end_against_the_origin() -> None:
    """A bare end letter states no block, so it cannot go stale: it resolves
    against whatever origin the launch stage finds, which is the whole reason
    a chained request writes one. freight-2 departs `A` — yard_e.A, once the
    train is there — and routes as before."""
    layout, _roster, _ = load("crossover-yard/meet")
    trace = second_request(layout, "A", ("up_e.B",))
    [chosen] = events(trace, "route_chosen", rid="freight-2")
    assert chosen["route"] == ["yard_e", "east_ladder.from_up", "up_e"]
    assert events(trace, "request_completed", rid="freight-2")
    assert_routes_leave_by_their_departure_end(layout, trace)


def test_a_drag_to_where_the_train_is_already_going_completes_on_arrival() -> None:
    """A request queued behind a route that ends where the request asks the
    train to go. The end it states is no longer a routing input, so there is
    no staleness to refuse: the train arrives, the arrival end names the
    block it is standing in, and the request completes with an empty route
    exactly as any other degenerate one does."""
    layout, _roster, _ = load("crossover-yard/meet")
    trace = second_request(layout, "yard_w.B", ("yard_e.A",))
    assert events(trace, "request_rejected", rid="freight-2") == []
    [chosen] = events(trace, "route_chosen", rid="freight-2")
    assert chosen["route"] == ["yard_e"] and chosen["k_tried"] == 0
    assert events(trace, "request_completed", rid="freight-2")


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
    layout, _roster, _ = load("crossover-yard/meet")
    answer, reason = admission_answer(
        second_request(layout, "yard_w.B", ("yard_e.B",)), "freight-2"
    )
    assert (answer, reason) == ("request_rejected", Reason.NO_ENTRY)
    # Named beside the end that can be entered, it is pruned and the request
    # lives on the survivor — the ends of that block judged one by one.
    trace = second_request(layout, "yard_w.B", ("yard_e.A", "yard_e.B"))
    [admitted] = events(trace, "request_admitted", rid="freight-2")
    assert admitted["dest"] == ["yard_e.A"]
    assert admitted["pruned"] == [{"end": "yard_e.B", "reason": Reason.NO_ENTRY}]


def test_degenerate_request_completes_without_moving_whichever_end() -> None:
    layout, _roster, _ = load("crossover-yard/meet")
    for end in ("yard_w.A", "yard_w.B"):
        scenario = Scenario(
            "stay",
            "crossover-yard",
            {"parked": TrainSpec("yard_w", "A-to-B")},
            (RequestSpec("parked", "yard_w.B", (end,)),),
        )
        trace = run(layout, stock(parked=600), scenario)
        assert events(trace, "request_completed", rid="parked-1")
        assert events(trace, "move_granted") == []
        assert events(trace, "move") == []
        [chosen] = events(trace, "route_chosen")
        assert chosen["route"] == ["yard_w"] and chosen["k_tried"] == 0


def test_a_refused_request_is_not_overtaken_by_the_trains_next_one() -> None:
    # Found by the Hypothesis differential (#28): a train's chained requests
    # must run in order. freight's first request is refused — express is
    # parked in dn_w and an idle train's block is permanently unavailable —
    # and its second request, to a free block, must not launch past it and
    # move the train out from under the request still waiting.
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        "queued",
        "crossover-yard",
        {
            "freight": TrainSpec("yard_w", "A-to-B"),
            "express": TrainSpec("dn_w", "B-to-A"),
        },
        (
            RequestSpec("freight", "yard_w.B", ("dn_w.A",)),
            RequestSpec("freight", "B", ("up_e.A",)),
        ),
    )
    trace = run(layout, stock(freight=600, express=600), scenario)
    assert events(trace, "grant_refused", rid="freight-1")
    assert events(trace, "route_chosen", rid="freight-2") == []
    assert events(trace, "request_completed") == []


def test_a_level_re_asserted_is_an_at_least_once_no_op() -> None:
    """A detector reports presence, and presence is a level (ADR-0047): a
    repeated reading re-asserts what the dispatcher already holds, so
    at-least-once delivery needs no counter and no dedup — and the repeat
    grants nothing, releases nothing and completes nothing twice."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    seen: list[str] = []
    Dispatcher(bus, layout, _roster, placement(scenario.trains), FullRoute(layout, 2))
    bus.subscribe(
        "tc49/dispatch/#",
        lambda topic, payload: seen.append(json.dumps([topic, payload])),
    )
    bus.publish(
        "tc49/dispatch/request_submitted",
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )
    bus.publish("tc49/layout/block_occupied", {"block": "dn_w"})
    bus.publish("tc49/layout/block_vacated", {"block": "yard_w"})
    bus.drain()
    said = list(seen)

    for repeat in (
        ("tc49/layout/block_occupied", {"block": "dn_w"}),
        ("tc49/layout/block_vacated", {"block": "yard_w"}),
    ):
        bus.publish(*cast(tuple[str, Payload], repeat))
    bus.drain()
    assert seen == said


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
        {"t1": TrainSpec("a", "A-to-B")},
        (RequestSpec("t1", "a.B", ("b.A",)),),
    )
    return run(layout, stock(t1=500), scenario)


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
    interface must not act on a `move` before the `align` naming the same
    transit. Under the milestone binding the bus delivers from one queue and
    the `align` is published first, which is what holds it."""
    trace = one_crossing(points_layout({"addr": "12", "position": "thrown"}))
    leaves = [line["event"] for line in events(trace)]
    assert leaves.index("align") < leaves.index("move")
