"""A detector reading no granted move accounts for (ADR-0048, #260, #1154).

Occupancy is anonymous, so the dispatcher recovers the train from its own lock
table: the block's holder, and the move that holder has outstanding. A reading
the table does not explain — a hand putting a locomotive on a detected block,
a train lifted off, a detector asserting on dirt — is a failure where it
happens, and **the rest keeps running**: the reading is named on
`state/disputed` for a person, no train is sent into a block that reads
occupied, and a train whose block reads clear takes no grant. It does not
raise: the frame is well formed, and a handler that raised would take the app
off the bus for an ordinary act of a person's hand (BUS.md, rule 4).

Driven at the bus, on a railroad standing still with no timetable at all —
which is exactly the railroad a hand reaches onto.
"""

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.dispatcher import FullRoute, Incremental
from tc49.lib.bus import Payload
from tc49.lib.inventory import AT, DRAINING, OFF, ON
from tc49.lib.scenario import TrainSpec
from tests.harness import POWER, drains, events, load, power, press, run

OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
REQUEST_WANTED = "tc49/schedule/request_wanted"
DISPUTED = "tc49/dispatch/state/disputed"

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


def reading(assembly: Assembly, topic: str, block: str) -> None:
    """One detector reading, as a layout binding that reads one reports it."""
    press(assembly, topic, {"block": block})


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
    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}

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

    assert disputed(standing) == {"trains": [], "blocks": []}
    assert granted(standing) == [("express_2", "up_w")]


def test_a_block_reading_clear_under_a_standing_train_stops_only_that_train(
    standing: Assembly,
) -> None:
    """The other direction: a train lifted off, or a detector dropping out
    under it. Where it went is not something a reading can say, so it takes no
    grant and is named, and another train is granted."""
    reading(standing, VACATED, "yard_w")

    assert drains(standing) == []
    assert disputed(standing) == {"trains": ["freight_1"], "blocks": []}

    ask(standing, "freight_1", "dn_w.A")
    ask(standing, "express_2", "up_w.B")

    assert granted(standing) == [("express_2", "up_w")]


def test_a_placement_clears_the_entry_and_the_train_runs(standing: Assembly) -> None:
    """A person has walked to it and says where it stands. The request it was
    waiting on goes with the placement (ADR-0049), so the next one is granted."""
    reading(standing, VACATED, "yard_w")

    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": "dn_w"})

    assert disputed(standing) == {"trains": [], "blocks": []}
    ask(standing, "freight_1", "dn_e.A")
    assert granted(standing) == [("freight_1", "dn_e")]


def test_placing_a_train_into_a_block_last_read_clear_does_not_dispute_it(
    standing: Assembly,
) -> None:
    """The clear reading is from before the person's word. A detector that
    still reads clear publishes nothing, so nothing else would end the entry,
    and this is the way out for one that has failed under a train: lift it
    and put it back."""
    reading(standing, VACATED, "yard_w")

    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": None})
    press(standing, PLACEMENT_WANTED, {"train": "freight_1", "block": "yard_w"})

    assert disputed(standing) == {"trains": [], "blocks": []}
    ask(standing, "freight_1", "dn_w.A")
    assert granted(standing) == [("freight_1", "dn_w")]


def test_a_placement_on_the_stray_block_resolves_it(standing: Assembly) -> None:
    """The person walks to the block, sees the locomotive somebody put there,
    and says so. The dispatcher places nothing itself: occupancy is anonymous,
    so it has no train to place (#153)."""
    reading(standing, OCCUPIED, "up_w")

    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})

    assert disputed(standing) == {"trains": [], "blocks": []}


def test_a_train_reading_occupied_again_takes_its_grant(standing: Assembly) -> None:
    """A dirty wheel: the detector drops out and comes back. Nobody had to do
    anything, and the waiting request is granted when it does."""
    reading(standing, VACATED, "yard_w")
    ask(standing, "freight_1", "dn_w.A")
    assert granted(standing) == []

    reading(standing, OCCUPIED, "yard_w")

    assert disputed(standing) == {"trains": [], "blocks": []}
    assert granted(standing) == [("freight_1", "dn_w")]


@pytest.mark.parametrize("strategy", [Incremental, FullRoute])
def test_an_active_train_waits_at_its_signal(
    strategy: type[Incremental | FullRoute],
) -> None:
    """Partway along a route, stopped in a block by a drain, its detector drops
    out. Power on again grants it nothing until the block reads occupied, and
    its route stays its own."""
    layout, roster, _ = load("crossover-yard/meet")
    assembly = assemble_live(layout, roster, STOOD, strategy)
    ask(assembly, "freight_1", "yard_e.A")
    reading(assembly, OCCUPIED, "dn_w")
    press(assembly, *power(DRAINING))
    reading(assembly, VACATED, "yard_w")
    state = assembly.dispatcher.state
    assert state.block_of["freight_1"] == "dn_w"
    assert "freight_1" not in state.crossing
    assert "freight_1" in state.active

    reading(assembly, VACATED, "dn_w")
    press(assembly, *power(ON))

    assert granted(assembly) == [("freight_1", "dn_w")]
    assert disputed(assembly) == {"trains": ["freight_1"], "blocks": []}
    assert "freight_1" in state.active

    reading(assembly, OCCUPIED, "dn_w")

    assert granted(assembly) == [("freight_1", "dn_w"), ("freight_1", "dn_e")]


def test_a_crossing_train_whose_origin_reads_clear_is_not_disputed(
    standing: Assembly,
) -> None:
    """The ordinary railroad: a train that has left its block and not yet read
    occupied in the next is what the picture already says, with the power on."""
    ask(standing, "freight_1", "dn_w.A")

    reading(standing, VACATED, "yard_w")

    assert "freight_1" in standing.dispatcher.state.crossing
    assert disputed(standing) == {"trains": [], "blocks": []}


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
    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}


def test_the_readings_a_granted_move_explains_ask_for_nothing() -> None:
    """The ordinary railroad, untouched: every reading a scenario produces
    reports on a move the dispatcher granted, so nothing is disputed and the
    requests complete."""
    trace = run(*load("crossover-yard/meet"))

    assert [line["power"] for line in events(trace, "power_wanted")] == [ON]
    assert len(events(trace, "request_completed")) == 3
    assert all(
        not line["trains"] and not line["blocks"] for line in events(trace, "disputed")
    )
