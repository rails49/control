"""The scheduler seam: releases, ids, expansion, exhaustion, facing, gestures."""

import io
import json
from typing import cast

from tc49.lib.bus import Bus, Payload
from tc49.lib.layout import Layout
from tc49.lib.scenario import RequestSpec, Scenario, TrainSpec
from tc49.lib.trace import TraceTap
from tc49.scheduler import Scheduler
from tests.harness import load


def yard() -> Layout:
    """crossover-yard, the railroad the scenario below stands on: the
    scheduler reads a layout to keep facing, and nothing else."""
    layout, _ = load("crossover-yard/meet")
    return layout


def two_train_scenario() -> Scenario:
    return Scenario(
        name="meet",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec(1100, "yard_w", "B"),
            "express_2": TrainSpec(600, "up_e", "A"),
        },
        requests=(
            RequestSpec("freight_1", "yard_w.B", ("yard_e",), 0),
            RequestSpec("express_2", "up_e.A", ("yard_w.B",), 0),
            RequestSpec("freight_1", "yard_e.A", ("yard_w",), 2),
        ),
    )


def collect(bus: Bus, topic_filter: str) -> list[tuple[str, Payload]]:
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append((topic, payload)))
    return seen


def tick(bus: Bus, n: int) -> None:
    bus.publish("tc49/layout/tick", {"tick": n})
    bus.drain()


def test_releases_at_due_ticks_with_deterministic_ids_and_expansion() -> None:
    bus = Bus()
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario())

    tick(bus, 0)
    assert [p for _, p in seen] == [
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A", "yard_e.B"],
        },
        {
            "id": "express_2-1",
            "train": "express_2",
            "depart": "up_e.A",
            "dest": ["yard_w.B"],
        },
    ]

    tick(bus, 1)
    assert len(seen) == 2  # nothing due at tick 1

    tick(bus, 2)
    assert [p for _, p in seen[2:]] == [
        {
            "id": "freight_1-2",
            "train": "freight_1",
            "depart": "yard_e.A",
            "dest": ["yard_w.A", "yard_w.B"],
        }
    ]


def test_exhausted_set_when_the_last_request_is_out() -> None:
    bus = Bus()
    seen = collect(bus, "tc49/schedule/state/exhausted")
    Scheduler(bus, yard(), two_train_scenario())

    tick(bus, 0)
    assert seen == []
    tick(bus, 2)
    assert [p for _, p in seen] == [{"exhausted": True}]
    tick(bus, 3)
    assert len(seen) == 1  # set once, not republished


def test_empty_scenario_is_exhausted_at_the_first_tick() -> None:
    bus = Bus()
    seen = collect(bus, "tc49/schedule/state/exhausted")
    scenario = two_train_scenario()
    Scheduler(
        bus, yard(), Scenario(scenario.name, scenario.layout, scenario.trains, ())
    )

    tick(bus, 0)
    assert [p for _, p in seen] == [{"exhausted": True}]


def test_the_timetable_is_off_when_the_session_says_so() -> None:
    """Which sources a session has is configuration (ADR-0036): `tc49 live`
    runs the same scheduler with nothing released, while `at` is a tick
    number, and the first gesture's id is still `<train>-1`."""
    bus = Bus()
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario(), timetable=False)

    tick(bus, 0)
    tick(bus, 2)
    assert seen == []


FACING = "tc49/schedule/state/facing"


def test_the_scenarios_placement_is_the_first_facing() -> None:
    """A train that has never moved has no other source for a direction
    arrow, which is why the topic survives the scheduler leaving the browser
    (ADR-0036)."""
    bus = Bus()
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), two_train_scenario())
    bus.drain()
    assert [p["facing"] for _, p in seen] == [
        {"express_2": "up_e.A", "freight_1": "yard_w.B"}
    ]


def test_a_granted_move_turns_the_train_away_from_the_end_it_entered() -> None:
    """`move_granted` carries the transit and the block entered, never the
    end entered through, so the layout is what says which ends the transit
    joins: `to_dn` joins dn_w.A to yard_w.B, so a train granted into dn_w
    comes in through A and faces B."""
    bus = Bus()
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), two_train_scenario())
    bus.publish(
        "tc49/dispatch/move_granted",
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "transit": "west_ladder.to_dn",
            "into": "dn_w",
            "aspect": "clear",
        },
    )
    bus.drain()
    assert seen[-1][1]["facing"]["freight_1"] == "dn_w.B"


def test_a_committed_route_faces_the_train_at_its_departure_end() -> None:
    """A request may depart against facing — ADR-0019 makes facing a
    scheduler discipline, not a system invariant — so the route the
    dispatcher commits to has the last word before the train moves."""
    bus = Bus()
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), two_train_scenario())
    tick(bus, 0)  # express_2-1 goes out, so the scheduler knows whose route it is
    bus.publish(
        "tc49/dispatch/route_chosen",
        {
            "id": "express_2-1",
            "route": ["up_e", "east_ladder.from_up", "yard_e"],
            "k_tried": 1,
        },
    )
    bus.drain()
    assert seen[-1][1]["facing"]["express_2"] == "up_e.B"


def test_facing_is_published_only_when_it_moves() -> None:
    """Last-value-wins, and every view redraws on it: republishing the same
    map on every dispatch event would be a line in the trace per grant."""
    bus = Bus()
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), two_train_scenario())
    tick(bus, 0)
    bus.publish("tc49/dispatch/request_admitted", {"id": "freight_1-1", "dest": []})
    bus.publish(
        "tc49/dispatch/route_chosen",
        {"id": "freight_1-1", "route": ["yard_w"], "k_tried": 0},
    )
    bus.drain()
    assert len(seen) == 1


WANTED = "tc49/ui/request_wanted"


def gesture(bus: Bus, payload: object) -> None:
    bus.publish(WANTED, cast(Payload, payload))
    bus.drain()


def test_a_gesture_is_composed_into_the_request_it_asks_for() -> None:
    """The two fields a gesture omits are the two the scheduler owns: the id
    it mints and the departure end it holds as facing (ADR-0036)."""
    bus = Bus()
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario(), timetable=False)

    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A", "dn_e.B"]})
    assert [p for _, p in seen] == [
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_e.A", "dn_e.B"],
        }
    ]


def test_gestures_and_the_timetable_share_one_undivided_counter() -> None:
    """An id that tells you who minted it is a shape, and no consumer reads
    the shape (ADR-0033): a person's drag simply takes the next number."""
    bus = Bus()
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario())

    tick(bus, 0)  # freight_1-1 and express_2-1 go out
    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert seen[-1][1]["id"] == "freight_1-3"  # -2 is the timetable's, at tick 2


def test_a_gesture_departs_from_where_facing_has_moved_to() -> None:
    """Facing is not the scenario's for long: the drag names no departure
    end, so what the scheduler has carried forward is what the request
    states."""
    bus = Bus()
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario(), timetable=False)
    bus.publish(
        "tc49/dispatch/move_granted",
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "transit": "west_ladder.to_dn",
            "into": "dn_w",
            "aspect": "clear",
        },
    )
    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert seen[-1][1]["depart"] == "dn_w.B"


UNCOMPOSABLE: list[object] = [
    "freight_1 to yard_e",  # not an object at all
    {},  # neither field
    {"train": None, "dest": ["yard_e.A"]},  # no train
    {"train": "freight_1", "dest": "yard_e.A"},  # dest a string, not ends
    {"train": "freight_1", "dest": ["yard_e.A", 7]},  # not all ends
    {"train": "ghost", "dest": ["yard_e.A"]},  # a train it holds no facing for
]


def test_no_gesture_can_raise_out_of_the_scheduler() -> None:
    """A gesture carries no id, so there is nothing to address an answer to
    and every uncomposable one is dropped in silence (ADR-0036). It is a line
    in the trace by virtue of having been published, which is what keeps a
    client bug diagnosable — and the session lives, an honest drag after all
    of it composing exactly as before.
    """
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)
    seen = collect(bus, "tc49/schedule/request_submitted")
    Scheduler(bus, yard(), two_train_scenario(), timetable=False)

    for payload in UNCOMPOSABLE:
        gesture(bus, payload)
    assert seen == []

    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert len([line for line in lines if line["event"] == "request_wanted"]) == len(
        UNCOMPOSABLE
    )

    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert seen[-1][1]["id"] == "freight_1-1"
