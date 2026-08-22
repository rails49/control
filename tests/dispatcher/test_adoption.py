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

It is also **per train** (#164): a collision costs the trains in it and no
others, and what it protects — one train to a block, and no train standing in
a block nothing holds — holds train by train.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from tc49.bench.runner import DEFAULT_K, placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.dispatcher.dispatch import ALLOCATION, ASPECTS
from tc49.lib.bus import Bus, Payload
from tc49.lib.roster import Train
from tc49.lib.scenario import TrainSpec
from tests.harness import load

RUN = "tc49/dispatch/state/run"
REQUESTS = "tc49/schedule/request_submitted"

MOVED: dict[str, Any] = {
    "trains": {"express_2": "up_w", "freight_1": "dn_e"},
    "crossing": {},
    "locks": {},
    "requests": [],
}
"""An evening's running: neither train is where the scenario placed it."""


def restarted(
    tmp_path: Path,
    picture: dict[str, Any] | None,
    aspects: dict[str, str] | None = None,
    run: str | None = None,
    added: dict[str, str] | None = None,
) -> tuple[Bus, Dispatcher, list[Payload]]:
    """A dispatcher on a bus whose file already holds that picture — and the
    aspects and the run word the last session left, where a test wants them —
    with everything published on it collected as it goes.

    No picture at all is the first session of all naming a path: a file that
    exists with nothing of the dispatcher's in it, which is a cold start.

    `added` is stock the scenario has gained since that picture was taken,
    train to starting block: a train no picture can name, which is where a
    collision comes from (#164).
    """
    path = tmp_path / "session.json"
    kept: dict[str, Any] = {} if picture is None else {ALLOCATION: picture}
    if aspects is not None:
        kept[ASPECTS] = {"aspects": aspects}
    if run is not None:
        kept[RUN] = {"run": run}
    path.write_text(json.dumps(kept))
    layout, roster, scenario = load("crossover-yard/meet")
    if added is not None:
        # Stock the scenario gained, which the railroad owns: on the roster,
        # and placed by the document (ADR-0039).
        roster = replace(
            roster,
            trains={**roster.trains, **{train: Train(600) for train in added}},
        )
        scenario = replace(
            scenario,
            trains={
                **scenario.trains,
                **{train: TrainSpec(at=at, facing="A") for train, at in added.items()},
            },
        )
    bus = Bus(path)
    dispatcher = Dispatcher(
        bus, layout, roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    said: list[Payload] = []
    bus.subscribe(
        "tc49/#", lambda topic, payload: said.append({"event": topic, **payload})
    )
    bus.drain()
    return bus, dispatcher, said


def coherent(dispatcher: Dispatcher) -> None:
    """The invariant every adoption keeps, whatever it took from the picture:
    one train to a block, and the standing lock CONTEXT.md says every parked
    train always has (#164). A train placed by neither holds nothing, which
    is off the layout and not a fault (ADR-0039)."""
    placed = dispatcher.state.block_of
    assert len(set(placed.values())) == len(placed), "two trains in one block"
    assert dispatcher.state.locks == {block: train for train, block in placed.items()}


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


def test_a_train_the_scenario_gained_starts_where_the_document_says(
    tmp_path: Path,
) -> None:
    """A train added since the picture was taken is a cold start of one, and
    contests nothing while its block is free: the two trains the picture
    names keep their restored positions beside it."""
    _, dispatcher, _ = restarted(tmp_path, MOVED, added={"local_3": "dn_w"})

    assert dispatcher.state.block_of == {
        "express_2": "up_w",
        "freight_1": "dn_e",
        "local_3": "dn_w",
    }
    coherent(dispatcher)


def test_only_the_colliding_train_gives_up_its_restored_position(
    tmp_path: Path,
) -> None:
    """The picture is taken a train at a time (#164).

    `local_3` was added to the document since the last run, so no picture can
    name it and its starting block is the only answer it has — and that block
    is where the picture stands `freight_1`. The train with a second answer
    is the one that yields: `freight_1` falls back to its own starting block,
    and `express_2`, which the collision has nothing to do with, comes back up
    where the last session left it.
    """
    _, dispatcher, _ = restarted(tmp_path, MOVED, added={"local_3": "dn_e"})

    assert dispatcher.state.block_of == {
        "local_3": "dn_e",  # the document's, the only word for it
        "freight_1": "yard_w",  # the document's, its picture block taken
        "express_2": "up_w",  # the picture's, untouched by the collision
    }
    coherent(dispatcher)


def test_a_train_with_nowhere_left_is_placed_by_neither(tmp_path: Path) -> None:
    """Both answers taken, so the train comes up off the layout (ADR-0039).

    `local_3` takes the block the picture stands `freight_1` in, and the
    picture has meanwhile parked `express_2` in `freight_1`'s own starting
    block — a completed request, which is where the scenario sends it. There
    is nothing left to place `freight_1` in, and standing it in a block
    another train holds is the one thing adoption may not do. The rest of the
    railroad is restored around it, and #153 is what points a person at it.
    """
    parked = {**MOVED, "trains": {"express_2": "yard_w", "freight_1": "dn_e"}}
    _, dispatcher, _ = restarted(tmp_path, parked, added={"local_3": "dn_e"})

    assert dispatcher.state.block_of == {"local_3": "dn_e", "express_2": "yard_w"}
    assert "freight_1" not in dispatcher.state.locks.values()
    coherent(dispatcher)


def test_a_colliding_pair_that_is_the_whole_railroad_ends_at_the_document(
    tmp_path: Path,
) -> None:
    """The picture #151 refused whole, now refused a train at a time — and
    with only two trains on the railroad the answer is the same one.

    `express_2` is what the picture does not name, so its starting block is
    all it has, and the picture stands `freight_1` in exactly that block.
    `freight_1` falls back and there is no third train left holding a
    restored position. What changed is that this is now a consequence of the
    per-train rule rather than a rule of its own.
    """
    stacked = {**MOVED, "trains": {"freight_1": "up_e"}}  # express_2's own block
    _, dispatcher, _ = restarted(tmp_path, stacked)

    assert dispatcher.state.block_of == {"freight_1": "yard_w", "express_2": "up_e"}
    coherent(dispatcher)


def test_the_train_that_falls_back_leaves_its_crossing_hint_behind(
    tmp_path: Path,
) -> None:
    """The hint belongs to the placement it came with: it names the transit
    that placement was consistent with, so a train standing where the
    document says instead is not on it. The hint of a train that kept its
    restored position is untouched — the collision is not its business.
    """
    crossing = {
        **MOVED,
        "crossing": {
            "freight_1": "crossover.dn_straight",
            "express_2": "crossover.up_straight",
        },
    }
    _, dispatcher, _ = restarted(tmp_path, crossing, added={"local_3": "dn_e"})

    assert dispatcher.state.block_of["freight_1"] == "yard_w"
    assert dispatcher.state.crossing == {"express_2": "crossover.up_straight"}


def test_a_train_placed_by_neither_carries_no_crossing_hint(tmp_path: Path) -> None:
    """The same rule for the train nothing places at all: it is standing
    somewhere a person has to find, and naming a transit it was crossing
    would be the picture speaking for a placement that was refused."""
    parked = {
        **MOVED,
        "trains": {"express_2": "yard_w", "freight_1": "dn_e"},
        "crossing": {"freight_1": "crossover.dn_straight"},
    }
    _, dispatcher, _ = restarted(tmp_path, parked, added={"local_3": "dn_e"})

    assert "freight_1" not in dispatcher.state.block_of
    assert dispatcher.state.crossing == {}


def test_the_opening_statement_corrects_a_stale_aspect(tmp_path: Path) -> None:
    """Every state topic the dispatcher writes now has a previous value on
    it, and aspects is one of them.

    The last session was cut off mid-route, so the file shows a signal at
    `approach` for a route no longer restored. Left alone that value stands
    until the first grant phase — a whole boundary, ten seconds of a session
    the operator is reconnecting into — and the panel joining draws a train a
    clear road it has no lock on. So the opening statement says the aspects
    too, beside the standing locks and the picture.
    """
    _, _, said = restarted(tmp_path, MOVED, aspects={"dn_e.B": "approach"})

    shown = [line for line in said if line["event"] == ASPECTS]
    assert shown, "the opening statement said nothing about the signals"
    assert all(set(line["aspects"].values()) == {"stop"} for line in shown)


def test_a_restored_session_comes_up_held(tmp_path: Path) -> None:
    """The whole point of the hold on a real railroad (#154).

    A picture nobody has looked at is not a railroad anyone should be
    granting into: the steel is wherever the last session left it, and the
    file says where it *believed* it was. So the constructor states `held`,
    and the operator releases it once they have looked.
    """
    _, dispatcher, said = restarted(tmp_path, MOVED)

    assert dispatcher.state.run == "held"
    # Once from the constructor's own publish and once as the last value the
    # subscription replays; the word is what matters, and it never moved.
    assert {line["run"] for line in said if line["event"] == RUN} == {"held"}


def test_a_session_with_nothing_to_adopt_still_comes_up_running(
    tmp_path: Path,
) -> None:
    """A cold start is a cold start whether or not it names a file: the first
    session of all writes the picture nobody has yet, and there is nothing
    for a hold to protect (ADR-0037)."""
    _, dispatcher, said = restarted(tmp_path, None)

    assert dispatcher.state.block_of == {"express_2": "up_e", "freight_1": "yard_w"}
    assert dispatcher.state.run == "running"
    assert {line["run"] for line in said if line["event"] == RUN} == {"running"}


def test_the_retained_word_is_not_what_decides_it(tmp_path: Path) -> None:
    """The file keeps whatever was retained on every state topic, `state/run`
    included, so a session cut while running finds `running` waiting for it.
    Adoption overrides it: coming up running on the strength of a picture
    nobody has looked at is the failure the hold exists to prevent (#123)."""
    _, dispatcher, _ = restarted(tmp_path, MOVED, run="running")

    assert dispatcher.state.run == "held"


def test_a_picture_the_document_overruled_holds_the_run_all_the_same(
    tmp_path: Path,
) -> None:
    """Where the picture contradicts the scenario the document wins the
    contested block (`restored`) — and the steel does not go back to the
    document with it. There was a session here and it was cut off, which is
    exactly what a person has to come and look at."""
    stacked = {**MOVED, "trains": {"freight_1": "up_e"}}  # express_2's own block
    _, dispatcher, _ = restarted(tmp_path, stacked)

    assert dispatcher.state.block_of == {"freight_1": "yard_w", "express_2": "up_e"}
    assert dispatcher.state.run == "held"
