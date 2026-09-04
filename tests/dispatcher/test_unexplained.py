"""A detector reading no granted move accounts for (ADR-0048, #260).

Occupancy is anonymous, so the dispatcher recovers the train from its own lock
table: the block's holder, and the move that holder has outstanding. A reading
the table does not explain — a hand putting a locomotive on a detected block,
a train pushed while the supply was off, a detector asserting on dirt — says
the table has stopped describing the steel.

It **holds the run**, by the path track power takes, and the dispute check
names what it contradicts for a person to walk. It does not raise: the frame
is well formed, and a handler that raised would take the app off the bus for
an ordinary act of a person's hand (SYSTEM.md, rule 4).

Driven at the bus, on a railroad standing still with no timetable at all —
which is exactly the railroad a hand reaches onto.
"""

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bus import Payload
from tc49.lib.inventory import AT
from tc49.lib.scenario import TrainSpec
from tests.harness import RUN_WANTED, events, load, press, run, runs

OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
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
    """A running railroad with nothing moving on it. A run whose document
    stood its trains comes up running (ADR-0037), and no request is minted
    into it, so every reading that arrives is one no grant explains."""
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


def test_a_block_no_grant_accounts_for_holds_the_run(standing: Assembly) -> None:
    """The case the decision exists for: a hand puts a locomotive on a
    detected block while the railroad is running. Nothing more commits, and
    no signalled end goes on showing `clear` over a railroad the dispatcher
    can no longer account for."""
    reading(standing, OCCUPIED, "up_w")

    assert runs(standing) == ["running", "held"]
    shown = events(standing.trace, "aspects")[-1]["aspects"]
    assert set(shown.values()) == {"stop"}


def test_the_hold_names_the_block_for_a_person_to_walk(standing: Assembly) -> None:
    """The hold alone would say only that something is wrong. The dispute
    check is published while held and is this comparison exactly, so the
    reading that stopped the railroad is the entry the person is sent to
    (#153)."""
    reading(standing, OCCUPIED, "up_w")

    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}


def test_a_block_reading_clear_with_a_train_in_it_holds_the_run(
    standing: Assembly,
) -> None:
    """The other direction, and the same sentence: a block the dispatcher
    believes a train stands in reports empty. Where that train went is not
    something a reading can say, which is why the answer is to stop and name
    it rather than to guess."""
    reading(standing, VACATED, "yard_w")

    assert runs(standing) == ["running", "held"]
    assert disputed(standing) == {"trains": ["freight_1"], "blocks": []}


def test_the_railroad_runs_again_once_a_person_has_said_what_it_is(
    standing: Assembly,
) -> None:
    """The whole recovery, which is what makes the hold an answer rather than
    a stop: the person walks to the block, sees the locomotive somebody put
    there, says so, and presses GO. The dispatcher places nothing itself —
    occupancy is anonymous, so it has no train to place (#153)."""
    reading(standing, OCCUPIED, "up_w")

    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})
    assert disputed(standing) == {"trains": [], "blocks": []}

    press(standing, RUN_WANTED, {"run": "running"})
    assert runs(standing) == ["running", "held", "running"]


def test_a_detector_restating_its_level_holds_nothing(standing: Assembly) -> None:
    """A reading is a level, so a repeat is an at-least-once redelivery and a
    no-op (ADR-0047). A binding that restates what it already said must not
    stop a railroad a person has just looked at and released."""
    reading(standing, OCCUPIED, "up_w")
    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})
    press(standing, RUN_WANTED, {"run": "running"})

    reading(standing, OCCUPIED, "up_w")

    assert runs(standing) == ["running", "held", "running"]


def test_a_held_run_is_not_held_again(standing: Assembly) -> None:
    """Nothing changes for a run already held: the reading was the dispute
    check's business before this decision and still is."""
    press(standing, RUN_WANTED, {"run": "held"})

    reading(standing, OCCUPIED, "up_w")

    assert runs(standing) == ["running", "held"]
    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}


def test_the_readings_a_granted_move_explains_hold_nothing() -> None:
    """The ordinary railroad, untouched: every reading a scenario produces
    reports on a move the dispatcher granted, so the run never holds and the
    requests complete."""
    trace = run(*load("crossover-yard/meet"))

    # Every row the run published said `running`: what moves the topic here
    # is `moving` alone, as the trains take their routes and finish them.
    assert {line["run"] for line in events(trace, "run")} == {"running"}
    assert len(events(trace, "request_completed")) == 3
