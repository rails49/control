"""A person says where a train actually stands (ADR-0037, #152).

`tc49/ui/placement_wanted` is the correction an operator makes with their own
eyes: this train is *here*. One gesture, one authority — the dispatcher alone
reads it, because "is that block free" is knowledge only it has, and having
accepted it announces `tc49/dispatch/train_placed` for everyone else to
follow. The scheduler follows that event and carries the train's facing
letter into the new block; it never reads the gesture.

Only while held, and only a block the train can actually be in. Anything else
is dropped, in silence and to the trace: a gesture carries no id and there is
nothing to address an answer to (ADR-0034).
"""

from pathlib import Path
from typing import Any

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import Incremental
from tc49.lib import durable
from tc49.lib.scenario import Scenario, TrainSpec
from tests.harness import RUN_WANTED, events, load, press, ticks

PLACEMENT_WANTED = "tc49/ui/placement_wanted"
REQUEST_WANTED = "tc49/ui/request_wanted"


def two_trains() -> Scenario:
    """`crossover-yard` with no timetable at all: a railroad standing still,
    which is what a person correcting a placement is looking at.

    `leviathan` is 2000mm and fits neither yard block (1400mm), so the fit
    rule has something to refuse; `dn_e` is where it stands, so the occupancy
    rule does too.
    """
    return Scenario(
        name="placing",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec(1100, "yard_w", "B"),
            "leviathan": TrainSpec(2000, "dn_e", "A"),
        },
        requests=(),
    )


@pytest.fixture
def held() -> Assembly:
    layout, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, two_trains())
    press(assembly, RUN_WANTED, {"run": "held"})
    return assembly


def place(assembly: Assembly, train: str, block: str) -> None:
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": block})


def last(assembly: Assembly, leaf: str) -> dict[str, Any]:
    return events(assembly.trace, leaf)[-1]


def placements(assembly: Assembly) -> list[dict[str, Any]]:
    return events(assembly.trace, "train_placed")


def facing(assembly: Assembly, train: str) -> str:
    return str(last(assembly, "facing")["facing"][train])


def test_a_placement_moves_the_lock_and_redraws_the_picture(held: Assembly) -> None:
    """Every parked train holds the lock on the block it stands in
    (CONTEXT.md), so placing one is moving that lock; the picture is
    republished because a joining client draws from it and nothing else."""
    before = last(held, "allocation")
    assert before["locks"]["yard_w"] == "freight_1"

    place(held, "freight_1", "up_w")

    assert placements(held) == [
        {"boundary": 0, "event": "train_placed", "train": "freight_1", "block": "up_w"}
    ]
    picture = last(held, "allocation")
    assert picture["trains"]["freight_1"] == "up_w"
    assert picture["locks"] == {"dn_e": "leviathan", "up_w": "freight_1"}


def test_the_scheduler_carries_facing_into_the_new_block(held: Assembly) -> None:
    """Facing is not part of placing: the gesture names a train and a block,
    the end letter comes over unchanged, and `reversal_wanted` is the
    correction where that lands the train the wrong way round (ADR-0019).
    The letter is arbitrary because the layout is topological and there is
    nothing better to derive from."""
    assert facing(held, "freight_1") == "yard_w.B"

    place(held, "freight_1", "up_w")

    assert facing(held, "freight_1") == "up_w.B"


def test_facing_never_names_the_wall_of_a_terminal_block(held: Assembly) -> None:
    """`yard_e.B` is the buffer stop and is in no connection. Every facing
    site goes through `leaving_end`, so the letter carried over is corrected
    to the one end the train can leave by (#145) rather than pointing it at
    the wall."""
    place(held, "freight_1", "yard_e")

    assert facing(held, "freight_1") == "yard_e.A"


def test_a_placement_is_dropped_while_the_run_is_running() -> None:
    """Placing under a running dispatcher would let a grant phase launch from
    a block the operator is still moving a locomotive out of."""
    layout, _ = load("crossover-yard/meet")
    running = assemble_live(layout, two_trains())

    place(running, "freight_1", "up_w")

    assert placements(running) == []
    assert last(running, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_placement_into_an_occupied_block_is_dropped(held: Assembly) -> None:
    """Two trains in one block is two holders of one lock, and the second
    would stand in a block nothing holds for it."""
    place(held, "freight_1", "dn_e")

    assert placements(held) == []
    assert last(held, "allocation")["locks"]["dn_e"] == "leviathan"


def test_a_placement_into_a_block_the_train_does_not_fit_in_is_dropped(
    held: Assembly,
) -> None:
    """The same fit the admission check applies to an arrival end, asked of
    a placement: the operator cannot report a train into a block it is longer
    than."""
    place(held, "leviathan", "yard_e")

    assert placements(held) == []
    assert last(held, "allocation")["trains"]["leviathan"] == "dn_e"


def test_a_placement_of_a_train_with_a_request_in_flight_is_dropped(
    held: Assembly,
) -> None:
    """On release the grant phase launches from `block_of`, so a pending
    request would silently depart from wherever the train was just put,
    having been admitted against the old block. Nothing cancels a request, so
    the way out is to release and let it finish (#152, Not this issue)."""
    press(held, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(held.trace, "request_admitted")

    place(held, "freight_1", "up_w")

    assert placements(held) == []
    assert last(held, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_placement_naming_stock_or_track_the_railroad_lacks_is_dropped(
    held: Assembly,
) -> None:
    """Dropped rather than answered: unlike a request, a gesture has no id an
    answer could be addressed to (ADR-0034)."""
    place(held, "ghost", "up_w")
    place(held, "freight_1", "siding_9")
    place(held, "freight_1", "up_w.A")  # an end is not a block

    assert placements(held) == []


def test_the_released_run_departs_from_where_the_train_was_put(
    held: Assembly,
) -> None:
    """The whole point of the gesture: what the dispatcher grants next comes
    off the corrected picture, and the steel under it agrees — the simulator
    stands in for a hand that lifted a locomotive, so it is told where the
    hand put it (ADR-0030)."""
    place(held, "freight_1", "up_w")
    press(held, RUN_WANTED, {"run": "running"})
    press(held, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(held, 12)

    assert last(held, "route_chosen")["route"][0] == "up_w"
    assert events(held.trace, "request_rejected") == []
    assert last(held, "request_completed")["id"] == "freight_1-1"
    assert last(held, "allocation")["trains"]["freight_1"] == "yard_e"


def test_a_placement_clears_whatever_the_train_was_crossing(tmp_path: Path) -> None:
    """A restored crossing hint is a train the last session left between two
    blocks, with no route behind it (#123) — exactly the train a person has
    to say something about. Once they have, it is standing in a block and
    crossing nothing, and the picture has to say so: the hint would otherwise
    ride out to every view and be persisted again, and affirming the block
    the dispatcher already believes in is no way out, that block not being
    free.

    One entry, and no more: the gesture names one train, and every other one
    the last session left between two blocks is still between them.
    """
    state = tmp_path / "session.json"
    durable.write(
        state,
        {
            "tc49/dispatch/state/allocation": {
                "trains": {"freight_1": "yard_w", "leviathan": "dn_e"},
                "crossing": {
                    "freight_1": "west_ladder.to_dn",
                    "leviathan": "east_ladder.from_dn",
                },
                "locks": {},
                "requests": [],
            }
        },
    )
    layout, _ = load("crossover-yard/meet")
    # No press: a session that adopted a picture comes up held (#154), which
    # is what makes the placement below acceptable at all.
    assembly = assemble_live(layout, two_trains(), state=state)
    assembly.bus.drain()  # the opening statement, which no boundary has yet
    assert last(assembly, "run")["run"] == "held"
    assert last(assembly, "allocation")["crossing"] == {
        "freight_1": "west_ladder.to_dn",
        "leviathan": "east_ladder.from_dn",
    }

    place(assembly, "freight_1", "up_w")

    after = last(assembly, "allocation")
    assert after["crossing"] == {"leviathan": "east_ladder.from_dn"}
    assert after["trains"] == {"freight_1": "up_w", "leviathan": "dn_e"}
    assert after["locks"] == {"up_w": "freight_1", "dn_e": "leviathan"}


def test_a_train_adoption_placed_nowhere_can_be_put_on_the_layout(
    tmp_path: Path,
) -> None:
    """The gesture is how the leftovers of a collision are ended (#164).

    Adoption takes the picture a train at a time, so a train whose picture
    block *and* whose starting block are both taken comes up placed nowhere
    at all — off the layout (ADR-0039), holding no lock, with a person the
    only way out. Here `leviathan` was added to the roster since the picture
    was taken and stands in `dn_e`, which is where the picture left
    `freight_1`; `railcar_3` is parked in `freight_1`'s own starting block,
    a working of an evening ago that completed.

    So the placement has no standing lock to move, only one to take.
    """
    state = tmp_path / "session.json"
    durable.write(
        state,
        {
            "tc49/dispatch/state/allocation": {
                "trains": {"freight_1": "dn_e", "railcar_3": "yard_w"},
                "crossing": {},
                "locks": {},
                "requests": [],
            }
        },
    )
    layout, _ = load("crossover-yard/meet")
    scenario = Scenario(
        name="unplaced",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec(1100, "yard_w", "B"),
            "railcar_3": TrainSpec(600, "dn_w", "A"),
            "leviathan": TrainSpec(2000, "dn_e", "A"),
        },
        requests=(),
    )
    assembly = assemble_live(layout, scenario, state=state)
    assembly.bus.drain()  # the opening statement, which no boundary has yet
    opening = last(assembly, "allocation")
    assert "freight_1" not in opening["trains"]
    assert "freight_1" not in opening["locks"].values()

    place(assembly, "freight_1", "up_w")

    after = last(assembly, "allocation")
    assert after["trains"] == {
        "freight_1": "up_w",
        "railcar_3": "yard_w",
        "leviathan": "dn_e",
    }
    assert after["locks"] == {
        "up_w": "freight_1",
        "yard_w": "railcar_3",
        "dn_e": "leviathan",
    }


def test_a_placement_into_a_committed_block_is_dropped() -> None:
    """A resource is claimed when it is **committed** — on a route the
    dispatcher has chosen, with no lock on it yet — and that is the weaker of
    the two claims a route carries (CONTEXT.md), not no claim at all. Under
    `Incremental` a fixed route runs on ahead of its locks, so reading the
    lock table alone would call those blocks free.

    Placing a train into one strands the working that owns it: the route is
    fixed (ADR-0002), the placed train is idle and its standing lock is a
    permanent obstacle (SAFETY.md), and nothing cancels a request — so the
    committed train would be refused for the rest of the session.
    """
    layout, _ = load("crossover-yard/meet")
    # `shunter` is short enough for either yard block, so the fit rule cannot
    # do this test's work for it.
    scenario = Scenario(
        name="committed",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec(1100, "yard_w", "B"),
            "shunter": TrainSpec(600, "dn_e", "A"),
        },
        requests=(),
    )
    assembly = assemble_live(layout, scenario, Incremental)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 1)
    press(assembly, RUN_WANTED, {"run": "held"})

    picture = last(assembly, "allocation")
    [committed] = picture["requests"]
    ahead = [
        block for block in committed["route"][::2] if block not in picture["locks"]
    ]
    assert ahead, "Incremental committed no block beyond its locks"
    target = ahead[0]
    assert layout.blocks[target] >= 600, "the fit rule would drop this anyway"

    place(assembly, "shunter", target)

    assert placements(assembly) == []
    assert last(assembly, "allocation")["trains"]["shunter"] == "dn_e"
