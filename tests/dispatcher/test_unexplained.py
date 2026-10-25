"""A detector reading no granted move accounts for (ADR-0048, #260).

Occupancy is anonymous, so the dispatcher recovers the train from its own lock
table: the block's holder, and the move that holder has outstanding. A reading
the table does not explain — a hand putting a locomotive on a detected block,
a train pushed while the supply was off, a detector asserting on dirt — says
the table has stopped describing the steel.

It **drains the railroad**: the dispatcher asks `layout` for `draining`, as a
person's press would (ADR-0078), and once the supply is off the dispute check
names what the reading contradicts for a person to walk. It does not raise:
the frame is well formed, and a handler that raised would take the app off
the bus for an ordinary act of a person's hand (BUS.md, rule 4).

Driven at the bus, on a railroad standing still with no timetable at all —
which is exactly the railroad a hand reaches onto.
"""

import pytest

from tc49.bench.runner import DEFAULT_K, Assembly, assemble_live, placement
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AT, DRAINING, OFF, ON
from tc49.lib.scenario import TrainSpec
from tests.harness import POWER, drains, events, load, power, press, run

OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
DISPUTED = "tc49/dispatch/state/disputed"
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
POWER_WANTED = "tc49/layout/power_wanted"

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


def drained(assembly: Assembly) -> None:
    """`layout` answering the drain, and switching the supply off once
    nothing is moving (ADR-0078). Stated here because the binding's half of
    it is the layout's to test."""
    press(assembly, *power(DRAINING))
    press(assembly, *power(OFF))


def disputed(assembly: Assembly) -> Payload:
    """The last value of the topic, which is what the panel points a person
    at (ADR-0032), without the stamp the binding put on it (#240)."""
    return {
        key: value
        for key, value in assembly.bus.last_values[DISPUTED].items()
        if key != AT
    }


def test_a_block_no_grant_accounts_for_drains_the_railroad(
    standing: Assembly,
) -> None:
    """The case the decision exists for: a hand puts a locomotive on a
    detected block while the power is on. The dispatcher asks for a drain,
    and once `layout` answers, nothing more commits and no signalled end goes
    on showing `clear` over a railroad the dispatcher can no longer account
    for."""
    reading(standing, OCCUPIED, "up_w")
    assert drains(standing) == [DRAINING]

    press(standing, *power(DRAINING))
    shown = events(standing.trace, "aspects")[-1]["aspects"]
    assert set(shown.values()) == {"stop"}


def test_the_drain_names_the_block_for_a_person_to_walk(standing: Assembly) -> None:
    """The drain alone would say only that something is wrong. The dispute
    check is published once the power is off and is this comparison exactly,
    so the reading that stopped the railroad is the entry the person is sent
    to (#153). Nothing is moving here, so the binding answers the drain with
    the supply off at once (ADR-0078)."""
    reading(standing, OCCUPIED, "up_w")

    assert standing.bus.last_values[POWER]["power"] == OFF
    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}


def test_a_block_reading_clear_with_a_train_in_it_drains_the_railroad(
    standing: Assembly,
) -> None:
    """The other direction, and the same sentence: a block the dispatcher
    believes a train stands in reports empty. Where that train went is not
    something a reading can say, which is why the answer is to stop and name
    it rather than to guess."""
    reading(standing, VACATED, "yard_w")
    assert drains(standing) == [DRAINING]

    drained(standing)
    assert disputed(standing) == {"trains": ["freight_1"], "blocks": []}


def test_the_railroad_runs_again_once_a_person_has_said_what_it_is(
    standing: Assembly,
) -> None:
    """The whole recovery, which is what makes the drain an answer rather
    than a stop: the person walks to the block, sees the locomotive somebody
    put there, says so, and turns the power on. The dispatcher places nothing
    itself — occupancy is anonymous, so it has no train to place (#153)."""
    reading(standing, OCCUPIED, "up_w")
    drained(standing)

    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})
    assert disputed(standing) == {"trains": [], "blocks": []}

    press(standing, *power(ON))
    press(
        standing,
        "tc49/schedule/request_wanted",
        {"train": "freight_1", "dest": ["yard_e.A"]},
    )
    assert events(standing.trace, "route_chosen")
    assert drains(standing) == [DRAINING]


def test_a_detector_restating_its_level_drains_nothing(standing: Assembly) -> None:
    """A reading is a level, so a repeat is an at-least-once redelivery and a
    no-op (ADR-0047). A binding that restates what it already said must not
    stop a railroad a person has just looked at and turned on."""
    reading(standing, OCCUPIED, "up_w")
    drained(standing)
    press(standing, PLACEMENT_WANTED, {"train": "shunter", "block": "up_w"})
    press(standing, *power(ON))

    reading(standing, OCCUPIED, "up_w")

    assert drains(standing) == [DRAINING]


def test_a_railroad_already_off_is_not_drained(standing: Assembly) -> None:
    """Nothing changes for a railroad already off: `draining` is answered
    from `on` alone, and the reading is the dispute check's business."""
    press(standing, *power(OFF))

    reading(standing, OCCUPIED, "up_w")

    assert drains(standing) == []
    assert disputed(standing) == {"trains": [], "blocks": ["up_w"]}


def test_the_readings_a_granted_move_explains_drain_nothing() -> None:
    """The ordinary railroad, untouched: every reading a scenario produces
    reports on a move the dispatcher granted, so nothing asks for a drain and
    the requests complete."""
    trace = run(*load("crossover-yard/meet"))

    assert [line["power"] for line in events(trace, "power_wanted")] == [ON]
    assert len(events(trace, "request_completed")) == 3


def test_nothing_is_granted_between_asking_for_a_drain_and_the_answer(
    standing: Assembly,
) -> None:
    """The dispatcher reads `on` until `layout` answers the drain it asked
    for, and a request arriving in that window is not granted: the table it
    would be granted from is the one the reading just said is wrong (#1087).
    Both are put on the bus before either is delivered, so the request lands
    before the answer, as it can on a broker."""
    standing.bus.publish(OCCUPIED, {"block": "up_w"})
    standing.bus.publish(
        "tc49/schedule/request_wanted",
        {"train": "freight_1", "dest": ["yard_e.A"]},
    )
    standing.bus.drain()

    assert drains(standing) == [DRAINING]
    assert not events(standing.trace, "move_granted")


def test_a_person_pressing_on_ends_a_drain_nobody_answered() -> None:
    """A dispatcher with no `layout` on its bus: the drain it asks for is
    never answered and power goes on reading `on`. Nothing is granted until a
    person presses `on`, which acknowledges the fault (ADR-0078, decision 7,
    #1087)."""
    bus = InProcessBus(Clock())
    layout, roster, scenario = load("crossover-yard/meet")
    Dispatcher(
        bus, layout, roster, placement(scenario.trains), FullRoute(layout, DEFAULT_K)
    )
    granted: list[Payload] = []
    bus.subscribe(
        "tc49/dispatch/move_granted", lambda _, payload: granted.append(payload)
    )

    for topic, payload in (
        (POWER, {"power": ON}),
        (OCCUPIED, {"block": "up_w"}),
        (
            REQUEST_SUBMITTED,
            {
                "id": "r-1",
                "train": "freight_1",
                "depart": "yard_w.B",
                "dest": ["dn_w.A"],
            },
        ),
    ):
        bus.publish(topic, payload)
        bus.drain()
    assert granted == []

    bus.publish(POWER_WANTED, {"power": ON})
    bus.drain()
    assert [payload["id"] for payload in granted] == ["r-1"]
