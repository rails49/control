"""Tests at the scheduler seam: releases, ids, expansion, exhaustion."""

from tc49.bus import Bus, Payload
from tc49.scheduler import Scheduler
from tc49.store import RequestSpec, Scenario, TrainSpec


def two_train_scenario() -> Scenario:
    return Scenario(
        name="meet",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec(1100, "yard_w"),
            "express_2": TrainSpec(600, "up_e"),
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
    Scheduler(bus, two_train_scenario())

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
    Scheduler(bus, two_train_scenario())

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
    Scheduler(bus, Scenario(scenario.name, scenario.layout, scenario.trains, ()))

    tick(bus, 0)
    assert [p for _, p in seen] == [{"exhausted": True}]
