"""The walking skeleton: crossover-yard/meet end-to-end under FullRoute."""

import json

from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout
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
    startup = [line for line in events(trace, "lock_granted") if line["tick"] == 0]
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


def test_a_mid_route_drag_is_judged_against_where_the_train_stands() -> None:
    """The departure block is checked against where the train stands, active
    route or not (#99). freight launches at tick 1 and is standing in dn_w
    when the second working is released at tick 2, so dn_w is the one block
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
        scenario = Scenario(
            "midroute",
            "crossover-yard",
            {"freight": TrainSpec(600, "yard_w", "B")},
            (
                RequestSpec("freight", "yard_w.B", ("yard_e.A",), 0),
                RequestSpec("freight", depart, ("dn_w.A",), 2),
            ),
        )
        trace = run(layout, scenario)
        # The admission answer only: a working admitted here is launched once
        # the active route completes, and the launch stage judges it again
        # from the origin the train has by then (DISPATCH.md).
        answers = [
            line["event"]
            for line in events(trace, rid="freight-2")
            if line["event"] in ("request_admitted", "request_rejected")
        ]
        assert answers[:1] == [fate], depart
        if fate == "request_rejected":
            [rejected] = events(trace, "request_rejected", rid="freight-2")
            assert rejected["reason"] == "wrong_origin", depart


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
        bus.publish("tc49/layout/tick", {"tick": 0})
        bus.publish("tc49/layout/tick", {"tick": 1})  # freight launches
        bus.publish("tc49/layout/block_vacated", {"block": "yard_w"})
        bus.publish("tc49/layout/block_occupied", {"block": "dn_w"})
        bus.publish("tc49/layout/tick", {"tick": 2})  # express launches too
        # Both trains move this tick: four sensors, delivered in any order.
        sensors: list[tuple[str, Payload]] = [
            ("tc49/layout/block_vacated", {"block": "dn_w"}),
            ("tc49/layout/block_occupied", {"block": "dn_e"}),
            ("tc49/layout/block_vacated", {"block": "up_e"}),
            ("tc49/layout/block_occupied", {"block": "up_w"}),
        ]
        for i in order:
            bus.publish(*sensors[i])
        bus.publish("tc49/layout/tick", {"tick": 3})
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
