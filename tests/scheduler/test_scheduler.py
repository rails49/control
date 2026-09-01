"""The scheduler seam: submission, ids, expansion, exhaustion, facing, gestures."""

import json
from pathlib import Path
from typing import cast

from tc49.bench.runner import facing as seed
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout
from tc49.lib.scenario import RequestSpec, TrainSpec
from tc49.scheduler import Scheduler
from tests.harness import load


def yard() -> Layout:
    """crossover-yard, the railroad the trains below stand on: the
    scheduler reads a layout to keep facing, and nothing else."""
    layout, _roster, _ = load("crossover-yard/meet")
    return layout


TWO_TRAINS = {
    "freight_1": TrainSpec("yard_w", "A-to-B"),
    "express_2": TrainSpec("up_e", "B-to-A"),
}
"""Where a document stands the two trains. The scheduler is never handed the
document: the harness reads a scenario into a facing seed and a timetable, and
those two are all that reaches here (bench/runner.py, ADR-0036)."""

TIMETABLE = (
    RequestSpec("freight_1", "yard_w.B", ("yard_e",)),
    RequestSpec("express_2", "up_e.A", ("yard_w.B",)),
    RequestSpec("freight_1", "yard_e.A", ("yard_w",)),
)


def seeded(trains: dict[str, TrainSpec] | None = None) -> dict[str, str]:
    """That placement as the facing seed the scheduler takes."""
    return seed(yard(), TWO_TRAINS if trains is None else trains)


def collect(bus: Bus, topic_filter: str) -> list[tuple[str, Payload]]:
    seen: list[tuple[str, Payload]] = []
    bus.subscribe(topic_filter, lambda topic, payload: seen.append((topic, payload)))
    return seen


def test_submits_the_whole_timetable_in_order_with_deterministic_ids() -> None:
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded(), TIMETABLE)

    bus.drain()
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
        {
            "id": "freight_1-2",
            "train": "freight_1",
            "depart": "yard_e.A",
            "dest": ["yard_w.A", "yard_w.B"],
        },
    ]


def test_exhausted_set_when_the_last_request_is_out() -> None:
    bus = Bus(Clock())
    seen = collect(bus, "tc49/schedule/state/exhausted")
    Scheduler(bus, yard(), seeded(), TIMETABLE)

    bus.drain()
    # Stamped by the binding that published it, the run clock reading zero
    # here: every state payload carries `at` and no event payload does (#240).
    assert [p for _, p in seen] == [{"at": 0.0, "exhausted": True}]
    bus.drain()
    assert len(seen) == 1  # set once, not republished


def test_an_empty_timetable_is_exhausted_at_once() -> None:
    bus = Bus(Clock())
    seen = collect(bus, "tc49/schedule/state/exhausted")
    Scheduler(bus, yard(), seeded())

    bus.drain()
    assert [p for _, p in seen] == [{"at": 0.0, "exhausted": True}]


def test_a_run_given_no_timetable_submits_nothing() -> None:
    """Which sources a run has is configuration (ADR-0036): `tc49 live` runs
    the same scheduler with no timetable at all, and the first gesture's id
    is still `<train>-1`."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())

    bus.drain()
    assert seen == []


FACING = "tc49/schedule/state/facing"


def test_the_documents_placement_is_the_first_facing() -> None:
    """A train that has never moved has no other source for a direction
    arrow, which is why the topic survives the scheduler leaving the browser
    (ADR-0036)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()
    assert [p["facing"] for _, p in seen] == [
        {"express_2": "up_e.B-to-A", "freight_1": "yard_w.A-to-B"}
    ]


def test_a_retained_facing_is_adopted_in_place_of_the_placement(
    tmp_path: Path,
) -> None:
    """A restart: the scheduler finds its own state topic already carrying
    facing, kept across the process by the bus binding, and takes it (#123).
    The document's placement is the cold start's seed and nothing more."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({FACING: {"facing": {"freight_1": "dn_e.B-to-A"}}}))
    bus = Bus(Clock(), path)
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()

    # `express_2` is not in the file, so it falls back to its placement: a
    # train added to the document since the last run is a cold start of one.
    assert seen[-1][1]["facing"] == {
        "express_2": "up_e.B-to-A",
        "freight_1": "dn_e.B-to-A",
    }


def test_a_facing_the_state_file_spells_the_old_way_is_refused(
    tmp_path: Path,
) -> None:
    """A durable state file written by a build from before #241 carries
    `dn_e.A`, which meant the end the train departs by and reads as no run at
    all. It is dropped rather than guessed at — reading it as `A-to-B` would
    turn the train round — and `freight_1` falls back to the placement the
    document gives it."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({FACING: {"facing": {"freight_1": "dn_e.A"}}}))
    bus = Bus(Clock(), path)
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()

    assert facing(seen) == {
        "express_2": "up_e.B-to-A",
        "freight_1": "yard_w.A-to-B",
    }


def test_a_retained_value_that_states_no_facing_map_is_a_cold_start(
    tmp_path: Path,
) -> None:
    """A retained value is a payload like any other, and rule 4 exempts no
    payload for having once been the scheduler's own: what is waiting on a
    broker that outlived the app can be hand-edited or written by an older
    build (#277). The first three raised out of the constructor while the
    value was subscripted, which is worse than a dropped frame — the app did
    not start at all. The scheduler starts as a cold start does instead,
    holding the seed its constructor was given, because a value it cannot
    read tells it nothing and refusing to start tells a person even less."""
    unreadable: list[object] = [
        "nonsense",  # not an object at all
        {"facing": "nonsense"},  # a value where the map belongs
        {"facing": ["freight_1"]},  # the trains without their facings
        {},  # nothing said about facing
    ]
    for retained in unreadable:
        path = tmp_path / "session.json"
        path.write_text(json.dumps({FACING: retained}))
        bus = Bus(Clock(), path)
        seen = collect(bus, FACING)
        Scheduler(bus, yard(), seeded(), TIMETABLE)
        bus.drain()

        assert facing(seen) == {
            "express_2": "up_e.B-to-A",
            "freight_1": "yard_w.A-to-B",
        }, retained


def test_a_train_the_retained_map_states_unreadably_loses_only_itself(
    tmp_path: Path,
) -> None:
    """The map is read one train at a time: the whole session's facing is in
    this one value, so dropping all of it for one entry would cold-start
    every train the good entries name (#277). `freight_1` falls back to its
    placement, and `express_2` is adopted as it always was."""
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({FACING: {"facing": {"freight_1": 7, "express_2": "dn_e.A-to-B"}}})
    )
    bus = Bus(Clock(), path)
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()

    assert facing(seen) == {
        "express_2": "dn_e.A-to-B",
        "freight_1": "yard_w.A-to-B",
    }


def test_a_train_only_the_old_spelling_names_comes_up_with_no_facing(
    tmp_path: Path,
) -> None:
    """The same refusal where there is no placement under it: a train a hand
    put on the rails last session is not held at all this one, and its drags
    are uncomposable until it is placed again (SYSTEM.md, ADR-0039). A
    guessed facing would send it the wrong way the first time it is asked to
    move."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({FACING: {"facing": {"shunter": "up_w.B"}}}))
    bus = Bus(Clock(), path)
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()

    assert "shunter" not in facing(seen)

    placed(bus, {"train": "shunter", "block": "up_w"})
    assert facing(seen)["shunter"] == "up_w.B-to-A"


def test_a_granted_move_turns_the_train_away_from_the_end_it_entered() -> None:
    """`move_granted` carries the transit and the block entered, never the
    end entered through, so the layout is what says which ends the transit
    joins: `to_dn` joins dn_w.A to yard_w.B, so a train granted into dn_w
    comes in through A and faces A-to-B."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
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
    assert seen[-1][1]["facing"]["freight_1"] == "dn_w.A-to-B"


def test_a_train_seeded_into_a_terminal_block_faces_its_connected_end() -> None:
    """`yard_w.A` is a wall — no connection holds it — so a train placed
    facing B-to-A there could never leave, and every drag would compose a
    request rejected `unreachable`. A terminal block has one end a train can leave by and the
    document does not get to choose otherwise (#145): a scheduler fed a
    document from anywhere is still right."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(
        bus, yard(), seeded(TWO_TRAINS | {"freight_1": TrainSpec("yard_w", "B-to-A")})
    )
    bus.drain()
    assert seen[-1][1]["facing"]["freight_1"] == "yard_w.A-to-B"


def test_a_granted_move_into_a_terminal_block_faces_its_connected_end() -> None:
    """The pass-through rule was incomplete rather than wrong: `to_dn` joins
    dn_w.A to yard_w.B, so a train granted into yard_w comes in through B and
    would face B-to-A, out through the end no connection holds. It faces
    A-to-B, the one end it can leave by, and the physical railroad is what
    settles it (#145)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.publish(
        "tc49/dispatch/move_granted",
        {
            "id": "express_2-1",
            "train": "express_2",
            "transit": "west_ladder.to_dn",
            "into": "yard_w",
            "aspect": "clear",
        },
    )
    bus.drain()
    assert seen[-1][1]["facing"]["express_2"] == "yard_w.A-to-B"


def test_a_committed_route_faces_the_train_at_its_departure_end() -> None:
    """A request may depart against facing — ADR-0019 makes facing a
    scheduler discipline, not a system invariant — so the route the
    dispatcher commits to has the last word before the train moves."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()  # express_2-1 goes out, so the scheduler knows whose route it is
    bus.publish(
        "tc49/dispatch/route_chosen",
        {
            "id": "express_2-1",
            "route": ["up_e", "east_ladder.from_up", "yard_e"],
            "k_tried": 1,
        },
    )
    bus.drain()
    assert seen[-1][1]["facing"]["express_2"] == "up_e.A-to-B"


def test_facing_is_published_only_when_it_moves() -> None:
    """Last-value-wins, and every view redraws on it: republishing the same
    map on every dispatch event would be a line in the trace per grant."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()
    bus.publish("tc49/dispatch/request_admitted", {"id": "freight_1-1", "dest": []})
    bus.publish(
        "tc49/dispatch/route_chosen",
        {"id": "freight_1-1", "route": ["yard_w"], "k_tried": 0},
    )
    bus.drain()
    assert len(seen) == 1


WANTED = "tc49/schedule/request_wanted"


def gesture(bus: Bus, payload: object) -> None:
    bus.publish(WANTED, cast(Payload, payload))
    bus.drain()


def test_a_gesture_is_composed_into_the_request_it_asks_for() -> None:
    """The two fields a gesture omits are the two the scheduler owns: the id
    it mints and the departure end it holds as facing (ADR-0036)."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())

    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A", "dn_e.B"]})
    assert [p for _, p in seen] == [
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["dn_e.A", "dn_e.B"],
        }
    ]


def test_a_drag_out_of_a_terminal_block_departs_by_its_connected_end() -> None:
    """What the whole fix is for: the drag names no departure end, so a train
    facing a wall composed a request rejected `unreachable`, over and over for
    the rest of the session (#145)."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(
        bus, yard(), seeded(TWO_TRAINS | {"freight_1": TrainSpec("yard_w", "B-to-A")})
    )

    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert seen[-1][1]["depart"] == "yard_w.B"


def test_gestures_and_the_timetable_share_one_undivided_counter() -> None:
    """An id that tells you who minted it is a shape, and no consumer reads
    the shape (ADR-0033): a person's drag simply takes the next number."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded(), TIMETABLE)

    bus.drain()  # the whole timetable goes out
    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert seen[-1][1]["id"] == "freight_1-3"  # -2 is the timetable's return working


def test_a_gesture_departs_from_where_facing_has_moved_to() -> None:
    """Facing is not the document's for long: the drag names no departure
    end, so what the scheduler has carried forward is what the request
    states."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())
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


def test_a_gesture_that_cannot_be_read_is_dropped() -> None:
    """Anything at all can be published where a person's page writes, and
    none of it raises out of the handler (ADR-0034): what cannot be composed
    leaves no request behind, and the next honest drag still composes."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())

    for payload in [
        "freight_1 to dn_e",  # not an object at all
        {"dest": ["dn_e.A"]},  # no train
        {"train": "freight_1"},  # no arrival ends
        {"train": "freight_1", "dest": "dn_e.A"},  # one end, not a set of them
        {"train": "freight_1", "dest": ["dn_e.A", 7]},  # not all ends
        {"train": "ghost", "dest": ["dn_e.A"]},  # a train this session lacks
    ]:
        gesture(bus, payload)
    assert seen == []

    gesture(bus, {"train": "freight_1", "dest": ["dn_e.A"]})
    assert [p["id"] for _, p in seen] == ["freight_1-1"]


REVERSAL = "tc49/schedule/reversal_wanted"


def reversal(bus: Bus, payload: object) -> None:
    bus.publish(REVERSAL, cast(Payload, payload))
    bus.drain()


def test_a_reversal_turns_the_train_around_where_it_stands() -> None:
    """The whole of the gesture is the little arrow in the block the train
    stands in (#124): facing becomes the other run across the same block,
    which ADR-0019 named as the one change routes do not account for.

    `express_2` stands in `up_e`, a through block, which is where the flip
    has two ends to choose between at all."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())

    reversal(bus, {"train": "express_2"})
    assert seen[-1][1]["facing"] == {
        "express_2": "up_e.A-to-B",
        "freight_1": "yard_w.A-to-B",
    }


def test_a_reversal_on_a_terminal_block_leaves_the_arrow_alone() -> None:
    """`freight_1` stands in `yard_w`, whose `A` end no connection holds. The
    end the flip would leave it pointing at is the wall, so it goes through
    `connected_end` and gives back the run it started with: one end is all
    the train can leave by, whichever way it is pointed (#145).

    Turned around with a bare flip of the value it faced `yard_w.B-to-A`,
    which is the placement the store refuses at load, and the next drag
    departed by the wall and was rejected `unreachable` — the train stuck for
    the rest of the session."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())

    reversal(bus, {"train": "freight_1"})
    assert seen[-1][1]["facing"] == {
        "express_2": "up_e.B-to-A",
        "freight_1": "yard_w.A-to-B",
    }


def test_a_reversal_composes_no_request_and_tells_the_dispatcher_nothing() -> None:
    """Nothing moves, so there is nothing to ask for: the dispatcher never
    learns the gesture happened."""
    bus = Bus(Clock())
    seen = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())

    reversal(bus, {"train": "freight_1"})
    assert seen == []


def test_a_reversal_is_dropped_while_the_train_has_a_request_in_flight() -> None:
    """Flipping the arrow under a queued request produces a lie: the request
    still departs the old end, and `route_chosen` flips the arrow back when it
    launches. So the rule is any request from submit to completion.

    Asked of `express_2` in the through block `up_e`, where the flip has an
    end to move to: in a terminal block the gesture is a no-op anyway and the
    drop would not be what held the arrow still (#145)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    gesture(bus, {"train": "express_2", "dest": ["dn_e.A"]})
    published = len(seen)

    reversal(bus, {"train": "express_2"})
    assert len(seen) == published
    assert seen[-1][1]["facing"]["express_2"] == "up_e.B-to-A"


def test_a_reversal_lands_once_the_request_is_answered() -> None:
    """A rejected request leaves the train idle — its marker is still on
    screen but the scheduler has dropped it — and that is precisely when you
    want to turn around.

    `express_2` again, so the arrow has somewhere to go and the assertion is
    about the rejection rather than about the block (#145)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    gesture(bus, {"train": "express_2", "dest": ["dn_e.A"]})
    bus.publish(
        "tc49/dispatch/request_rejected",
        {"id": "express_2-1", "reason": "no_entry"},
    )
    bus.drain()

    reversal(bus, {"train": "express_2"})
    assert seen[-1][1]["facing"]["express_2"] == "up_e.A-to-B"


def test_a_cancelled_request_is_dropped_and_never_re_submitted() -> None:
    """A request ends by arrival, by rejection, or by cancellation
    (ADR-0049), and the scheduler treats the third like the other two: the
    request and its destination go, the train is idle again — a reversal
    lands, which is what says the scheduler has let go — and nothing is
    composed in its place.

    A destination that is still wanted is asked for again with
    `request_wanted`. Re-submitting here would put back the very work a
    person's gesture just ended.
    """
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    submitted = collect(bus, "tc49/dispatch/request_submitted")
    Scheduler(bus, yard(), seeded())
    gesture(bus, {"train": "express_2", "dest": ["dn_e.A"]})
    assert len(submitted) == 1

    announce(bus, "request_cancelled", {"id": "express_2-1", "reason": "revoked"})

    assert len(submitted) == 1
    reversal(bus, {"train": "express_2"})
    assert seen[-1][1]["facing"]["express_2"] == "up_e.A-to-B"


def test_a_cancellation_needs_no_facing_case_of_its_own() -> None:
    """`removed` is followed by `train_removed`, which already pops the
    facing, and `displaced` by `train_placed`, which already recomputes it.
    The cancellation itself moves no arrow: the train is where it was until
    one of those two says otherwise."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    gesture(bus, {"train": "express_2", "dest": ["dn_e.A"]})
    published = len(seen)

    announce(bus, "request_cancelled", {"id": "express_2-1", "reason": "removed"})
    assert len(seen) == published

    announce(bus, "train_removed", {"train": "express_2"})
    assert "express_2" not in seen[-1][1]["facing"]


def test_a_reversal_that_cannot_be_read_is_dropped() -> None:
    """A gesture carries no id, so there is nothing to address an answer to
    and a broadcast refusal would be uncorrelatable (ADR-0034): what cannot
    be read leaves nothing behind, and the trace is its only record."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()  # the placement facing, so what follows is the answer
    published = len(seen)

    for payload in [
        "freight_1",  # not an object at all
        {},  # no train
        {"train": 7},  # a train that is not a name
        {"train": "ghost"},  # a train this session holds no facing for
    ]:
        reversal(bus, payload)
    assert len(seen) == published


PLACED = "tc49/dispatch/train_placed"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"


def placed(bus: Bus, payload: Payload) -> None:
    bus.publish(PLACED, payload)
    bus.drain()


def facing(seen: list[tuple[str, Payload]]) -> dict[str, str]:
    """The facing map as the scheduler last published it."""
    return cast(dict[str, str], seen[-1][1]["facing"])


def test_facing_follows_a_train_the_dispatcher_has_accepted_as_placed() -> None:
    """The facing is carried into the new block (#152). Arbitrary,
    because the layout is topological and there is nothing better to derive
    from; `reversal_wanted` is the correction where it lands the train the
    wrong way round, which is the shape the eventual roster drag wants
    anyway."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())

    placed(bus, {"train": "freight_1", "block": "up_w"})
    assert seen[-1][1]["facing"] == {
        "express_2": "up_e.B-to-A",
        "freight_1": "up_w.A-to-B",
    }


def test_a_train_placed_into_a_terminal_block_faces_its_connected_end() -> None:
    """`yard_e.B` is the buffer stop. Every facing site goes through
    `connected_facing`, so the run carried over is turned to the one end the
    train can leave by rather than pointing it at the wall (#145)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())

    placed(bus, {"train": "express_2", "block": "yard_e"})
    assert seen[-1][1]["facing"]["express_2"] == "yard_e.B-to-A"


def test_the_scheduler_never_reads_the_placement_gesture() -> None:
    """One gesture, one authority (ADR-0037). Whether the block is free is
    knowledge only the dispatcher has, so the scheduler follows the fact it
    publishes and not the gesture — two apps reading one payload would have
    to agree on every precondition, and the picture would split exactly where
    a real operator works."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()
    published = len(seen)

    bus.publish(PLACEMENT_WANTED, {"train": "freight_1", "block": "up_w"})
    bus.drain()
    assert len(seen) == published


def test_a_train_nothing_placed_gains_a_facing_when_it_is_placed() -> None:
    """A train off the layout has no facing, there being no block for one to
    be an end of. Placing it is where its facing begins: `train_placed` is the
    dispatcher having accepted the train as known, so the scheduler carries
    nothing across and starts from `B-to-A`, which `reversal_wanted` corrects
    (ADR-0019, ADR-0039)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()
    assert "shunter" not in facing(seen)

    placed(bus, {"train": "shunter", "block": "up_w"})
    assert facing(seen)["shunter"] == "up_w.B-to-A"


def test_a_restart_keeps_the_facing_of_a_train_no_document_places(
    tmp_path: Path,
) -> None:
    """A train a hand put on the rails has a facing and no placement in any
    document (ADR-0039). Dropping it on a restart would leave every drag of
    that train uncomposable — the departure end is read off facing — and the
    operator would find one train on the railroad that can be sent
    nowhere."""
    path = tmp_path / "session.json"
    path.write_text(json.dumps({FACING: {"facing": {"shunter": "up_w.A-to-B"}}}))
    bus = Bus(Clock(), path)
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()

    assert facing(seen)["shunter"] == "up_w.A-to-B"


def test_a_train_taken_off_the_layout_loses_its_facing() -> None:
    """The other direction of the same gesture: no block, no facing to hold
    (ADR-0039)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded())
    bus.drain()
    assert "freight_1" in facing(seen)

    bus.publish("tc49/dispatch/train_removed", {"train": "freight_1"})
    bus.drain()
    assert "freight_1" not in facing(seen)


# -- what the dispatcher announces, read and never trusted (#259) -----------


def announce(bus: Bus, leaf: str, payload: object) -> None:
    bus.publish(f"tc49/dispatch/{leaf}", cast(Payload, payload))
    bus.drain()


def test_an_announcement_that_cannot_be_read_leaves_facing_where_it_was() -> None:
    """A leaf under `dispatch` names the component that emits it and not the
    process that published this frame: the bus authenticates nobody, so an
    announcement is read exactly as a gesture is (SYSTEM.md, rule 4). None of
    these raises out of the handler, none moves an arrow, and the honest
    grant after them still lands.

    Two of the shapes are the layout's rather than the payload's — a transit
    no connection here holds, and one that crosses neither end of the block
    named — and are dropped for the same reason: there is no end to face away
    from. That second one is the shared rule and not this reader's own
    (SYSTEM.md, #276): the layout interface drops the `move` of the same shape
    rather than run a train over track the layout does not have.
    """
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()
    published, settled = len(seen), facing(seen)

    unreadable: list[tuple[str, object]] = [
        ("move_granted", "freight_1 into dn_w"),  # not an object at all
        ("move_granted", {"train": "freight_1", "into": "dn_w"}),  # no transit
        ("move_granted", {"train": "freight_1", "transit": "west_ladder.to_dn"}),
        ("move_granted", {"train": 7, "transit": "west_ladder.to_dn", "into": "dn_w"}),
        ("move_granted", {"train": "f", "transit": "ghost.to_dn", "into": "dn_w"}),
        (
            "move_granted",
            {"train": "f", "transit": "west_ladder.to_dn", "into": "up_e"},
        ),
        ("route_chosen", ["up_e", "east_ladder.from_up"]),  # nor a list of fields
        ("route_chosen", {"route": ["up_e", "east_ladder.from_up"]}),  # no id
        ("route_chosen", {"id": "express_2-1", "route": "up_e"}),  # not a sequence
        ("route_chosen", {"id": "express_2-1", "route": ["up_e", 7]}),  # not all names
        ("route_chosen", {"id": "express_2-1", "route": ["up_e", "ghost.from_up"]}),
        ("route_chosen", {"id": "nobody-9", "route": ["up_e", "east_ladder.from_up"]}),
        ("train_placed", {"train": "freight_1"}),  # no block
        ("train_placed", {"train": "freight_1", "block": None}),  # removal's word
        ("train_removed", {}),  # no train
        ("train_removed", {"train": 7}),
        ("request_completed", {}),  # no id
        ("request_rejected", {"id": 7, "reason": "malformed"}),
    ]
    for leaf, payload in unreadable:
        announce(bus, leaf, payload)
    assert len(seen) == published
    assert facing(seen) == settled

    announce(
        bus,
        "move_granted",
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "transit": "west_ladder.to_dn",
            "into": "dn_w",
            "aspect": "clear",
        },
    )
    assert facing(seen)["freight_1"] == "dn_w.A-to-B"


def test_a_leaf_the_scheduler_does_not_act_on_is_ignored() -> None:
    """Rule 3 hands the scheduler the whole of `dispatch`, so its own
    submissions come back past it beside every announcement it does not
    follow. Ignoring one is rule 4 doing its ordinary work — including a leaf
    that did not exist when this scheduler was built, which is what leaves the
    inventory open (SYSTEM.md)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()
    published, settled = len(seen), facing(seen)

    announce(
        bus,
        "request_submitted",  # the scheduler's own, on its own filter
        {
            "id": "freight_1-1",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )
    announce(bus, "lock_granted", {"train": "freight_1", "resources": ["dn_w"]})
    announce(bus, "throttle_moved", {"train": "freight_1", "speed": 40})  # not yet
    assert len(seen) == published
    assert facing(seen) == settled


def test_an_answer_that_cannot_be_read_leaves_the_request_in_flight() -> None:
    """The two answers are what free a train to be turned around at rest: an
    id the scheduler cannot read frees nothing, so the reversal stays dropped
    and the request stays the scheduler's to remember (#124)."""
    bus = Bus(Clock())
    seen = collect(bus, FACING)
    Scheduler(bus, yard(), seeded(), TIMETABLE)
    bus.drain()
    settled = facing(seen)

    announce(bus, "request_completed", {})  # no id at all
    announce(bus, "request_rejected", {"id": 7, "reason": "malformed"})
    reversal(bus, {"train": "express_2"})
    assert facing(seen) == settled

    announce(bus, "request_completed", {"id": "express_2-1"})
    reversal(bus, {"train": "express_2"})
    assert facing(seen)["express_2"] == "up_e.A-to-B"
