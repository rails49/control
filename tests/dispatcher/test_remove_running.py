"""A train comes off while running, and its track opens when it reads clear
(ADR-0069, #669).

`placement_wanted` with `block: null` is accepted in any run state. What the
train held is released at once, except each block that still reads occupied:
that one stays held by the train until a detector says it is clear, and the
transit it was crossing stays held until both its blocks have opened. The
clear reading that opens such a block is explained — it releases the block and
does not hold the run.

Driven at the bus, with the detector readings pressed by hand where a test
wants a level the simulator has not reported. The simulator stands in for the
hand (#672): on `train_removed` it reads clear every block its own detectors
read occupied for the train, so a train it moved comes off in one cascade. The
gesture made before the hand is a train standing on a reading the simulator
never made, which nothing lifts until the test says so.
"""

from typing import Any, cast

from tc49.bench.runner import Assembly
from tests.harness import RUN_WANTED, events, live, minted, press, runs, ticks

PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"


def remove(assembly: Assembly, train: str) -> None:
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": None})


def place(assembly: Assembly, train: str, block: str) -> None:
    press(assembly, PLACEMENT_WANTED, {"train": train, "block": block})


def reading(assembly: Assembly, topic: str, block: str) -> None:
    press(assembly, topic, {"block": block})


def last(assembly: Assembly, leaf: str) -> dict[str, Any]:
    return events(assembly.trace, leaf)[-1]


def locks(assembly: Assembly) -> dict[str, str]:
    return cast(dict[str, str], last(assembly, "allocation")["locks"])


def released(assembly: Assembly) -> list[list[str]]:
    return [line["resources"] for line in events(assembly.trace, "lock_released")]


def arrived() -> Assembly:
    """`crossover-yard/meet` running, freight_1 run to `yard_e` and standing
    there, its block read occupied by the simulator."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 8)
    state = assembly.dispatcher.state
    assert state.block_of["freight_1"] == "yard_e"
    assert not state.active and state.reported["yard_e"] is True
    return assembly


def standing() -> Assembly:
    """`crossover-yard/meet` running, freight_1 standing in `yard_w` where the
    scenario put it, its detector pressed occupied and the run resumed from
    the hold that first reading raises (ADR-0048): a train at rest with a
    detector under it that the simulator never read, so nothing lifts it
    until the test does."""
    assembly = live("crossover-yard/meet")
    reading(assembly, OCCUPIED, "yard_w")
    press(assembly, RUN_WANTED, {"run": "running"})
    state = assembly.dispatcher.state
    assert state.block_of["freight_1"] == "yard_w"
    assert state.reported["yard_w"] is True
    assert runs(assembly) == ["running", "held", "running"]
    return assembly


def crossing() -> Assembly:
    """freight_1 between two blocks: its head reported in `dn_e`, its tail
    still in `dn_w`, both reading occupied, and the rest of its route ahead
    locked and never reported."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 3)
    state = assembly.dispatcher.state
    assert state.crossing == {"freight_1": "crossover.dn_straight"}
    assert state.reported["dn_w"] is True and state.reported["dn_e"] is True
    return assembly


def test_a_block_reading_occupied_stays_held_until_it_reads_clear() -> None:
    """The case the decision exists for: the gesture before the hand. The
    loco still stands in the block, so the block stays the train's; the
    detector going clear is the lift, and it opens the block without
    stopping anybody."""
    assembly = standing()

    remove(assembly, "freight_1")

    assert last(assembly, "train_removed")["train"] == "freight_1"
    assert "freight_1" not in last(assembly, "allocation")["trains"]
    assert locks(assembly)["yard_w"] == "freight_1"

    reading(assembly, VACATED, "yard_w")

    assert released(assembly)[-1] == ["yard_w"]
    assert "yard_w" not in locks(assembly)
    assert runs(assembly) == ["running", "held", "running"]


def test_a_train_the_simulator_moved_comes_off_in_one_cascade() -> None:
    """The simulator is the hand (#672): it reads clear the block it read
    the train into, and that reading opens the block like any other lift."""
    assembly = arrived()

    remove(assembly, "freight_1")

    assert released(assembly)[-1] == ["yard_e"]
    assert "yard_e" not in locks(assembly)
    assert runs(assembly) == ["running"]


def test_a_block_never_reported_is_released_at_once() -> None:
    """A block the layout has said nothing about has nothing to wait for."""
    assembly = live("crossover-yard/meet")

    remove(assembly, "freight_1")

    assert last(assembly, "train_removed")["train"] == "freight_1"
    assert released(assembly) == [["yard_w"]]
    assert "yard_w" not in locks(assembly)
    assert runs(assembly) == ["running"]


def test_a_train_with_a_request_is_cancelled_and_its_clear_route_opens() -> None:
    """The request ends `removed` before the train comes off, and the route
    ahead — blocks no detector has under a loco — is released in the one
    line, with what the loco still stands on kept until the simulator, as
    the hand, reads it clear on the next."""
    assembly = live("crossover-yard/meet")
    press(assembly, REQUEST_WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    ticks(assembly, 2)
    state = assembly.dispatcher.state
    assert state.block_of["freight_1"] == "dn_w" and state.reported["dn_w"] is True
    before = len(released(assembly))

    remove(assembly, "freight_1")

    leaves = [line["event"] for line in events(assembly.trace)]
    assert leaves.index("request_cancelled") < leaves.index("train_removed")
    assert last(assembly, "request_cancelled") == {
        "time": last(assembly, "request_cancelled")["time"],
        "event": "request_cancelled",
        "id": minted(assembly, "freight_1"),
        "reason": "removed",
    }
    assert released(assembly)[before:] == [
        ["dn_e", "east_ladder.from_dn", "yard_e"],
        ["crossover.dn_straight", "dn_w"],
    ]
    assert locks(assembly) == {"up_e": "express_2"}
    assert not state.active and not state.crossing
    assert runs(assembly) == ["running"]


def test_a_crossing_train_keeps_its_transit_until_both_blocks_read_clear() -> None:
    """Head in one block and tail in the other: both read occupied, so both
    stay held and so does the transit between them. The simulator, as the
    hand, reads both clear in the order it read them occupied: the first
    clear opens its block alone; the second opens its block and the transit
    together."""
    assembly = crossing()
    before = len(released(assembly))

    remove(assembly, "freight_1")

    assert released(assembly)[before:] == [
        ["east_ladder.from_dn", "yard_e"],
        ["dn_w"],
        ["crossover.dn_straight", "dn_e"],
    ]
    assert locks(assembly) == {"up_e": "express_2"}
    assert runs(assembly) == ["running"]


def test_putting_a_train_on_a_block_still_needs_the_run_held() -> None:
    """That direction takes a lock, and ADR-0039's reason applies to it
    unchanged."""
    assembly = live("crossover-yard/meet")

    place(assembly, "freight_1", "dn_w")

    assert events(assembly.trace, "train_placed") == []
    assert last(assembly, "allocation")["trains"]["freight_1"] == "yard_w"


def test_a_removed_train_may_be_put_back_into_a_block_it_still_holds() -> None:
    """The block is the train's own claim, so it is free to that train, and
    the residual lock becomes its standing lock."""
    assembly = standing()
    press(assembly, RUN_WANTED, {"run": "held"})
    remove(assembly, "freight_1")

    place(assembly, "freight_1", "yard_w")

    assert last(assembly, "train_placed") == {
        "time": last(assembly, "train_placed")["time"],
        "event": "train_placed",
        "train": "freight_1",
        "block": "yard_w",
    }
    assert last(assembly, "allocation")["trains"]["freight_1"] == "yard_w"
    assert locks(assembly)["yard_w"] == "freight_1"


def test_another_train_is_refused_a_block_a_removed_train_still_holds() -> None:
    assembly = standing()
    press(assembly, RUN_WANTED, {"run": "held"})
    remove(assembly, "freight_1")

    place(assembly, "express_2", "yard_w")

    assert events(assembly.trace, "train_placed") == []
    assert locks(assembly)["yard_w"] == "freight_1"


def test_a_held_removal_keeps_an_occupied_block_as_a_running_one_does() -> None:
    assembly = standing()
    press(assembly, RUN_WANTED, {"run": "held"})

    remove(assembly, "freight_1")

    assert locks(assembly)["yard_w"] == "freight_1"
    reading(assembly, VACATED, "yard_w")
    assert released(assembly)[-1] == ["yard_w"]
    assert runs(assembly) == ["running", "held", "running", "held"]


def test_a_put_back_train_is_a_standing_train_again() -> None:
    """Once the residual lock is a standing lock, a clear reading under it is
    what ADR-0048 says it is: a train the dispatcher believes stands there
    and the detector says does not."""
    assembly = standing()
    press(assembly, RUN_WANTED, {"run": "held"})
    remove(assembly, "freight_1")
    place(assembly, "freight_1", "yard_w")
    press(assembly, RUN_WANTED, {"run": "running"})

    reading(assembly, VACATED, "yard_w")

    assert runs(assembly) == [
        "running",
        "held",
        "running",
        "held",
        "running",
        "held",
    ]
    assert locks(assembly)["yard_w"] == "freight_1"


def test_a_clear_reading_under_a_standing_train_still_holds_the_run() -> None:
    """A detector dropping out under a dirty wheel reads the same as a lift,
    and only a removal says which it was (ADR-0048, ADR-0069): a removed
    train's residue elsewhere explains nothing here."""
    assembly = standing()
    remove(assembly, "freight_1")
    reading(assembly, OCCUPIED, "up_e")
    assert runs(assembly) == ["running", "held", "running", "held"]
    press(assembly, RUN_WANTED, {"run": "running"})

    reading(assembly, VACATED, "up_e")

    assert runs(assembly)[-2:] == ["running", "held"]
    assert locks(assembly)["up_e"] == "express_2"
    assert locks(assembly)["yard_w"] == "freight_1"
