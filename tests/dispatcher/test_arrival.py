"""A move ends on both its readings, and no train is sent into a block that
reads occupied (#791, ADR-0077).

Each test drives a dispatcher on a bus of its own over `crossover-yard/meet`,
answering every `move_granted` with `block_occupied` of the block it moves
into and then `block_vacated` of the one it leaves, unless the case says
otherwise — and the lock table breaks no rule after any delivery (ADR-0076).
The four paths here are ones the physical railroad produces: a detector
stuck occupied with the power turned on again over it, a detector dropping
out under a standing train with the power turned on again over it, a train's own residue on its way back,
and a vacate behind before the occupy ahead, which a train shorter than the
gap between two blocks' detectors gives in normal running.
"""

from typing import Any

import pytest

from tc49.dispatcher import FullRoute, Incremental
from tc49.dispatcher.dispatch import broken
from tc49.lib.bus import Payload
from tc49.lib.inventory import DRAINING, OFF, ON
from tests.dispatcher.test_lock_rules import a_bus_dispatcher, deliver, drains
from tests.harness import POWER

REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"

STRATEGIES = [Incremental, FullRoute]


class Railroad:
    """The dispatcher, and a railroad that answers what it grants."""

    def __init__(self, strategy: type[Incremental | FullRoute] = Incremental) -> None:
        self.bus, self.dispatcher, self.said = a_bus_dispatcher(strategy)
        self.answered = 0

    def deliver(self, topic: str, payload: Payload, answer: bool = True) -> None:
        """One frame, the lock table checked after it, and — unless told
        otherwise — every move it granted run to its sensors."""
        deliver(self.bus, topic, payload)
        assert broken(self.dispatcher.state) == []
        if answer:
            self.answer()

    def answer(self) -> None:
        while len(self.granted()) > self.answered:
            train = self.granted()[self.answered]["train"]
            self.answered += 1
            move = self.dispatcher.state.active[train].outstanding
            assert move is not None
            self.deliver(OCCUPIED, {"block": move.into}, answer=False)
            self.deliver(VACATED, {"block": move.from_block}, answer=False)

    def power(self, value: str, answer: bool = True) -> None:
        """The layout stating the power, as a binding answering a press
        would."""
        self.deliver(POWER, {"power": value}, answer)

    def drained(self) -> None:
        """The drain the dispatcher asked for, answered and run to `off`."""
        assert drains(self.said)[-1] == DRAINING
        self.power(DRAINING)
        self.power(OFF)

    def request(self, rid: str, depart: str, dest: str, answer: bool = True) -> None:
        self.deliver(
            REQUEST_SUBMITTED,
            {"id": rid, "train": "freight_1", "depart": depart, "dest": [dest]},
            answer,
        )

    def leaf(self, name: str) -> list[dict[str, Any]]:
        return [dict(p) for t, p in self.said if t.endswith(f"/{name}")]

    def granted(self) -> list[dict[str, Any]]:
        return self.leaf("move_granted")


def stuck_yard_e(strategy: type[Incremental | FullRoute]) -> Railroad:
    """`yard_e` reads occupied, the railroad drains for it, and a person
    turns the power on again over the dispute."""
    railroad = Railroad(strategy)
    railroad.deliver(OCCUPIED, {"block": "yard_e"})
    railroad.drained()
    railroad.power(ON)
    return railroad


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_block_that_reads_occupied_is_not_entered(
    strategy: type[Incremental | FullRoute],
) -> None:
    railroad = stuck_yard_e(strategy)
    railroad.request("r-1", "yard_w.B", "yard_e.A")

    assert "yard_e" not in [p["into"] for p in railroad.granted()]
    refused = [p for p in railroad.leaf("grant_refused") if p["id"] == "r-1"]
    assert {"resource": "yard_e", "holder": ""} in refused[-1]["obstacles"]
    assert drains(railroad.said) == [DRAINING]  # the reading's, and no other

    railroad.deliver(VACATED, {"block": "yard_e"})

    assert {"id": "r-1"} in railroad.leaf("request_completed")
    state = railroad.dispatcher.state
    assert state.block_of["freight_1"] == "yard_e"
    assert state.locks["yard_e"] == "freight_1"


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_cancelled_request_does_not_enter_it_either(
    strategy: type[Incremental | FullRoute],
) -> None:
    railroad = stuck_yard_e(strategy)
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    railroad.deliver(CANCEL_WANTED, {"id": "r-1"})

    assert "yard_e" not in [p["into"] for p in railroad.granted()]
    assert railroad.leaf("request_cancelled")


def test_a_train_does_not_enter_its_own_residue() -> None:
    """`freight_1` taken off in `dn_w` while it reads occupied, put down in
    `yard_e`, and sent back west: `dn_w` waits for its clear reading."""
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.deliver(PLACEMENT_WANTED, {"train": "freight_1", "block": None})
    railroad.power(OFF)
    railroad.deliver(PLACEMENT_WANTED, {"train": "freight_1", "block": "yard_e"})
    railroad.power(ON)
    state = railroad.dispatcher.state
    assert state.block_of["freight_1"] == "yard_e"

    railroad.request("r-2", "yard_e.A", "yard_w.B")

    assert "dn_w" not in [p["into"] for p in railroad.granted()[1:]]
    assert state.locks["dn_w"] == "freight_1"
    assert "dn_w" in state.residue

    railroad.deliver(OCCUPIED, {"block": "dn_w"})
    railroad.deliver(VACATED, {"block": "dn_w"})

    assert "dn_w" not in state.locks
    assert "dn_w" not in state.residue


def test_a_vacate_before_the_arrival_waits_for_it() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    assert [p["into"] for p in railroad.granted()] == ["dn_w"]
    state = railroad.dispatcher.state

    railroad.deliver(VACATED, {"block": "yard_w"}, answer=False)

    assert drains(railroad.said) == []
    assert state.locks["yard_w"] == "freight_1"
    assert len(railroad.granted()) == 1

    railroad.deliver(OCCUPIED, {"block": "dn_w"}, answer=False)

    assert state.block_of["freight_1"] == "dn_w"
    assert "yard_w" not in state.locks
    assert len(railroad.granted()) == 2

    railroad.answered = 1
    railroad.answer()
    assert {"id": "r-1"} in railroad.leaf("request_completed")


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_clear_reading_from_before_the_grant_does_not_end_the_move(
    strategy: type[Incremental | FullRoute],
) -> None:
    """`yard_w` drops out under `freight_1` and the power is turned on again
    over it: the arrival waits for a vacate heard while the move is
    outstanding (#806)."""
    railroad = Railroad(strategy)
    railroad.deliver(VACATED, {"block": "yard_w"})
    state = railroad.dispatcher.state
    railroad.drained()
    railroad.power(ON)
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    assert [p["into"] for p in railroad.granted()] == ["dn_w"]

    railroad.deliver(OCCUPIED, {"block": "dn_w"}, answer=False)

    released = railroad.leaf("lock_released")
    assert not [p for p in released if "yard_w" in p["resources"]]
    assert state.locks["yard_w"] == "freight_1"
    assert state.locks["west_ladder.to_dn"] == "freight_1"
    assert "freight_1" in state.crossing
    assert state.block_of["freight_1"] == "dn_w"

    railroad.deliver(OCCUPIED, {"block": "yard_w"}, answer=False)
    # Asked for, and not answered: the train is still crossing, so a person
    # ends the drain before `layout` would switch anything off.
    assert drains(railroad.said) == [DRAINING, DRAINING]
    railroad.power(DRAINING, answer=False)
    railroad.power(ON, answer=False)
    railroad.deliver(VACATED, {"block": "yard_w"}, answer=False)

    assert {
        "train": "freight_1",
        "resources": ["yard_w", "west_ladder.to_dn"],
    } in railroad.leaf("lock_released")
    assert state.crossing["freight_1"] == "crossover.dn_straight"


def test_a_clear_reading_taken_back_does_not_end_the_move() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    state = railroad.dispatcher.state

    railroad.deliver(VACATED, {"block": "yard_w"}, answer=False)
    railroad.deliver(OCCUPIED, {"block": "yard_w"}, answer=False)
    assert drains(railroad.said) == [DRAINING]
    railroad.deliver(OCCUPIED, {"block": "dn_w"}, answer=False)

    assert "freight_1" in state.crossing
    assert state.locks["yard_w"] == "freight_1"


def test_a_repeat_reading_changes_nothing() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    state = railroad.dispatcher.state

    for topic, block in ((VACATED, "yard_w"), (OCCUPIED, "dn_w")):
        railroad.deliver(topic, {"block": block}, answer=False)
        locks, block_of, said = (
            dict(state.locks),
            dict(state.block_of),
            len(railroad.said),
        )
        railroad.deliver(topic, {"block": block}, answer=False)
        assert state.locks == locks
        assert state.block_of == block_of
        assert len(railroad.said) == said
        assert drains(railroad.said) == []


def test_a_vacate_before_the_arrival_on_the_last_move() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A", answer=False)

    railroad.deliver(VACATED, {"block": "yard_w"}, answer=False)
    assert not railroad.leaf("request_completed")

    railroad.deliver(OCCUPIED, {"block": "dn_w"}, answer=False)
    assert railroad.leaf("request_completed") == [{"id": "r-1"}]
    assert railroad.dispatcher.state.block_of["freight_1"] == "dn_w"


def test_a_cancelled_request_retires_on_the_arrival() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A", answer=False)
    railroad.deliver(CANCEL_WANTED, {"id": "r-1"}, answer=False)

    railroad.deliver(VACATED, {"block": "yard_w"}, answer=False)
    assert not railroad.leaf("request_cancelled")

    railroad.deliver(OCCUPIED, {"block": "dn_w"}, answer=False)
    assert [p["id"] for p in railroad.leaf("request_cancelled")] == ["r-1"]
    assert railroad.dispatcher.state.locks == {
        "dn_w": "freight_1",
        "up_e": "express_2",
    }


def test_a_placement_over_a_broken_table() -> None:
    """The lock on `freight_1`'s block gone by hand: placing it elsewhere
    gives up only what it holds."""
    railroad = Railroad()
    railroad.power(OFF)
    state = railroad.dispatcher.state
    del state.locks["yard_w"]

    railroad.deliver(PLACEMENT_WANTED, {"train": "freight_1", "block": "dn_w"})

    assert state.block_of["freight_1"] == "dn_w"
    assert state.locks["dn_w"] == "freight_1"
