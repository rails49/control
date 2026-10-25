"""A person says where a train actually stands (#152, #821).

`tc49/dispatch/placement_wanted` is the correction an operator makes with their own
eyes: this train is *here*. One gesture, one authority — the dispatcher alone
reads it, because "is that block free" is knowledge only it has, and having
accepted it announces `tc49/dispatch/train_placed` for everyone else to
follow. The scheduler follows that event and carries the train's facing
into the new block; it never reads the gesture.

Placing at any power, into a block that is **free** — no lock on it and on no
active train's route — and that the train fits; taking a train off at any
power too (ADR-0069, `test_remove_running`). Anything else is refused on
`tc49/dispatch/placement_refused`, naming the train, the block and why
(ADR-0092, decision 3): the answer names what the gesture named, so it needs
no id (ADR-0034). A gesture that cannot be read as a placement names no train,
and is still dropped with no answer.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, assemble_live
from tc49.dispatcher import Dispatcher, FullRoute, Incremental
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import OFF, ON
from tc49.lib.rejection import PlacementRefusal
from tc49.lib.roster import Roster
from tc49.lib.scenario import TrainSpec
from tests.harness import events, load, minted, power, press, stock, ticks

PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"


STOCK = stock(freight_1=1100, leviathan=2000, railcar_3=600, shunter=600)
"""The railroad's roster, one for the suite: `leviathan` at 2000mm fits
neither yard block (1400mm), so the fit rule has something to refuse."""


def two_trains() -> dict[str, TrainSpec]:
    """`crossover-yard` with no timetable at all: a railroad standing still,
    which is what a person correcting a placement is looking at.

    `leviathan` stands in `dn_e`, so the occupancy rule has something to
    refuse too.
    """
    return {
        "freight_1": TrainSpec("yard_w", "A-to-B"),
        "leviathan": TrainSpec("dn_e", "B-to-A"),
    }


@pytest.fixture
def off() -> Assembly:
    """The two trains standing, and the power off: where a person putting
    locomotives on the rails usually is."""
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains())
    press(assembly, *power(OFF))
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


def refusals(assembly: Assembly) -> list[tuple[str, str | None, str]]:
    """Every `placement_refused`, as train, block and reason."""
    return [
        (line["train"], line["block"], line["reason"])
        for line in events(assembly.trace, "placement_refused")
    ]


def locks(assembly: Assembly) -> dict[str, str]:
    return dict(last(assembly, "allocation")["locks"])


def placements(assembly: Assembly) -> list[dict[str, Any]]:
    return events(assembly.trace, "train_placed")


def cancellations(assembly: Assembly) -> list[dict[str, Any]]:
    return events(assembly.trace, "request_cancelled")


def order(assembly: Assembly, *leaves: str) -> list[str]:
    """The named leaves in the order the trace carries them, which is the
    order they were published in."""
    return [
        str(line["event"]) for line in events(assembly.trace) if line["event"] in leaves
    ]


def facing(assembly: Assembly, train: str) -> str:
    return str(last(assembly, "facing")["facing"][train])


def test_a_placement_moves_the_lock_and_redraws_the_picture(off: Assembly) -> None:
    """Every parked train holds the lock on the block it stands in
    (GLOSSARY.md), so placing one is moving that lock; the picture is
    republished because a joining client draws from it and nothing else."""
    before = last(off, "allocation")
    assert before["locks"]["yard_w"] == "freight_1"

    place(off, "freight_1", "up_w")

    assert placements(off) == [
        {"time": 0.0, "event": "train_placed", "train": "freight_1", "block": "up_w"}
    ]
    picture = last(off, "allocation")
    assert picture["trains"]["freight_1"] == "up_w"
    assert picture["locks"] == {"dn_e": "leviathan", "up_w": "freight_1"}


def test_the_scheduler_carries_facing_into_the_new_block(off: Assembly) -> None:
    """Facing is not part of placing: the gesture names a train and a block,
    the run across it comes over unchanged, and `reversal_wanted` is the
    correction where that lands the train the wrong way round (ADR-0019).
    Which run is arbitrary because the layout is topological and there is
    nothing better to derive from."""
    assert facing(off, "freight_1") == "yard_w.A-to-B"

    place(off, "freight_1", "up_w")

    assert facing(off, "freight_1") == "up_w.A-to-B"


def test_facing_never_names_the_wall_of_a_terminal_block(off: Assembly) -> None:
    """`yard_e.B` is the buffer stop and is in no connection. Every facing
    site goes through `connected_facing`, so the run carried over is turned
    to the one end the train can leave by (#145) rather than pointing it at
    the wall."""
    place(off, "freight_1", "yard_e")

    assert facing(off, "freight_1") == "yard_e.B-to-A"


def test_a_placement_into_a_free_block_is_accepted_while_on() -> None:
    """Placing is accepted at any power (#821): what decides it is whether
    the block is free, and a free block is one no grant can be about to send
    a train into, so placing there while the dispatcher routes races with
    nothing it is deciding."""
    layout, _roster, _ = load("crossover-yard/meet")
    on = assemble_live(layout, STOCK, two_trains())
    on.bus.drain()
    assert on.dispatcher.state.power == ON

    place(on, "freight_1", "up_w")

    assert placements(on) == [
        {"time": 0.0, "event": "train_placed", "train": "freight_1", "block": "up_w"}
    ]
    assert last(on, "allocation")["trains"]["freight_1"] == "up_w"


def test_a_placement_into_a_block_another_route_claims_is_refused_while_on() -> None:
    """The other half: a block on another train's route is not free, locked
    yet or not, and standing a train there would put it in front of a train
    the dispatcher is sending through. Under `Incremental` the route runs on
    ahead of its locks, which is the claim the lock table alone would miss."""
    layout, _roster, _ = load("crossover-yard/meet")
    on = assemble_live(layout, STOCK, two_trains(), Incremental)
    press(on, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    route = last(on, "route_chosen")["route"]
    ahead = [
        block for block in route[::2] if block not in last(on, "allocation")["locks"]
    ]
    assert ahead, "the route has no block it has not locked yet"

    place(on, "shunter", ahead[0])

    assert placements(on) == []
    assert refusals(on) == [("shunter", ahead[0], PlacementRefusal.NOT_FREE)]
    assert last(on, "allocation")["trains"].get("shunter") is None


def test_a_placement_into_an_occupied_block_is_refused(off: Assembly) -> None:
    """Two trains in one block is two holders of one lock, and the second
    would stand in a block nothing holds for it."""
    before = locks(off)

    place(off, "freight_1", "dn_e")

    assert placements(off) == []
    assert refusals(off) == [("freight_1", "dn_e", PlacementRefusal.NOT_FREE)]
    assert locks(off) == before
    assert before["dn_e"] == "leviathan"


def test_a_placement_into_a_block_the_train_does_not_fit_in_is_refused(
    off: Assembly,
) -> None:
    """The same fit the admission check applies to an arrival end, asked of
    a placement: the operator cannot report a train into a block it is longer
    than."""
    before = locks(off)

    place(off, "leviathan", "yard_e")

    assert placements(off) == []
    assert refusals(off) == [("leviathan", "yard_e", PlacementRefusal.NO_FIT)]
    assert locks(off) == before
    assert last(off, "allocation")["trains"]["leviathan"] == "dn_e"


def test_a_placement_cancels_the_request_in_flight_and_then_places(
    off: Assembly,
) -> None:
    """A request in flight was a precondition and is not one any more
    (ADR-0049, #271): the gesture ends the request and then stands the train,
    so `request_cancelled` comes before `train_placed` and the fact describes
    a train with no request.

    What the old precondition protected is kept by the cancellation rather
    than by the refusal. On release the grant phase launches from `block_of`,
    and there is no longer a request to launch from anywhere: the queued one
    was admitted against the block the train has just been moved out of, and
    it ends with the gesture that moved it.
    """
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(off.trace, "request_admitted")

    place(off, "freight_1", "up_w")

    assert cancellations(off) == [
        {
            "time": 0.0,
            "event": "request_cancelled",
            "id": minted(off, "freight_1"),
            "reason": "displaced",
        }
    ]
    assert placements(off) == [
        {"time": 0.0, "event": "train_placed", "train": "freight_1", "block": "up_w"}
    ]
    assert last(off, "allocation")["trains"]["freight_1"] == "up_w"
    assert last(off, "allocation")["requests"] == []
    assert order(off, "request_cancelled", "train_placed") == [
        "request_cancelled",
        "train_placed",
    ]


def test_a_displaced_train_never_departs_on_the_cancelled_route(
    off: Assembly,
) -> None:
    """The whole point of ending the request rather than refusing the
    placement: turning the power on afterwards moves no wheel on work the person
    has already ended, and the route that was chosen against the old block is
    not run from the new one."""
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    place(off, "freight_1", "up_w")

    press(off, *power(ON))
    ticks(off, 8)

    assert events(off.trace, "route_chosen") == []
    assert events(off.trace, "move_granted") == []
    assert last(off, "allocation")["trains"]["freight_1"] == "up_w"


def test_a_placement_over_an_outstanding_move_retires_the_request_at_once() -> None:
    """The derailment, exactly: a train granted a move, the power off under
    it, and a person who can see the locomotive is not where the sensors say
    it is going.

    A `cancel_wanted` would defer here, nothing on the bus retracting a
    `move` already sent. A placement does not: the person is answering the
    move the sensors may never answer, so the request retires at the gesture
    and the train is stood where they say it is (ADR-0049).

    A sensor that does arrive afterwards explains nothing and drains the
    railroad (ADR-0048) — which is the right answer to a detector firing
    under a train somebody has moved by hand, and a no-op here because the
    power is already off.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains(), FullRoute)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    press(assembly, *power(OFF))
    picture = last(assembly, "allocation")
    assert picture["crossing"]["freight_1"], "no move is outstanding"

    place(assembly, "freight_1", "up_w")

    assert last(assembly, "request_cancelled") == {
        "time": 0.0,
        "event": "request_cancelled",
        "id": minted(assembly, "freight_1"),
        "reason": "displaced",
    }
    after = last(assembly, "allocation")
    assert after["trains"]["freight_1"] == "up_w"
    assert after["crossing"] == {}
    assert after["requests"] == []
    assert after["locks"] == {"up_w": "freight_1", "dn_e": "leviathan"}

    ticks(assembly, 4)  # the sensors of the move nobody is making any more

    # The harness's own press and nothing since: no drain asked of `off`.
    assert [line["power"] for line in events(assembly.trace, "power_wanted")] == [ON]
    assert last(assembly, "allocation")["trains"]["freight_1"] == "up_w"


def test_a_placement_the_railroad_cannot_accept_changes_nothing(
    off: Assembly,
) -> None:
    """The block is judged before the request is cancelled, so a refusal
    leaves the request standing (#1062). A block another train stands in is
    refused, and so is one the railroad does not have."""
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    before = last(off, "allocation")["requests"]

    place(off, "freight_1", "dn_e")  # leviathan is standing there
    place(off, "freight_1", "siding_9")

    assert cancellations(off) == []
    assert placements(off) == []
    assert refusals(off) == [
        ("freight_1", "dn_e", PlacementRefusal.NOT_FREE),
        ("freight_1", "siding_9", PlacementRefusal.UNKNOWN_BLOCK),
    ]
    assert last(off, "allocation")["trains"]["freight_1"] == "yard_w"
    assert last(off, "allocation")["locks"]["dn_e"] == "leviathan"
    assert last(off, "allocation")["requests"] == before


def test_a_crossing_train_put_back_where_it_stands_keeps_its_move() -> None:
    """A person sets a moving train down in the block it is departing. That
    block is its standing lock and not free, so the placement is refused, and
    the move it is making keeps its route: released under it, nothing would
    tell `layout`, which would go on driving it (#1062)."""
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains(), FullRoute)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    press(assembly, *power(OFF))
    before = last(assembly, "allocation")
    assert before["crossing"]["freight_1"], "no move is outstanding"

    place(assembly, "freight_1", "yard_w")

    assert refusals(assembly) == [("freight_1", "yard_w", PlacementRefusal.NOT_FREE)]
    assert cancellations(assembly) == []
    after = last(assembly, "allocation")
    assert after["crossing"] == before["crossing"]
    assert after["locks"] == before["locks"]
    assert after["requests"] == before["requests"]


def test_a_placement_into_a_block_the_trains_own_route_holds_succeeds() -> None:
    """Cancelling first is what makes the placement possible rather than
    merely permitted. Under `FullRoute` a launch locks the whole route, so
    every block the train was going to run through is one `free` would refuse
    — for a claim belonging to the very request the gesture is ending.

    This is the derailment: the train stopped somewhere along its route, and
    the person says where.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains(), FullRoute)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    route = last(assembly, "route_chosen")["route"]
    press(assembly, *power(OFF))
    ahead = route[2]  # the first block beyond the origin, locked by the launch
    assert last(assembly, "allocation")["locks"][ahead] == "freight_1"

    place(assembly, "freight_1", ahead)

    assert last(assembly, "request_cancelled")["reason"] == "displaced"
    assert last(assembly, "train_placed")["block"] == ahead
    assert last(assembly, "allocation")["locks"] == {
        ahead: "freight_1",
        "dn_e": "leviathan",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"train": "freight_1"},
        {"train": 7, "block": "up_w"},
        {"train": "freight_1", "block": 42},
        "freight_1 in up_w",
    ],
    ids=[
        "no fields",
        "no block key",
        "train not a name",
        "block not a name",
        "not an object",
    ],
)
def test_a_gesture_that_cannot_be_read_at_all_is_dropped(
    off: Assembly, payload: object
) -> None:
    """Anyone may publish on the topic and nothing authenticates them, so the
    gesture is read and never subscripted: what cannot be read moves no train
    and takes no app down (BUS.md, rule 4). The missing `block` key is a
    frame that lost a field, not a train taken off the layout — the key's
    presence is load-bearing, and a `null` a page wrote is the removal."""
    press(off, PLACEMENT_WANTED, cast(Any, payload))

    assert placements(off) == []
    assert removals(off) == []
    assert refusals(off) == []
    assert last(off, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_placement_naming_stock_the_railroad_lacks_is_refused(
    off: Assembly,
) -> None:
    """Answered with what the gesture named, which is how a reader matches
    the answer to its drag with no id (ADR-0092, decision 3)."""
    before = locks(off)

    place(off, "ghost", "up_w")

    assert placements(off) == []
    assert refusals(off) == [("ghost", "up_w", PlacementRefusal.UNKNOWN_TRAIN)]
    assert locks(off) == before


def test_a_placement_naming_track_the_railroad_lacks_is_refused(
    off: Assembly,
) -> None:
    before = locks(off)

    place(off, "freight_1", "siding_9")
    place(off, "freight_1", "up_w.A")  # an end is not a block

    assert placements(off) == []
    assert refusals(off) == [
        ("freight_1", "siding_9", PlacementRefusal.UNKNOWN_BLOCK),
        ("freight_1", "up_w.A", PlacementRefusal.UNKNOWN_BLOCK),
    ]
    assert locks(off) == before


def test_the_released_run_departs_from_where_the_train_was_put(
    off: Assembly,
) -> None:
    """The whole point of the gesture: what the dispatcher grants next comes
    off the corrected picture, and the steel under it agrees — the simulator
    stands in for a hand that lifted a locomotive, so it is told where the
    hand put it (ADR-0030)."""
    place(off, "freight_1", "up_w")
    press(off, *power(ON))
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(off, 12)

    assert last(off, "route_chosen")["route"][0] == "up_w"
    assert events(off.trace, "request_rejected") == []
    assert last(off, "request_completed")["id"] == minted(off, "freight_1")
    assert last(off, "allocation")["trains"]["freight_1"] == "yard_e"


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
    kept: dict[str, Payload] = {
        "tc49/dispatch/state/allocation": {
            "trains": {"freight_1": "yard_w", "leviathan": "dn_e"},
            "crossing": {
                "freight_1": "west_ladder.to_dn",
                "leviathan": "east_ladder.from_dn",
            },
            "locks": {},
            "requests": [],
        }
    }
    layout, _roster, _ = load("crossover-yard/meet")
    # No press: a placement is accepted at any power (#821).
    assembly = assemble_live(layout, STOCK, two_trains(), retained=kept)
    assembly.bus.drain()  # the opening statement, which no boundary has yet
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
    a request of an evening ago that completed.

    So the placement has no standing lock to move, only one to take.
    """
    kept: dict[str, Payload] = {
        "tc49/dispatch/state/allocation": {
            "trains": {"freight_1": "dn_e", "railcar_3": "yard_w"},
            "crossing": {},
            "locks": {},
            "requests": [],
        }
    }
    layout, _roster, _ = load("crossover-yard/meet")
    stood = {
        "freight_1": TrainSpec("yard_w", "A-to-B"),
        "railcar_3": TrainSpec("dn_w", "B-to-A"),
        "leviathan": TrainSpec("dn_e", "B-to-A"),
    }
    assembly = assemble_live(layout, STOCK, stood, retained=kept)
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
    the two claims a route carries (GLOSSARY.md), not no claim at all. Under
    `Incremental` a fixed route runs on ahead of its locks, so reading the
    lock table alone would call those blocks free.

    Placing a train into one strands the request that owns it: the route is
    fixed (ADR-0002), and the placed train is idle, so its standing lock is a
    permanent obstacle (SAFETY.md) and the committed train would be refused
    for the rest of the session. A placement cancels its **own** train's
    request (ADR-0049) and never another's, so what is refused here is a
    claim the gesture has no way to release.
    """
    layout, _roster, _ = load("crossover-yard/meet")
    # `shunter` is short enough for either yard block, so the fit rule cannot
    # do this test's work for it.
    stood = {
        "freight_1": TrainSpec("yard_w", "A-to-B"),
        "shunter": TrainSpec("dn_e", "B-to-A"),
    }
    assembly = assemble_live(layout, STOCK, stood, Incremental)
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 1)
    press(assembly, *power(OFF))

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
    assert refusals(assembly) == [("shunter", target, PlacementRefusal.NOT_FREE)]
    assert last(assembly, "allocation")["trains"]["shunter"] == "dn_e"


# -- taking a train off the layout ------------------------------------------
#
# The other direction of the one gesture (ADR-0039, #170). A train off the
# layout is known and standing nowhere: absence from the picture's `trains`,
# nothing on the canvas, and its locks given up.


def test_a_removal_takes_the_train_out_of_the_picture_and_frees_what_it_held(
    off: Assembly,
) -> None:
    """A hand lifting a locomotive out of a block. The block is free the
    moment it is gone, so the release is a ledger line of its own — that is
    what happened, and nothing took the block."""
    assert last(off, "allocation")["locks"]["yard_w"] == "freight_1"

    remove(off, "freight_1")

    assert removals(off) == [
        {"time": 0.0, "event": "train_removed", "train": "freight_1"}
    ]
    assert last(off, "lock_released") == {
        "time": 0.0,
        "event": "lock_released",
        "train": "freight_1",
        "resources": ["yard_w"],
    }
    picture = last(off, "allocation")
    assert "freight_1" not in picture["trains"]
    assert picture["locks"] == {"dn_e": "leviathan"}


def test_a_train_off_the_layout_has_no_facing(off: Assembly) -> None:
    """Facing is the end of *its block* a parked train would depart through,
    so with no block there is none to hold (ADR-0019, ADR-0039)."""
    assert facing(off, "freight_1") == "yard_w.A-to-B"

    remove(off, "freight_1")

    assert "freight_1" not in last(off, "facing")["facing"]


def test_a_train_put_back_on_the_layout_gains_a_facing_again(
    off: Assembly,
) -> None:
    """Removal is not deletion: the train is still on the roster, and placing
    it is what gives it a block and a facing back."""
    remove(off, "freight_1")

    place(off, "freight_1", "up_w")

    assert last(off, "allocation")["trains"]["freight_1"] == "up_w"
    assert facing(off, "freight_1") == "up_w.B-to-A"


def test_a_removal_releases_everything_the_train_held(tmp_path: Path) -> None:
    """The sweep is by holder and not of one block. A restored crossing train
    is the one whose lock set is not obviously its standing block — it is
    between two of them (#154) — and it is also the train an operator most
    wants to lift out, there being no sensor that will ever say where it
    stopped."""
    kept: dict[str, Payload] = {
        "tc49/dispatch/state/allocation": {
            "trains": {"freight_1": "yard_w", "leviathan": "dn_e"},
            "crossing": {"freight_1": "west_ladder.to_dn"},
            "locks": {},
            "requests": [],
        }
    }
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, two_trains(), retained=kept)
    assembly.bus.drain()

    remove(assembly, "freight_1")

    after = last(assembly, "allocation")
    assert "freight_1" not in after["trains"]
    assert after["crossing"] == {}
    assert "freight_1" not in after["locks"].values()


def test_a_removal_cancels_the_request_in_flight_and_then_lifts_the_train(
    off: Assembly,
) -> None:
    """The other direction of the same gesture, and the case #237 asked for:
    a train mid-request is taken off the layout, its request cancelled
    `removed` on the way (ADR-0049, #271). A broken-down locomotive comes off
    in a person's hand, rather than the power being turned on so the railroad
    can run it to a destination it is no longer going to.

    `request_cancelled` precedes `train_removed`, so the fact describes a
    train with no request — which is what lets the scheduler drop the facing
    on it without wondering whether something still wants it.
    """
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(off.trace, "request_admitted")

    remove(off, "freight_1")

    assert cancellations(off) == [
        {
            "time": 0.0,
            "event": "request_cancelled",
            "id": minted(off, "freight_1"),
            "reason": "removed",
        }
    ]
    assert removals(off) == [
        {"time": 0.0, "event": "train_removed", "train": "freight_1"}
    ]
    picture = last(off, "allocation")
    assert "freight_1" not in picture["trains"]
    assert picture["requests"] == []
    assert order(off, "request_cancelled", "train_removed") == [
        "request_cancelled",
        "train_removed",
    ]


def test_a_removal_naming_stock_the_railroad_lacks_is_refused(
    off: Assembly,
) -> None:
    """The removal is the same gesture, so it is refused the same way, its
    `null` block carried back as it came."""
    before = locks(off)

    remove(off, "ghost")

    assert removals(off) == []
    assert refusals(off) == [("ghost", None, PlacementRefusal.UNKNOWN_TRAIN)]
    assert locks(off) == before


def test_removing_a_train_that_is_already_off_the_layout_says_nothing(
    off: Assembly,
) -> None:
    """The gesture asks for the state the train is in. There is no fact to
    announce, and announcing one would put a second removal in the trace and
    on every view. Nor is it refused: what it asked for holds."""
    remove(off, "freight_1")

    remove(off, "freight_1")

    assert len(removals(off)) == 1
    assert refusals(off) == []


def test_a_request_for_a_train_just_taken_off_the_layout_is_answered(
    off: Assembly,
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
    remove(off, "freight_1")
    press(off, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assert events(off.trace, "request_submitted") == []

    press(
        off,
        "tc49/dispatch/request_submitted",
        {
            "id": "freight_1-9",
            "train": "freight_1",
            "depart": "yard_w.B",
            "dest": ["yard_e.A"],
        },
    )

    assert last(off, "request_rejected")["reason"] == "no_origin"


def test_a_run_may_come_up_with_an_empty_layout_and_be_placed_into() -> None:
    """The ordinary cold start of a run an operator drives (ADR-0039): every
    train known and off the layout, nothing on the rails, and nothing to do
    but place them and turn the power on — in either order, because a
    placement is accepted at any power (#821)."""
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK)
    assembly.bus.drain()

    opening = last(assembly, "allocation")
    assert opening["trains"] == {} and opening["locks"] == {}
    assert events(assembly.trace, "lock_granted") == []
    assert last(assembly, "facing")["facing"] == {}

    place(assembly, "freight_1", "yard_w")

    assert last(assembly, "allocation")["trains"] == {"freight_1": "yard_w"}
    assert facing(assembly, "freight_1") == "yard_w.A-to-B"


def test_a_hand_placed_train_no_document_placed_survives_a_restart(
    tmp_path: Path,
) -> None:
    """Adoption keeps the picture's word for every train the **railroad**
    owns, not only for the ones a document placed (ADR-0039).

    The train an operator put on the rails by hand is exactly the one no
    document names, and it is standing there: a session that came back up
    without it would believe the block free and hand it to the next train,
    with a locomotive in it.
    """
    kept: dict[str, Payload] = {
        "tc49/dispatch/state/allocation": {
            "trains": {"shunter": "up_w"},
            "crossing": {},
            "locks": {},
            "requests": [],
        }
    }
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, retained=kept)
    assembly.bus.drain()

    picture = last(assembly, "allocation")
    assert picture["trains"] == {"shunter": "up_w"}
    assert picture["locks"] == {"up_w": "shunter"}


def test_a_picture_naming_stock_the_railroad_lacks_is_not_adopted(
    tmp_path: Path,
) -> None:
    """The roster is what makes a train known, so a name the railroad does not
    own is a picture from another railroad or another day."""
    kept: dict[str, Payload] = {
        "tc49/dispatch/state/allocation": {
            "trains": {"ghost": "up_w"},
            "crossing": {},
            "locks": {},
            "requests": [],
        }
    }
    layout, _roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, STOCK, retained=kept)
    assembly.bus.drain()

    assert last(assembly, "allocation")["trains"] == {}


def built(
    roster: Roster, reread: Callable[[], Roster | None]
) -> tuple[InProcessBus, list[Payload]]:
    """A dispatcher for a run an operator drives, built on `crossover-yard`
    from `roster`, that reads the roster again through `reread`; and every
    `train_placed` it publishes."""
    layout, _roster, _ = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    placed: list[Payload] = []
    bus.subscribe(
        "tc49/dispatch/train_placed", lambda _, payload: placed.append(payload)
    )
    Dispatcher(bus, layout, roster, {}, Incremental(layout, DEFAULT_K), reread=reread)
    bus.drain()
    return bus, placed


def put(bus: InProcessBus, train: str, block: str) -> None:
    bus.publish(PLACEMENT_WANTED, {"train": train, "block": block})
    bus.drain()


def test_a_train_made_after_the_build_is_placed_from_the_roster_read_again() -> None:
    """A train made in the stock view after the last build is on the store's
    roster and not the dispatcher's: its placement reads the roster once more
    and is then judged as any other (ADR-0092, decision 1)."""
    reads: list[None] = []

    def reread() -> Roster:
        reads.append(None)
        return stock(freight_1=1100, railcar_3=600)

    bus, placed = built(stock(freight_1=1100), reread)
    put(bus, "railcar_3", "yard_w")

    assert reads == [None]
    assert placed == [{"train": "railcar_3", "block": "yard_w"}]


def test_a_train_the_store_lacks_too_is_refused_as_unknown() -> None:
    """`unknown_train` is said only after the read: the store not answering
    and the store not having it are refused alike (ADR-0092, decision 3)."""
    reads: list[None] = []

    def reread() -> Roster | None:
        reads.append(None)
        return None if len(reads) == 1 else stock(freight_1=1100)

    bus, placed = built(stock(freight_1=1100), reread)
    refused: list[Payload] = []
    bus.subscribe(
        "tc49/dispatch/placement_refused", lambda _, payload: refused.append(payload)
    )
    put(bus, "ghost", "yard_w")
    put(bus, "ghost", "yard_w")

    assert len(reads) == 2
    assert placed == []
    assert refused == 2 * [
        {"train": "ghost", "block": "yard_w", "reason": "unknown_train"}
    ]


def test_a_train_the_dispatcher_has_keeps_the_length_it_was_built_with() -> None:
    """A changed length waits for a build (ADR-0071): the read adds what the
    dispatcher lacks and leaves what it has alone. `freight_1` at 1100 fits a
    1400 yard block, and at the store's 2000 would not."""
    bus, placed = built(
        stock(freight_1=1100), lambda: stock(freight_1=2000, railcar_3=600)
    )
    put(bus, "railcar_3", "up_w")
    put(bus, "freight_1", "yard_w")

    assert placed == [
        {"train": "railcar_3", "block": "up_w"},
        {"train": "freight_1", "block": "yard_w"},
    ]
