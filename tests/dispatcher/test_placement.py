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
from tests.harness import RUN_WANTED, events, load, press, stock, ticks

PLACEMENT_WANTED = "tc49/ui/placement_wanted"
REQUEST_WANTED = "tc49/ui/request_wanted"


STOCK = stock(freight_1=1100, leviathan=2000, railcar_3=600, shunter=600)
"""The railroad's roster, one for the suite: `leviathan` at 2000mm fits
neither yard block (1400mm), so the fit rule has something to refuse."""


def two_trains() -> Scenario:
    """`crossover-yard` with no timetable at all: a railroad standing still,
    which is what a person correcting a placement is looking at.

    `leviathan` stands in `dn_e`, so the occupancy rule has something to
    refuse too.
    """
    return Scenario(
        name="placing",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec("yard_w", "B"),
            "leviathan": TrainSpec("dn_e", "A"),
        },
        requests=(),
    )


@pytest.fixture
def held() -> Assembly:
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains())
    press(assembly, RUN_WANTED, {"run": "held"})
    return assembly


def place(assembly: Assembly, train: str, block: str) -> None:
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": block})


def remove(assembly: Assembly, train: str) -> None:
    """The same gesture in the other direction: nowhere is one of the places
    a train can be said to be (ADR-0039)."""
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": None})


def removals(assembly: Assembly) -> list[dict[str, Any]]:
    return events(assembly.trace, "train_removed")


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
    layout, _roster, _ = load("crossover-yard/meet")
    running = assemble_live(layout, STOCK, two_trains())

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
    layout, _roster, _ = load("crossover-yard/meet")
    # No press: a session that adopted a picture comes up held (#154), which
    # is what makes the placement below acceptable at all.
    assembly = assemble_live(layout, STOCK, two_trains(), state=state)
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
    layout, _roster, _ = load("crossover-yard/meet")
    scenario = Scenario(
        name="unplaced",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec("yard_w", "B"),
            "railcar_3": TrainSpec("dn_w", "A"),
            "leviathan": TrainSpec("dn_e", "A"),
        },
        requests=(),
    )
    assembly = assemble_live(layout, STOCK, scenario, state=state)
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
    layout, _roster, _ = load("crossover-yard/meet")
    # `shunter` is short enough for either yard block, so the fit rule cannot
    # do this test's work for it.
    scenario = Scenario(
        name="committed",
        layout="crossover-yard",
        trains={
            "freight_1": TrainSpec("yard_w", "B"),
            "shunter": TrainSpec("dn_e", "A"),
        },
        requests=(),
    )
    assembly = assemble_live(layout, STOCK, scenario, Incremental)
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


# -- taking a train off the layout ------------------------------------------
#
# The other direction of the one gesture (ADR-0039, #170). A train off the
# layout is known and standing nowhere: absence from the picture's `trains`,
# nothing on the canvas, and its locks given up.


def test_a_removal_takes_the_train_out_of_the_picture_and_frees_what_it_held(
    held: Assembly,
) -> None:
    """A hand lifting a locomotive out of a block. The block is free the
    moment it is gone, so the release is a ledger line of its own — that is
    what happened, and nothing took the block."""
    assert last(held, "allocation")["locks"]["yard_w"] == "freight_1"

    remove(held, "freight_1")

    assert removals(held) == [
        {"boundary": 0, "event": "train_removed", "train": "freight_1"}
    ]
    assert last(held, "lock_released") == {
        "boundary": 0,
        "event": "lock_released",
        "train": "freight_1",
        "resources": ["yard_w"],
    }
    picture = last(held, "allocation")
    assert "freight_1" not in picture["trains"]
    assert picture["locks"] == {"dn_e": "leviathan"}


def test_a_train_off_the_layout_has_no_facing(held: Assembly) -> None:
    """Facing is the end of *its block* a parked train would depart through,
    so with no block there is none to hold (ADR-0019, ADR-0039)."""
    assert facing(held, "freight_1") == "yard_w.B"

    remove(held, "freight_1")

    assert "freight_1" not in last(held, "facing")["facing"]


def test_a_train_put_back_on_the_layout_gains_a_facing_again(
    held: Assembly,
) -> None:
    """Removal is not deletion: the train is still on the roster, and placing
    it is what gives it a block and a facing back."""
    remove(held, "freight_1")

    place(held, "freight_1", "up_w")

    assert last(held, "allocation")["trains"]["freight_1"] == "up_w"
    assert facing(held, "freight_1") == "up_w.A"


def test_a_removal_releases_everything_the_train_held(tmp_path: Path) -> None:
    """The sweep is by holder and not of one block. A restored crossing train
    is the one whose lock set is not obviously its standing block — it is
    between two of them (#154) — and it is also the train an operator most
    wants to lift out, there being no sensor that will ever say where it
    stopped."""
    state = tmp_path / "session.json"
    durable.write(
        state,
        {
            "tc49/dispatch/state/allocation": {
                "trains": {"freight_1": "yard_w", "leviathan": "dn_e"},
                "crossing": {"freight_1": "west_ladder.to_dn"},
                "locks": {},
                "requests": [],
            }
        },
    )
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains(), state=state)
    assembly.bus.drain()

    remove(assembly, "freight_1")

    after = last(assembly, "allocation")
    assert "freight_1" not in after["trains"]
    assert after["crossing"] == {}
    assert "freight_1" not in after["locks"].values()


def test_a_removal_is_dropped_while_the_run_is_running() -> None:
    """The same precondition as placing, for the same reason: the dispatcher
    is granting against the picture, and a block that empties under it
    invalidates what it has already granted."""
    layout, _roster, _ = load("crossover-yard/meet")
    running = assemble_live(layout, STOCK, two_trains())

    remove(running, "freight_1")

    assert removals(running) == []
    assert last(running, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_removal_of_a_train_with_a_request_in_flight_is_dropped(
    held: Assembly,
) -> None:
    """A train mid-request cannot be taken off the layout: nothing cancels a
    request, so the way out is to release the hold and let it run (#123)."""
    press(held, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(held.trace, "request_admitted")

    remove(held, "freight_1")

    assert removals(held) == []
    assert last(held, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_removal_naming_stock_the_railroad_lacks_is_dropped(
    held: Assembly,
) -> None:
    """Dropped rather than answered, a gesture having no id an answer could
    be addressed to (ADR-0034)."""
    remove(held, "ghost")

    assert removals(held) == []


def test_removing_a_train_that_is_already_off_the_layout_says_nothing(
    held: Assembly,
) -> None:
    """The gesture asks for the state the train is in. There is no fact to
    announce, and announcing one would put a second removal in the trace and
    on every view."""
    remove(held, "freight_1")

    remove(held, "freight_1")

    assert len(removals(held)) == 1


def test_a_request_for_a_train_just_taken_off_the_layout_is_answered(
    held: Assembly,
) -> None:
    """Off the layout is a place a train can be, so a request naming one is
    answered rather than raised — `no_origin`, there being no block to depart
    from (ADR-0039, ADR-0021).

    Submitted at the dispatcher's own topic, because a *gesture* for such a
    train never becomes a request: the scheduler composes the departure end
    out of facing, and a train off the layout has none, so it drops the drag
    in silence (ADR-0036). What gets this far is a timetable, or a page whose
    frame reached the bus by another road.
    """
    remove(held, "freight_1")
    press(held, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(held.trace, "request_submitted") == []

    press(
        held,
        "tc49/schedule/request_submitted",
        {
            "id": "freight_1-9",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )

    assert last(held, "request_rejected")["reason"] == "no_origin"


def test_a_run_may_come_up_with_an_empty_layout() -> None:
    """The cold start once a scenario places nothing: every train known and
    off the layout, nothing on the rails, and nothing to do but place them
    (ADR-0039). No adoption and no picture, so the run comes up running and
    the hold is a press like any other."""
    layout, _roster, _ = load("crossover-yard/meet")
    empty = Scenario(name="empty", layout="crossover-yard", trains={}, requests=())
    assembly = assemble_live(layout, STOCK, empty)
    assembly.bus.drain()

    opening = last(assembly, "allocation")
    assert opening["trains"] == {} and opening["locks"] == {}
    assert events(assembly.trace, "lock_granted") == []
    assert last(assembly, "facing")["facing"] == {}

    press(assembly, RUN_WANTED, {"run": "held"})
    place(assembly, "freight_1", "yard_w")

    assert last(assembly, "allocation")["trains"] == {"freight_1": "yard_w"}
    assert facing(assembly, "freight_1") == "yard_w.B"
