"""What a dispatcher coming back up takes from the run before it (#151).

A restart loses the lock table and no sensor can return it, sensors being
anonymous, so placement has to be seeded before the first sensor event. The
seed used to be the scenario document, which says where the railroad
*started*. Now the bus binding holds the last picture across the process
(SYSTEM.md, the bus), and the dispatcher finds it waiting on its own state
topic and adopts it — which is literally what happens against a broker that
outlived the app.

Adoption is **selective** (#123): placement and the crossing hint are taken,
`locks` and `requests` are not. The lock table is rebuilt one block per train
exactly as a cold start builds it, the queue comes back empty, and no request
id resumes — ADR-0033 is untouched.
"""

import json
from pathlib import Path
from typing import Any

from tc49.bench.runner import DEFAULT_K
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Bus, Payload
from tests.harness import load

ALLOCATION = "tc49/dispatch/state/allocation"
REQUESTS = "tc49/schedule/request_submitted"

MOVED: dict[str, Any] = {
    "trains": {"express_2": "up_w", "freight_1": "dn_e"},
    "crossing": {},
    "locks": {},
    "requests": [],
}
"""An evening's running: neither train is where the scenario placed it."""


def restarted(
    tmp_path: Path, picture: dict[str, Any]
) -> tuple[Bus, Dispatcher, list[Payload]]:
    """A dispatcher on a bus whose file already holds that picture, with
    everything published on it collected as it goes."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({ALLOCATION: picture}))
    layout, scenario = load("crossover-yard/meet")
    bus = Bus(path)
    dispatcher = Dispatcher(bus, layout, scenario, FullRoute(layout, DEFAULT_K))
    said: list[Payload] = []
    bus.subscribe(
        "tc49/#", lambda topic, payload: said.append({"event": topic, **payload})
    )
    bus.drain()
    return bus, dispatcher, said


def test_placement_is_adopted_in_place_of_the_scenario(tmp_path: Path) -> None:
    """The whole point: the railroad comes back up where it was standing, not
    where the scenario document says it started."""
    _, dispatcher, _ = restarted(tmp_path, MOVED)

    assert dispatcher.state.block_of == {"express_2": "up_w", "freight_1": "dn_e"}
    assert dispatcher.state.locks == {"up_w": "express_2", "dn_e": "freight_1"}


def test_the_standing_locks_are_published_at_the_adopted_blocks(
    tmp_path: Path,
) -> None:
    """One `lock_granted` per train, exactly as the cold start publishes —
    what changes is the block it names."""
    _, _, said = restarted(tmp_path, MOVED)

    granted = {
        line["train"]: line["resources"]
        for line in said
        if line["event"] == "tc49/dispatch/lock_granted"
    }
    assert granted == {"express_2": ["up_w"], "freight_1": ["dn_e"]}


def test_a_train_that_was_crossing_comes_back_crossing(tmp_path: Path) -> None:
    """The placement hint survives with no route behind it: the picture says
    the train is on a transit, and a person is sent to look (#123). Clearing
    it is #154's placement gesture."""
    crossing = {**MOVED, "crossing": {"freight_1": "crossover.dn_straight"}}
    _, dispatcher, said = restarted(tmp_path, crossing)

    assert dispatcher.state.crossing == {"freight_1": "crossover.dn_straight"}
    picture = [line for line in said if line["event"] == ALLOCATION][-1]
    assert picture["crossing"] == {"freight_1": "crossover.dn_straight"}
    assert picture["requests"] == []  # a hint, never a resumed move


def test_the_locks_and_the_queue_are_left_behind(tmp_path: Path) -> None:
    """Everything a restart does *not* restore, in one picture: a lock table
    mid-route and a request in flight. The lock table comes back one block
    per train and the queue comes back empty."""
    running = {
        **MOVED,
        "locks": {"dn_e": "freight_1", "east_ladder.from_dn": "freight_1"},
        "requests": [
            {
                "id": "freight_1-1",
                "train": "freight_1",
                "depart": "yard_w.B",
                "dest": ["yard_e.A"],
                "route": ["dn_e", "east_ladder.from_dn", "yard_e"],
            }
        ],
    }
    _, dispatcher, _ = restarted(tmp_path, running)

    assert dispatcher.state.locks == {"up_w": "express_2", "dn_e": "freight_1"}
    assert dispatcher.pending == ()
    assert dispatcher.state.active == {}


def test_an_id_the_last_dispatcher_saw_is_admitted_afresh(tmp_path: Path) -> None:
    """`_seen_ids` starts empty, so a scheduler that also restarted and
    re-minted `freight_1-1` is submitting a new request to a new dispatcher.
    ADR-0033 asks for uniqueness and nothing more, and the id is opaque."""
    running = {
        **MOVED,
        "trains": {"express_2": "up_w", "freight_1": "yard_w"},
        "requests": [
            {
                "id": "freight_1-1",
                "train": "freight_1",
                "depart": "yard_w.B",
                "dest": ["yard_e.A"],
            }
        ],
    }
    bus, _, said = restarted(tmp_path, running)
    said.clear()

    bus.publish(
        REQUESTS,
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )
    bus.drain()

    admitted = [
        line["id"] for line in said if line["event"] == "tc49/dispatch/request_admitted"
    ]
    assert admitted == ["freight_1-1"]


def test_a_train_the_scenario_does_not_carry_is_not_adopted(tmp_path: Path) -> None:
    """Stock is the scenario's, so the picture is read for the trains this
    session has and no others. A file left by another railroad names none of
    them and is simply not adopted, rather than half-adopted."""
    stranger = {**MOVED, "trains": {"north": "claro_2", "freight_1": "dn_e"}}
    _, dispatcher, _ = restarted(tmp_path, stranger)

    assert dispatcher.state.block_of == {"express_2": "up_e", "freight_1": "dn_e"}
