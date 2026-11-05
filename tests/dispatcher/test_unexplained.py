"""A sensor reading no granted move accounts for (ADR-0048, #260, #1154).

Occupancy is anonymous, so the dispatcher recovers the train from its own lock
table: what each train occupies, and the move it has outstanding. A reading
the table does not explain — a hand putting a locomotive on a detected block,
a detector asserting on dirt — is a failure where it happens, and **the rest
keeps running**: the reading is named on `state/disputed` for a person and no
train is sent into a block that reads occupied. A clear reading disputes
nothing, since a short train stands between its block's two sensors (#1164). It
does not raise: the frame is well formed, and a handler that raised would take
the app off the bus for an ordinary act of a person's hand (BUS.md, rule 4).

Driven at the bus, on a railroad standing still with no timetable at all —
which is exactly the railroad a hand reaches onto.
"""

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import FullRoute, Incremental
from tc49.lib.bus import Payload
from tc49.lib.inventory import AT, DRAINING, OFF, ON
from tc49.lib.scenario import TrainSpec
from tests.harness import POWER, drains, events, load, power, press, run, settled

OCCUPIED = True
VACATED = False
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
DISPUTED = "tc49/dispatch/state/disputed"
ASPECTS = "tc49/dispatch/state/aspects"
STOP = "stop"

STOOD = {
    "freight_1": TrainSpec("yard_w", "A-to-B"),
    "express_2": TrainSpec("up_e", "B-to-A"),
}
"""Two trains standing where a document put them, and nothing to do: `up_w`
and `dn_w` are free, and `shunter` is on the roster and off the layout — the
locomotive a hand is about to put down (ADR-0039)."""


@pytest.fixture
def standing() -> Assembly:
    """A railroad with the power on and nothing moving on it. No request is
    minted into it, so every reading that arrives is one no grant
    explains."""
    layout, roster, _ = load("crossover-yard/meet")
    return assemble_live(layout, roster, STOOD)


def reading(assembly: Assembly, occupied: bool, block: str) -> None:
    """The reading of one sensor of the block, as a layout binding that reads one
    reports it."""
    press(assembly, *settled(f"{block}.A", occupied))


def disputed(assembly: Assembly) -> Payload:
    """The last value of the topic, which is what the panel points a person
    at (ADR-0032), without the stamp the binding put on it (#240)."""
    return {
        key: value
        for key, value in assembly.bus.last_values[DISPUTED].items()
        if key != AT
    }


def ask(assembly: Assembly, train: str, dest: str) -> None:
    press(assembly, REQUEST_WANTED, {"train": train, "dest": [dest]})


def granted(assembly: Assembly) -> list[tuple[str, str]]:
    """Each move granted so far: the train and the block it was sent into."""
    return [
        (line["train"], line["into"]) for line in events(assembly.trace, "move_granted")
    ]


def test_a_block_no_grant_accounts_for_is_named_and_others_run(
    standing: Assembly,
) -> None:
    """A hand puts a locomotive on a detected block with the power on. No
    drain is asked and a person is told. A train elsewhere is granted, and a
    train whose way lies through that block is not sent into it."""
    reading(standing, OCCUPIED, "up_w")

    assert drains(standing) == []
    assert standing.bus.last_values[POWER]["power"] == ON
    assert disputed(standing) == {"blocks": ["up_w"]}

    ask(standing, "freight_1", "dn_w.A")
    assert granted(standing) == [("freight_1", "dn_w")]

    ask(standing, "express_2", "up_w.B")
    assert ("express_2", "up_w") not in granted(standing)


def test_the_block_opens_when_it_reads_clear(standing: Assembly) -> None:
    """The reading goes as it came, and the train waiting on it goes: a sweep
    runs for it, with no person's hand needed."""
    reading(standing, OCCUPIED, "up_w")
    ask(standing, "express_2", "up_w.B")
    assert granted(standing) == []

    reading(standing, VACATED, "up_w")

    assert disputed(standing) == {"blocks": []}
    assert granted(standing) == [("express_2", "up_w")]


@pytest.mark.parametrize("strategy", [Incremental, FullRoute])
def test_a_train_in_a_block_reading_clear_is_granted(
    strategy: type[Incremental | FullRoute],
) -> None:
    """A short train stands between its block's two sensors, and both read
    clear. It is where the lock table says, so nothing is disputed (#1164)."""
    layout, roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, roster, STOOD, strategy)

    reading(assembly, VACATED, "yard_w")
    ask(assembly, "freight_1", "dn_w.A")

    assert drains(assembly) == []
    assert disputed(assembly) == {"blocks": []}
    assert granted(assembly) == [("freight_1", "dn_w")]


def test_a_move_out_of_a_block_reading_clear_ends_on_its_entry_sensor(
    standing: Assembly,
) -> None:
    """A train placed beyond its exit sensor never reads occupied on it, so the
    entry sensor clearing is the last reading the move hears, and it releases the
    origin with the transit (#1164, #1171)."""
    reading(standing, VACATED, "yard_w")
    ask(standing, "freight_1", "dn_w.A")

    reading(standing, OCCUPIED, "dn_w")

    state = standing.dispatcher.state
    assert "freight_1" not in state.crossing
    assert state.locks["yard_w"] == "freight_1"

    reading(standing, VACATED, "dn_w")

    assert state.locks.get("yard_w") is None


def test_a_short_train_passing_its_exit_sensor_ends_the_move_when_it_clears(
    standing: Assembly,
) -> None:
    """On the way out the short train crosses the sensor at its block's far end:
    occupied, which its move explains, and still occupied as the nose reaches
    the next block. The tail is still on the sensor, so the origin stays held
    until it clears (ADR-0077, #1164)."""
    press(standing, *settled("yard_w.B", False))
    ask(standing, "freight_1", "dn_w.A")

    press(standing, *settled("yard_w.B"))
    assert disputed(standing) == {"blocks": []}
    reading(standing, OCCUPIED, "dn_w")

    state = standing.dispatcher.state
    assert state.locks["yard_w"] == "freight_1"

    press(standing, *settled("yard_w.B", False))

    assert state.locks.get("yard_w") is None


def test_a_placement_leaves_a_clear_reading_where_it_is(standing: Assembly) -> None:
    """A clear reading disputes nothing, so the person's word has nothing to
    forget, and the detector has stated its level: the train lifted and put
    back runs (#1164)."""
    reading(standing, VACATED, "yard_w")

    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": None})
    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": "yard_w"})

    assert standing.dispatcher.state.readings["yard_w.A"] is False
    assert disputed(standing) == {"blocks": []}
    ask(standing, "freight_1", "dn_w.A")
    assert granted(standing) == [("freight_1", "dn_w")]


def test_a_placement_on_the_stray_block_resolves_it(standing: Assembly) -> None:
    """The person walks to the block, sees the locomotive somebody put there,
    and says so. The dispatcher places nothing itself: occupancy is anonymous,
    so it has no train to place (#153)."""
    reading(standing, OCCUPIED, "up_w")

    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})

    assert disputed(standing) == {"blocks": []}


@pytest.mark.parametrize("strategy", [Incremental, FullRoute])
def test_an_active_train_whose_block_reads_clear_goes_on(
    strategy: type[Incremental | FullRoute],
) -> None:
    """Partway along a route, stopped in a block by a drain, its detector drops
    out. Power on again grants its next move (#1164)."""
    layout, roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, roster, STOOD, strategy)
    ask(assembly, "freight_1", "yard_e.A")
    press(assembly, *power(DRAINING))
    reading(assembly, OCCUPIED, "dn_w")
    state = assembly.dispatcher.state
    assert state.block_of["freight_1"] == "dn_w"
    assert "freight_1" not in state.crossing
    assert "freight_1" in state.active

    reading(assembly, VACATED, "dn_w")
    press(assembly, *power(ON))

    assert granted(assembly) == [("freight_1", "dn_w"), ("freight_1", "dn_e")]
    assert disputed(assembly) == {"blocks": []}


@pytest.mark.parametrize("strategy", [Incremental, FullRoute])
def test_a_block_held_ahead_reading_occupied_is_disputed(
    strategy: type[Incremental | FullRoute],
) -> None:
    """A hand puts a locomotive on a block `freight_1` holds ahead. A lock
    explains nothing, so the block is named, its holder is told nobody's train
    stands there, and its signal shows `stop`. It goes when the block reads
    clear (#1164)."""
    layout, roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, roster, STOOD, strategy)
    ask(assembly, "freight_1", "yard_e.A")
    assert assembly.dispatcher.state.locks["dn_e"] == "freight_1"

    reading(assembly, OCCUPIED, "dn_e")

    assert disputed(assembly) == {"blocks": ["dn_e"]}

    reading(assembly, OCCUPIED, "dn_w")
    reading(assembly, VACATED, "yard_w")

    assert events(assembly.trace, "grant_refused")[-1]["obstacles"] == [
        {"resource": "dn_e", "holder": ""}
    ]
    assert assembly.bus.last_values[ASPECTS]["aspects"]["dn_w.B"] == STOP
    assert granted(assembly) == [("freight_1", "dn_w")]
    assert assembly.dispatcher.state.locks["dn_e"] == "freight_1"

    reading(assembly, VACATED, "dn_e")

    assert disputed(assembly) == {"blocks": []}
    assert granted(assembly) == [("freight_1", "dn_w"), ("freight_1", "dn_e")]


def test_the_origin_and_the_arrival_of_a_move_are_explained(
    standing: Assembly,
) -> None:
    """Both blocks of the move outstanding read occupied, and neither is
    disputed, with the train recorded in either (#1164)."""
    ask(standing, "freight_1", "dn_w.A")
    reading(standing, VACATED, "yard_w")
    reading(standing, OCCUPIED, "yard_w")
    assert disputed(standing) == {"blocks": []}

    reading(standing, OCCUPIED, "dn_w")

    assert standing.dispatcher.state.block_of["freight_1"] == "dn_w"
    assert disputed(standing) == {"blocks": []}


def test_a_train_recorded_in_a_block_explains_it(standing: Assembly) -> None:
    reading(standing, OCCUPIED, "yard_w")

    assert disputed(standing) == {"blocks": []}


def test_a_block_a_train_explains_keeps_its_holder_in_a_refusal(
    standing: Assembly,
) -> None:
    """The reading is `express_2`'s, in the block it stands in, so that is who
    `freight_1` waits for (#1164)."""
    reading(standing, OCCUPIED, "up_e")

    obstacle = standing.dispatcher.state.obstacle("up_e", "freight_1")

    assert obstacle == ("held", "up_e", "express_2")


def test_residue_of_a_removal_is_explained(standing: Assembly) -> None:
    """The block a removed train still holds reads occupied until the hand has
    lifted it (ADR-0069, #1164)."""
    reading(standing, OCCUPIED, "yard_w")

    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": None})

    assert standing.dispatcher.state.residue == {"yard_w"}
    assert disputed(standing) == {"blocks": []}


def test_a_crossing_train_whose_origin_reads_clear_is_not_disputed(
    standing: Assembly,
) -> None:
    """The ordinary railroad: a train that has left its block and not yet read
    occupied in the next is what the picture already says, with the power on."""
    ask(standing, "freight_1", "dn_w.A")

    reading(standing, VACATED, "yard_w")

    assert "freight_1" in standing.dispatcher.state.crossing
    assert disputed(standing) == {"blocks": []}


def test_a_detector_restating_its_level_changes_nothing(standing: Assembly) -> None:
    """A reading is a level, so a repeat is an at-least-once redelivery and a
    no-op (ADR-0047)."""
    reading(standing, OCCUPIED, "up_w")
    before = len(events(standing.trace, "disputed"))

    reading(standing, OCCUPIED, "up_w")

    assert len(events(standing.trace, "disputed")) == before
    assert drains(standing) == []


@pytest.mark.parametrize("value", [DRAINING, OFF])
def test_a_reading_with_the_power_not_on_is_named_too(
    standing: Assembly, value: str
) -> None:
    press(standing, *power(value))

    reading(standing, OCCUPIED, "up_w")

    assert drains(standing) == []
    assert disputed(standing) == {"blocks": ["up_w"]}


def test_the_readings_a_granted_move_explains_ask_for_nothing() -> None:
    """The ordinary railroad, untouched: every reading a scenario produces
    reports on a move the dispatcher granted, so nothing is disputed and the
    requests complete."""
    trace = run(*load("crossover-yard/meet"))

    assert [line["power"] for line in events(trace, "power_wanted")] == [ON]
    assert len(events(trace, "request_completed")) == 3
    assert all(not line["blocks"] for line in events(trace, "disputed"))
