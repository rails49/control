"""A move runs on what its sensors read, and no train is sent into a block that
reads occupied (#791, ADR-0077, #1171).

Each test drives a dispatcher on a bus of its own over `crossover-yard/meet`,
answering every `move_granted` with its entry sensor occupied, then its exit
sensor occupied and clear, then its entry sensor clear, unless the case says
otherwise — and the lock table breaks no rule after any delivery (ADR-0076).
The four paths here are ones the physical railroad produces: a sensor
stuck occupied with the power turned on again over it, a sensor dropping
out under a standing train with the power turned on again over it, a train's own residue on its way back,
and a clear behind before the occupied ahead, which a train shorter than the
gap between two blocks' sensors gives in normal running.
"""

from typing import Any

import pytest

from tc49.dispatcher import FullRoute, Incremental
from tc49.dispatcher.dispatch import broken
from tc49.lib.bus import Payload
from tc49.lib.inventory import OFF, ON
from tests.dispatcher.test_lock_rules import a_bus_dispatcher, deliver, drains
from tests.harness import POWER, settled

REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"

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
            move = self.dispatcher.state.following[train][-1]
            for reading in (
                settled(move.entry),
                settled(move.exit),
                settled(move.exit, False),
                settled(move.entry, False),
            ):
                self.deliver(*reading, answer=False)

    def power(self, value: str, answer: bool = True) -> None:
        """The layout stating the power, as a binding answering a press
        would."""
        self.deliver(POWER, {"power": value}, answer)

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
    """`yard_e` reads occupied, with nothing claiming it."""
    railroad = Railroad(strategy)
    railroad.deliver(*settled("yard_e.A"))
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
    assert drains(railroad.said) == []

    railroad.deliver(*settled("yard_e.A", False))

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
    railroad.deliver(*settled("dn_w.B"))
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

    railroad.deliver(*settled("dn_w.B", False))

    assert "dn_w" not in state.locks
    assert "dn_w" not in state.residue


def test_a_clear_behind_before_the_head_is_in_releases_only_the_block_left() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    assert [p["into"] for p in railroad.granted()] == ["dn_w"]
    state = railroad.dispatcher.state

    railroad.deliver(*settled("yard_w.B"), answer=False)
    railroad.deliver(*settled("yard_w.B", False), answer=False)

    assert drains(railroad.said) == []
    assert "yard_w" not in state.locks
    assert state.block_of["freight_1"] == "dn_w"
    assert state.locks["west_ladder.to_dn"] == "freight_1"
    assert len(railroad.granted()) == 1

    railroad.deliver(*settled("dn_w.A"), answer=False)

    assert len(railroad.granted()) == 2


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_an_exit_sensor_occupied_at_the_grant_then_clear_releases_the_block(
    strategy: type[Incremental | FullRoute],
) -> None:
    """`yard_w.B` drops out under `freight_1` and reads occupied again before the
    grant: it stands occupied at the grant, and clear from there is the tail out
    (#806)."""
    railroad = Railroad(strategy)
    railroad.deliver(*settled("yard_w.B", False))
    railroad.deliver(*settled("yard_w.B"))
    state = railroad.dispatcher.state
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    assert [p["into"] for p in railroad.granted()] == ["dn_w"]

    railroad.deliver(*settled("dn_w.A"), answer=False)

    released = railroad.leaf("lock_released")
    assert not [p for p in released if "yard_w" in p["resources"]]
    assert state.locks["yard_w"] == "freight_1"
    assert state.locks["west_ladder.to_dn"] == "freight_1"
    assert state.block_of["freight_1"] == "dn_w"

    railroad.deliver(*settled("yard_w.B", False), answer=False)

    assert {"train": "freight_1", "resources": ["yard_w"]} in railroad.leaf(
        "lock_released"
    )
    assert state.locks["west_ladder.to_dn"] == "freight_1"
    assert state.crossing["freight_1"] == "crossover.dn_straight"


def test_a_clear_reading_with_no_occupied_before_it_releases_nothing() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    state = railroad.dispatcher.state

    railroad.deliver(*settled("yard_w.B", False), answer=False)
    assert drains(railroad.said) == []
    railroad.deliver(*settled("dn_w.A"), answer=False)

    assert state.locks["yard_w"] == "freight_1"


def test_a_repeat_reading_changes_nothing() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    state = railroad.dispatcher.state

    for reading in (settled("yard_w.B", False), settled("dn_w.A")):
        railroad.deliver(*reading, answer=False)
        locks, block_of, said = (
            dict(state.locks),
            dict(state.block_of),
            len(railroad.said),
        )
        railroad.deliver(*reading, answer=False)
        assert state.locks == locks
        assert state.block_of == block_of
        assert len(railroad.said) == said
        assert drains(railroad.said) == []


def test_a_request_completes_when_its_entry_sensor_clears() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A", answer=False)

    railroad.deliver(*settled("dn_w.A"), answer=False)
    assert not railroad.leaf("request_completed")
    assert railroad.dispatcher.state.block_of["freight_1"] == "dn_w"

    railroad.deliver(*settled("dn_w.A", False), answer=False)
    assert railroad.leaf("request_completed") == [{"id": "r-1"}]


def test_a_cancelled_request_retires_at_the_end_of_its_move() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A", answer=False)
    railroad.deliver(CANCEL_WANTED, {"id": "r-1"}, answer=False)

    railroad.deliver(*settled("dn_w.A"), answer=False)
    assert not railroad.leaf("request_cancelled")

    railroad.deliver(*settled("dn_w.A", False), answer=False)
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


ALLOCATION = "tc49/dispatch/state/allocation"


def recorded_before_granted(railroad: Railroad, block: str, into: str) -> bool:
    """Whether the allocation naming `freight_1` in `block` went out before
    the `move_granted` taking it into `into`."""
    said = [(t, dict(p)) for t, p in railroad.said]
    recorded = next(
        i
        for i, (t, p) in enumerate(said)
        if t == ALLOCATION and p["trains"].get("freight_1") == block
    )
    granted = next(
        i
        for i, (t, p) in enumerate(said)
        if t.endswith("/move_granted") and p["into"] == into
    )
    return recorded < granted


def test_the_head_in_is_recorded_before_the_next_grant() -> None:
    """The scheduler moves facing on the allocation, and `layout` reads that
    facing for the next `move`, so the allocation recording the head in goes
    out first (#1038, #1025, ADR-0052)."""
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A", answer=False)
    railroad.deliver(*settled("dn_w.A"), answer=False)

    assert recorded_before_granted(railroad, "dn_w", "dn_e")


def test_a_request_ending_is_recorded_before_the_next_ones_grant() -> None:
    """The same for the first move of a chained request, granted by the
    sweep of the reading that completes the one before it."""
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A", answer=False)
    railroad.deliver(
        REQUEST_SUBMITTED,
        {"id": "r-2", "train": "freight_1", "dest": ["yard_e.A"], "after": "r-1"},
        answer=False,
    )
    railroad.deliver(*settled("dn_w.A"), answer=False)
    railroad.deliver(*settled("dn_w.A", False), answer=False)

    assert railroad.leaf("request_completed") == [{"id": "r-1"}]
    assert recorded_before_granted(railroad, "dn_w", "dn_e")
