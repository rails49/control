"""The walking skeleton: crossover-yard/meet end-to-end under FullRoute."""

import json

from tc49.bus import Bus, Payload
from tc49.dispatch import Dispatcher
from tc49.layout import Layout
from tc49.locking import FullRoute
from tc49.store import RequestSpec, Scenario, TrainSpec
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
        {"leviathan": TrainSpec(2000, "up_w")},
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
        {"t1": TrainSpec(500, "a")},
        # Departing through a.A, the unconnected end: no route can exist.
        (RequestSpec("t1", "a.A", ("b.A",), 0),),
    )
    trace = run(layout, scenario)
    leaves = [line["event"] for line in events(trace, rid="t1-1")]
    assert leaves == ["request_submitted", "request_admitted", "request_rejected"]
    [rejected] = events(trace, "request_rejected")
    assert rejected["reason"] == "unreachable"


def test_degenerate_request_completes_without_moving_whichever_end() -> None:
    layout, _ = load("crossover-yard/meet")
    for end in ("yard_w.A", "yard_w.B"):
        scenario = Scenario(
            "stay",
            "crossover-yard",
            {"parked": TrainSpec(600, "yard_w")},
            (RequestSpec("parked", "yard_w.B", (end,), 0),),
        )
        trace = run(layout, scenario)
        assert events(trace, "request_completed", rid="parked-1")
        assert events(trace, "move_granted") == []
        assert events(trace, "cross") == []
        [chosen] = events(trace, "route_chosen")
        assert chosen["route"] == ["yard_w"] and chosen["k_tried"] == 0


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
