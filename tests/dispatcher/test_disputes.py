"""What the detectors say about the placement a session came back up on (#153).

On power-up the detectors assert straight away, anonymously but at once, and
that is exactly the moment the restored placement is least trustworthy: the
steel has stood unwatched since the last session, long enough for a stalled
train to have been lifted out of a tunnel by hand (CONTEXT.md, recovery). So
while the run is held the dispatcher compares the two and names the
contradictions — a train standing in a block that reads clear, and a block
that reads occupied with nothing claiming it.

It resolves nothing: occupancy is anonymous, so the check only points and a
person ends every entry with a `placement_wanted`. And **silence is not a
clear reading** — a block the layout has said nothing about takes no part,
which is what keeps a binding that reports nothing from disputing the whole
railroad.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from tc49.bench.runner import DEFAULT_K
from tc49.dispatcher import Dispatcher, FullRoute
from tc49.lib.bus import Bus, Payload
from tc49.lib.roster import Train
from tc49.lib.scenario import TrainSpec
from tests.harness import RUN_WANTED, load

ALLOCATION = "tc49/dispatch/state/allocation"
DISPUTED = "tc49/dispatch/state/disputed"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACEMENT_WANTED = "tc49/ui/placement_wanted"

MOVED: dict[str, Any] = {
    "trains": {"express_2": "up_w", "freight_1": "dn_e"},
    "crossing": {},
    "locks": {},
    "requests": [],
}
"""Where the last session believed the two trains were standing."""


def restored(
    tmp_path: Path,
    picture: dict[str, Any] | None = None,
    added: dict[str, str] | None = None,
) -> tuple[Bus, Dispatcher]:
    """A dispatcher on a bus whose file already holds that picture, which is
    the session that comes up held (#154) and so the one the check runs in.

    `added` is stock the scenario has gained since the picture was taken,
    train to starting block: the trains a collision is made of (#164).
    """
    path = tmp_path / "session.json"
    path.write_text(json.dumps({} if picture is None else {ALLOCATION: picture}))
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
    dispatcher = Dispatcher(bus, layout, roster, scenario, FullRoute(layout, DEFAULT_K))
    bus.drain()
    return bus, dispatcher


def reports(
    bus: Bus, occupied: tuple[str, ...] = (), clear: tuple[str, ...] = ()
) -> None:
    """The detectors asserting, as a layout binding that reads them reports:
    a block it says nothing about is in neither list."""
    for block in occupied:
        bus.publish(OCCUPIED, {"block": block})
    for block in clear:
        bus.publish(VACATED, {"block": block})
    bus.drain()


def disputed(bus: Bus) -> Payload:
    """The last value of the topic, which is what a client joining later is
    served — the panel that points a person at the railroad (ADR-0032)."""
    return bus.last_values[DISPUTED]


def press(bus: Bus, topic: str, payload: Payload) -> None:
    bus.publish(topic, payload)
    bus.drain()


def test_a_train_moved_by_hand_disputes_the_two_blocks(tmp_path: Path) -> None:
    """The case the check exists for: the picture says `freight_1` is in
    `dn_e` and it is standing in `dn_w`. Exactly two entries — the block it
    left, now reading clear, and the block it sits in, now reading occupied
    with nothing claiming it."""
    bus, _ = restored(tmp_path, MOVED)

    reports(bus, occupied=("dn_w",), clear=("dn_e",))

    assert disputed(bus) == {"trains": ["freight_1"], "blocks": ["dn_w"]}


def test_a_picture_the_detectors_agree_with_disputes_nothing(tmp_path: Path) -> None:
    """The ordinary restart: nothing moved while the apps were down, and the
    person has a railroad to look at rather than a list."""
    bus, _ = restored(tmp_path, MOVED)

    reports(bus, occupied=("up_w", "dn_e"), clear=("up_e", "dn_w", "yard_w", "yard_e"))

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_a_layout_reporting_no_occupancy_disputes_nothing(tmp_path: Path) -> None:
    """**Silence is not a clear reading.** The milestone-1 simulator publishes
    sensors for moves alone and reports nothing at startup (SYSTEM.md), and
    reading every unreported block as clear would make the whole railroad a
    dispute on every restore."""
    bus, _ = restored(tmp_path, MOVED)

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_a_block_the_layout_has_not_reported_takes_no_part(tmp_path: Path) -> None:
    """The same rule, one detector at a time: a layout that watches part of
    its railroad disputes only what it watches. `express_2` stands in `up_w`
    and nothing has said whether `up_w` is occupied."""
    bus, _ = restored(tmp_path, MOVED)

    reports(bus, occupied=("dn_e",))

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_placing_the_train_resolves_both_entries(tmp_path: Path) -> None:
    """The set empties as the railroad is walked: a person who has looked
    says where the train stands, and both halves of its dispute go — the
    block it now stands in is the block that reads occupied."""
    bus, _ = restored(tmp_path, MOVED)
    reports(bus, occupied=("dn_w",), clear=("dn_e",))

    press(bus, PLACEMENT_WANTED, {"train": "freight_1", "block": "dn_w"})

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_the_opening_statement_carries_the_set(tmp_path: Path) -> None:
    """Stated from the constructor as `state/run` and `state/allocation` are:
    a joining client is served the set rather than left to read one out of an
    absence, and a value the last session left is cleared rather than
    standing over this one's railroad (ADR-0032)."""
    stale = {"trains": ["freight_1"], "blocks": ["dn_w"]}
    path = tmp_path / "session.json"
    path.write_text(json.dumps({ALLOCATION: MOVED, DISPUTED: stale}))
    layout, roster, scenario = load("crossover-yard/meet")
    bus = Bus(path)
    Dispatcher(bus, layout, roster, scenario, FullRoute(layout, DEFAULT_K))
    bus.drain()

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_releasing_the_hold_is_allowed_and_empties_the_set(tmp_path: Path) -> None:
    """The person decides, not the check: a dispute never blocks the release.
    What it does end is the comparison — a running dispatcher's placement
    follows the sensors move by move, and the picture the check was made
    against is one the operator has accepted."""
    bus, dispatcher = restored(tmp_path, MOVED)
    reports(bus, occupied=("dn_w",), clear=("dn_e",))

    press(bus, RUN_WANTED, {"run": "running"})

    assert dispatcher.state.run == "running"
    assert disputed(bus) == {"trains": [], "blocks": []}


def test_holding_the_run_again_asks_the_detectors_again(tmp_path: Path) -> None:
    """The check belongs to a held run rather than to a restart: a person who
    holds the railroad mid-evening is looking at it for the same reason."""
    bus, _ = restored(tmp_path, MOVED)
    reports(bus, occupied=("dn_w",), clear=("dn_e",))
    press(bus, RUN_WANTED, {"run": "running"})

    press(bus, RUN_WANTED, {"run": "held"})

    assert disputed(bus) == {"trains": ["freight_1"], "blocks": ["dn_w"]}


def test_a_crossing_train_leaves_no_dispute_behind_it(tmp_path: Path) -> None:
    """A train the picture says is between two blocks stands in none: the
    block `trains` still names is one it has left, so a clear reading there
    agrees with the picture rather than contradicting it. That train is
    already the one a person is sent to — the panel draws it on the
    connection (#154) — and saying it twice would say it wrongly."""
    crossing = {**MOVED, "crossing": {"freight_1": "crossover.dn_straight"}}
    bus, _ = restored(tmp_path, crossing)

    reports(bus, clear=("dn_e",))

    assert disputed(bus) == {"trains": [], "blocks": []}


def test_a_train_adoption_placed_nowhere_is_disputed_as_a_block(
    tmp_path: Path,
) -> None:
    """The other side of the per-train adoption of #164.

    `freight_1` had both its answers taken, so it is placed nowhere and the
    check has no block of its own to read against: a train off the layout
    stands in nothing and contradicts nothing. The steel is still somewhere,
    though, and wherever it reads occupied nothing claims it — so it comes
    out as the stray *block* it is, which is exactly where a person is sent.
    """
    parked = {**MOVED, "trains": {"express_2": "yard_w", "freight_1": "dn_e"}}
    bus, dispatcher = restored(tmp_path, parked, added={"local_3": "dn_e"})
    assert "freight_1" not in dispatcher.state.block_of

    reports(bus, occupied=("dn_e", "dn_w"), clear=("up_e", "up_w"))

    assert disputed(bus) == {"trains": [], "blocks": ["dn_w"]}
