"""The lock table follows a train by what each sensor reads, against the move it
was granted (#1165, #1171).

Driven at the bus on `crossover-yard/meet`, with the row a layout binding
publishes. `freight_1` stands in `yard_w` and is sent to `yard_e` over `dn_w` and
`dn_e`, and the lock table breaks no rule after any delivery (ADR-0076).
"""

from collections.abc import Callable
from typing import Any

import pytest

from tc49.bench.runner import DEFAULT_K, placement
from tc49.dispatcher import Dispatcher, FullRoute, Incremental
from tc49.dispatcher.dispatch import ALLOCATION, Adopted, broken, restored
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.inventory import ON
from tests.dispatcher.test_lock_rules import a_bus_dispatcher, deliver
from tests.harness import POWER, load, retaining, settled

STRATEGIES = [Incremental, FullRoute]
Strategy = type[Incremental | FullRoute]

REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
CANCEL_WANTED = "tc49/dispatch/cancel_wanted"
MOVE_WITHDRAWN = "tc49/layout/move_withdrawn"
UNKNOWN_SENSORS = "tc49/layout/state/unknown_sensors"
MOVING = "tc49/dispatch/state/moving"
DISPUTED = "tc49/dispatch/state/disputed"

T1 = "west_ladder.to_dn"
T2 = "crossover.dn_straight"
T3 = "east_ladder.from_dn"
TRAIN = "freight_1"


class Railroad:
    """The dispatcher with the power on, each frame's table checked."""

    def __init__(self, strategy: Strategy = Incremental) -> None:
        self.bus, self.dispatcher, self.said = a_bus_dispatcher(strategy)
        self.state = self.dispatcher.state
        self.bus.subscribe(
            "tc49/layout/withdraw_wanted",
            lambda topic, payload: self.said.append((topic, payload)),
        )

    def deliver(self, topic: str, payload: Payload) -> None:
        deliver(self.bus, topic, payload)
        assert broken(self.state) == []

    def read(self, sensor: str, occupied: bool = True) -> None:
        self.deliver(*settled(sensor, occupied))

    def clear(self, sensor: str) -> None:
        self.read(sensor, False)

    def request(self, rid: str, depart: str, dest: str, train: str = TRAIN) -> None:
        self.deliver(
            REQUEST_SUBMITTED,
            {"id": rid, "train": train, "depart": depart, "dest": [dest]},
        )

    def lists(self, *sensors: str) -> None:
        self.deliver(
            UNKNOWN_SENSORS,
            {
                "sensors": [
                    {"sensor": sensor, "reason": "no report", "reported": True}
                    for sensor in sensors
                ]
            },
        )

    def leaf(self, name: str) -> list[dict[str, Any]]:
        return [dict(p) for t, p in self.said if t.endswith(f"/{name}")]

    def granted(self) -> list[str]:
        return [p["into"] for p in self.leaf("move_granted")]

    def released(self) -> list[list[str]]:
        return [p["resources"] for p in self.leaf("lock_released")]

    def completed(self) -> list[str]:
        return [p["id"] for p in self.leaf("request_completed")]

    def cancelled(self) -> list[str]:
        return [p["id"] for p in self.leaf("request_cancelled")]

    def on(self) -> list[str]:
        return self.state.occupied[TRAIN]

    def picture(self) -> dict[str, list[str]]:
        return dict(self.bus.last_values[ALLOCATION]["occupied"])

    def disputed(self) -> list[str]:
        return list(self.bus.last_values[DISPUTED]["blocks"])

    def moving(self) -> bool:
        return bool(self.bus.last_values[MOVING]["moving"])

    def ends_on_its_far_sensor(self) -> None:
        """`freight_1` run to `dn_w`, the head in by `dn_w.B` with `dn_w.A`
        listed as it passed."""
        self.request("r-1", "yard_w.B", "dn_w.A")
        self.lists("dn_w.A")
        self.read("dn_w.B")


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_each_reading_of_a_move_in_turn(strategy: Strategy) -> None:
    railroad = Railroad(strategy)
    railroad.request("r-1", "yard_w.B", "yard_e.A")

    # The move is granted: T is occupied.
    assert railroad.on() == ["yard_w", T1]
    assert railroad.state.crossing == {TRAIN: T1}

    # The exit sensor occupied says nothing to the table.
    railroad.read("yard_w.B")
    assert railroad.on() == ["yard_w", T1]

    # The head in: Y is occupied, and the next move is granted.
    railroad.read("dn_w.A")
    assert railroad.on() == ["yard_w", T1, "dn_w", T2]
    assert railroad.state.block_of[TRAIN] == "dn_w"
    assert railroad.granted() == ["dn_w", "dn_e"]
    assert railroad.released() == []

    # The tail out of X: X is released, naming X.
    railroad.clear("yard_w.B")
    assert railroad.on() == [T1, "dn_w", T2]
    assert railroad.released() == [["yard_w"]]

    # The whole train in Y: T is released.
    railroad.clear("dn_w.A")
    assert railroad.on() == ["dn_w", T2]
    assert railroad.released() == [["yard_w"], [T1]]
    assert railroad.picture()[TRAIN] == ["dn_w", T2]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_long_train_is_granted_its_next_move_with_its_tail_behind_it(
    strategy: Strategy,
) -> None:
    railroad = Railroad(strategy)
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    railroad.read("yard_w.B")
    assert railroad.picture()[TRAIN] == ["yard_w", T1]

    railroad.read("dn_w.A")

    assert railroad.granted() == ["dn_w", "dn_e"]
    assert railroad.picture()[TRAIN] == ["yard_w", T1, "dn_w", T2]

    railroad.clear("yard_w.B")
    assert railroad.picture()[TRAIN] == [T1, "dn_w", T2]

    railroad.clear("dn_w.A")
    assert railroad.picture()[TRAIN] == ["dn_w", T2]
    assert railroad.released() == [["yard_w"], [T1]]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_short_train_clears_behind_before_its_head_is_in(strategy: Strategy) -> None:
    railroad = Railroad(strategy)
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.read("yard_w.B")

    railroad.clear("yard_w.B")

    assert railroad.released() == [["yard_w"]]
    assert railroad.state.block_of[TRAIN] == "dn_w"
    assert railroad.state.crossing == {TRAIN: T1}
    assert railroad.on() == [T1]
    assert railroad.disputed() == []
    assert "yard_w.B" not in railroad.bus.last_values["tc49/dispatch/state/aspects"]

    railroad.read("dn_w.A")
    assert railroad.on() == [T1, "dn_w"]
    assert railroad.state.locks[T1] == TRAIN

    railroad.clear("dn_w.A")
    assert railroad.on() == ["dn_w"]
    assert railroad.completed() == ["r-1"]
    assert railroad.disputed() == []


def test_a_passed_signal_shows_stop_when_the_tail_has_left() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.read("yard_w.B")
    aspects = railroad.bus.last_values["tc49/dispatch/state/aspects"]["aspects"]
    assert aspects["yard_w.B"] != "stop"

    railroad.clear("yard_w.B")

    aspects = railroad.bus.last_values["tc49/dispatch/state/aspects"]["aspects"]
    assert aspects["yard_w.B"] == "stop"


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_both_sensors_clear_a_train_in_its_block_is_granted(
    strategy: Strategy,
) -> None:
    railroad = Railroad(strategy)
    railroad.clear("yard_w.A")
    railroad.clear("yard_w.B")

    railroad.request("r-1", "yard_w.B", "dn_w.A")

    assert railroad.granted() == ["dn_w"]
    assert railroad.disputed() == []


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_train_placed_beyond_its_exit_sensor_releases_x_and_t_together(
    strategy: Strategy,
) -> None:
    railroad = Railroad(strategy)
    railroad.request("r-1", "yard_w.B", "dn_w.A")

    railroad.read("dn_w.A")
    assert railroad.on() == ["yard_w", T1, "dn_w"]

    railroad.clear("dn_w.A")

    assert railroad.released() == [["yard_w", T1]]
    assert railroad.on() == ["dn_w"]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_train_passing_an_unknown_entry_sensor_leaves_its_transit_occupied(
    strategy: Strategy,
) -> None:
    railroad = Railroad(strategy)
    railroad.ends_on_its_far_sensor()

    assert railroad.completed() == ["r-1"]
    assert railroad.state.block_of[TRAIN] == "dn_w"
    assert railroad.state.locks[T1] == TRAIN
    assert T1 in railroad.on()
    assert railroad.moving() is False


def test_that_transit_goes_at_the_next_moves_tail_in() -> None:
    railroad = Railroad()
    railroad.ends_on_its_far_sensor()
    railroad.lists()

    railroad.request("r-2", "dn_w.B", "dn_e.A")
    assert railroad.on()[-1] == T2
    assert railroad.state.locks[T1] == TRAIN

    railroad.read("dn_e.A")
    railroad.clear("dn_e.A")

    assert T1 not in railroad.state.locks
    assert railroad.on() == ["dn_e"]


def test_that_transit_goes_at_a_placement() -> None:
    railroad = Railroad()
    railroad.ends_on_its_far_sensor()

    railroad.deliver(PLACEMENT_WANTED, {"train": TRAIN, "block": "up_w"})

    assert T1 not in railroad.state.locks
    assert railroad.on() == ["up_w"]
    assert railroad.state.following.get(TRAIN) is None


def test_the_far_sensor_ends_the_request_and_the_entry_sensor_still_releases() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.read("dn_w.A")

    railroad.read("dn_w.B")
    assert railroad.completed() == ["r-1"]
    assert railroad.state.locks[T1] == TRAIN

    railroad.clear("dn_w.A")

    assert T1 not in railroad.state.locks
    assert railroad.completed() == ["r-1"]


def test_a_reading_no_move_expects_changes_nothing() -> None:
    """A person backing a train at a platform, and a clear under a train."""
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.read("dn_w.A")
    railroad.clear("dn_w.A")
    assert railroad.completed() == ["r-1"]
    on, locks = list(railroad.on()), dict(railroad.state.locks)

    railroad.read("dn_w.B")
    railroad.clear("dn_w.B")
    railroad.read("dn_w.B")
    railroad.clear("dn_w.B")
    railroad.clear("dn_w.A")

    assert railroad.on() == on
    assert railroad.state.locks == locks
    assert railroad.state.block_of[TRAIN] == "dn_w"
    assert railroad.disputed() == []


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_an_occupied_reading_on_a_block_only_held_ahead_disputes_it(
    strategy: Strategy,
) -> None:
    railroad = Railroad(strategy)
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    assert railroad.state.locks["dn_e"] == TRAIN

    railroad.read("dn_e.B")

    assert railroad.disputed() == ["dn_e"]

    railroad.read("dn_w.A")

    assert railroad.granted() == ["dn_w"]
    assert railroad.leaf("grant_refused")[-1]["obstacles"] == [
        {"resource": "dn_e", "holder": ""}
    ]


def test_a_block_a_train_occupies_or_its_move_enters_is_not_disputed() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")

    railroad.read("yard_w.A")
    railroad.read("dn_w.B")

    assert railroad.disputed() == []


def reversal(strategy: Strategy = Incremental) -> Railroad:
    """`freight_1` placed in `dn_e`, sent into the terminal track `yard_e`, and
    asked to come back out by the end it goes in by."""
    railroad = Railroad(strategy)
    railroad.deliver(POWER, {"power": "off"})
    railroad.deliver(PLACEMENT_WANTED, {"train": TRAIN, "block": "dn_e"})
    railroad.deliver(POWER, {"power": ON})
    railroad.request("r-1", "dn_e.B", "yard_e.A")
    railroad.request("r-2", "yard_e.A", "dn_e.B")
    assert railroad.granted() == ["yard_e"]
    return railroad


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_reversal_starts_only_when_the_last_request_has_ended(
    strategy: Strategy,
) -> None:
    railroad = reversal(strategy)

    railroad.read("yard_e.A")
    assert railroad.granted() == ["yard_e"]
    assert railroad.completed() == []

    railroad.clear("yard_e.A")

    assert railroad.completed() == ["r-1"]
    assert railroad.granted() == ["yard_e", "dn_e"]
    assert railroad.on() == ["yard_e", T3]

    # Its entry sensor is this move's exit sensor.
    railroad.read("yard_e.A")
    railroad.clear("yard_e.A")

    assert railroad.on() == [T3]
    assert railroad.state.block_of[TRAIN] == "dn_e"
    assert railroad.released()[-1] == ["yard_e"]


def test_a_reversal_past_an_unknown_entry_sensor_waits_for_the_far_sensor() -> None:
    railroad = reversal()
    railroad.lists("yard_e.A")
    railroad.read("yard_e.B")
    assert railroad.completed() == ["r-1"]
    # The train's block is out of use until the sensor returns.
    assert railroad.granted() == ["yard_e"]

    railroad.lists()

    assert railroad.granted() == ["yard_e", "dn_e"]
    assert railroad.on() == ["dn_e", "yard_e", T3]

    railroad.read("dn_e.B")
    railroad.clear("dn_e.B")

    assert railroad.on() == ["dn_e"]
    assert T3 not in railroad.state.locks
    assert "yard_e" not in railroad.state.locks


def test_a_cancel_with_the_head_not_in_asks_for_the_move_back() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A")

    railroad.deliver(CANCEL_WANTED, {"id": "r-1"})

    assert [t for t, _ in railroad.said if t.endswith("/withdraw_wanted")]
    assert railroad.cancelled() == []

    railroad.deliver(MOVE_WITHDRAWN, {"train": TRAIN, "transit": T1, "into": "dn_w"})

    assert railroad.cancelled() == ["r-1"]
    assert railroad.on() == ["yard_w"]
    assert railroad.state.locks == {"yard_w": TRAIN, "up_e": "express_2"}
    assert not railroad.state.following[TRAIN]


@pytest.mark.parametrize("ending", ["dn_w.A", "dn_w.B"])
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_cancel_with_the_head_in_and_the_tail_behind_retires_at_the_end(
    strategy: Strategy, ending: str
) -> None:
    railroad = Railroad(strategy)
    railroad.deliver(POWER, {"power": "draining"})
    railroad.deliver(POWER, {"power": ON})
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    railroad.deliver(POWER, {"power": "draining"})
    railroad.read("yard_w.B")
    railroad.read("dn_w.A")
    said = len(railroad.said)

    railroad.deliver(CANCEL_WANTED, {"id": "r-1"})

    assert not [t for t, _ in railroad.said[said:] if t.endswith("/withdraw_wanted")]
    assert railroad.cancelled() == []
    assert railroad.bus.last_values[ALLOCATION]["requests"][0]["cancelling"] == "dn_w"

    if ending == "dn_w.A":
        railroad.clear(ending)
        behind: list[str] = ["dn_w"]
        assert "yard_w" not in railroad.state.locks
    else:
        railroad.read(ending)
        behind = ["yard_w", T1, "dn_w"]

    assert railroad.cancelled() == ["r-1"]
    assert railroad.on() == behind
    assert {r for r, by in railroad.state.locks.items() if by == TRAIN} == set(behind)


def test_a_cancel_with_nothing_outstanding_retires_at_once() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    railroad.deliver(POWER, {"power": "draining"})
    railroad.read("dn_w.A")
    railroad.clear("dn_w.A")

    railroad.deliver(CANCEL_WANTED, {"id": "r-1"})

    assert railroad.cancelled() == ["r-1"]
    assert {r for r, by in railroad.state.locks.items() if by == TRAIN} == {"dn_w"}


def test_a_removal_keeps_what_reads_occupied_and_the_transit_beside_it() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "yard_e.A")
    railroad.read("yard_w.B")

    railroad.deliver(PLACEMENT_WANTED, {"train": TRAIN, "block": None})

    state = railroad.state
    assert state.residue == {"yard_w", T1}
    assert TRAIN not in state.occupied and TRAIN not in state.following
    assert state.locks["yard_w"] == TRAIN and state.locks[T1] == TRAIN

    railroad.clear("yard_w.B")

    assert state.residue == set()
    assert "yard_w" not in state.locks and T1 not in state.locks


def test_a_removal_residue_waits_for_a_listed_sensor_returning_at_an_equal_level() -> (
    None
):
    railroad = Railroad()
    railroad.read("yard_w.B")
    railroad.lists("yard_w.A")
    railroad.deliver(PLACEMENT_WANTED, {"train": TRAIN, "block": None})
    assert railroad.state.residue == {"yard_w"}

    railroad.clear("yard_w.B")
    assert railroad.state.residue == {"yard_w"}

    railroad.read("yard_w.A", False)
    assert railroad.state.residue == {"yard_w"}

    railroad.lists()

    assert railroad.state.residue == set()
    assert "yard_w" not in railroad.state.locks


def adopted(rows: dict[str, Payload]) -> tuple[InProcessBus, Dispatcher]:
    """A dispatcher come back up on a bus holding `rows`."""
    layout, roster, scenario = load("crossover-yard/meet")
    bus = retaining(rows)
    dispatcher = Dispatcher(
        bus, layout, roster, placement(scenario.trains), Incremental(layout, DEFAULT_K)
    )
    bus.drain()
    return bus, dispatcher


PICTURE: dict[str, Any] = {
    "trains": {"freight_1": "dn_w", "express_2": "up_e"},
    "crossing": {},
    "locks": {},
    "occupied": {"freight_1": [T1, "dn_w"], "express_2": ["up_e"]},
    "requests": [],
}


def test_a_restart_holds_and_publishes_what_the_picture_says_a_train_occupies() -> None:
    bus, dispatcher = adopted({ALLOCATION: PICTURE})

    state = dispatcher.state
    assert state.occupied == {"freight_1": [T1, "dn_w"], "express_2": ["up_e"]}
    assert state.locks == {T1: TRAIN, "dn_w": TRAIN, "up_e": "express_2"}
    assert bus.last_values[ALLOCATION]["occupied"] == state.occupied
    assert broken(state) == []


def test_a_restart_on_a_value_without_the_field_starts() -> None:
    picture = {key: value for key, value in PICTURE.items() if key != "occupied"}

    _, dispatcher = adopted({ALLOCATION: picture})

    assert dispatcher.state.occupied["freight_1"] == ["dn_w"]
    assert dispatcher.state.locks == {"dn_w": TRAIN, "up_e": "express_2"}


def test_a_restart_reads_the_field_an_entry_at_a_time() -> None:
    layout, roster, _ = load("crossover-yard/meet")
    picture = {
        **PICTURE,
        "occupied": {
            "freight_1": [T1, "gone.nowhere", "nowhere", 42, "up_e", "dn_w"],
            "express_2": "up_e",
        },
    }

    found: Adopted = restored(picture, layout, roster, {})

    assert found.occupied == {"freight_1": [T1, "dn_w"], "express_2": ["up_e"]}


def test_a_restart_gives_an_entry_to_the_train_that_took_it_first() -> None:
    layout, roster, _ = load("crossover-yard/meet")
    picture = {
        **PICTURE,
        "occupied": {"freight_1": [T2, "dn_w"], "express_2": [T2, "up_e"]},
    }

    found = restored(picture, layout, roster, {})

    assert found.occupied == {"freight_1": [T2, "dn_w"], "express_2": ["up_e"]}


def test_a_train_that_did_not_keep_its_place_adopts_none() -> None:
    layout, roster, _ = load("crossover-yard/meet")
    picture = {
        **PICTURE,
        "trains": {"express_2": "up_e", "freight_1": "up_e"},
        "occupied": {"freight_1": [T1, "up_e"], "express_2": ["up_e"]},
    }

    found = restored(picture, layout, roster, {"express_2": "up_e", TRAIN: "yard_w"})

    assert found.occupied[TRAIN] == ["yard_w"]


def test_after_a_restart_nothing_releases_until_the_next_move() -> None:
    sensors: dict[str, Payload] = dict([settled("dn_w.A", False)])
    bus, dispatcher = adopted({ALLOCATION: PICTURE, **sensors})
    state = dispatcher.state
    assert state.readings == {"dn_w.A": False}

    for reading in (settled("dn_w.A"), settled("dn_w.A", False)):
        bus.publish(*reading)
    bus.drain()
    assert state.locks[T1] == TRAIN
    assert not state.following

    bus.publish(POWER, {"power": ON})
    bus.publish(
        REQUEST_SUBMITTED,
        {"id": "r-1", "train": TRAIN, "depart": "dn_w.B", "dest": ["dn_e.A"]},
    )
    bus.publish(*settled("dn_e.A"))
    bus.publish(*settled("dn_e.A", False))
    bus.drain()

    assert T1 not in state.locks
    assert state.occupied[TRAIN] == ["dn_e"]


def test_moving_runs_from_the_grant_to_the_end_of_the_move() -> None:
    railroad = Railroad()
    assert railroad.moving() is False

    railroad.request("r-1", "yard_w.B", "dn_w.A")
    assert railroad.moving() is True

    railroad.read("dn_w.A")
    assert railroad.state.crossing == {}
    assert railroad.moving() is True

    railroad.clear("dn_w.A")
    assert railroad.moving() is False


def test_moving_goes_false_at_the_far_sensor() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")
    railroad.read("dn_w.A")

    railroad.read("dn_w.B")

    assert railroad.moving() is False


def test_moving_with_one_sensor_listed_and_with_both() -> None:
    railroad = Railroad()
    railroad.request("r-1", "yard_w.B", "dn_w.A")

    railroad.lists("dn_w.A")
    assert railroad.moving() is True

    railroad.lists("dn_w.A", "dn_w.B")
    assert railroad.moving() is False


def steps() -> list[Callable[[Railroad], None]]:
    """Every state a reading leaves, for `broken`."""
    return [
        lambda r: r.request("r-1", "yard_w.B", "yard_e.A"),
        lambda r: r.read("yard_w.B"),
        lambda r: r.clear("yard_w.B"),
        lambda r: r.read("dn_w.A"),
        lambda r: r.read("dn_w.B"),
        lambda r: r.clear("dn_w.A"),
        lambda r: r.clear("dn_w.B"),
        lambda r: r.read("dn_e.A"),
        lambda r: r.clear("dn_e.A"),
    ]


def test_the_lock_table_breaks_no_rule_along_a_move() -> None:
    railroad = Railroad()
    for step in steps():
        step(railroad)  # `Railroad.deliver` asserts it
    assert broken(railroad.state) == []


def test_an_entry_on_a_list_that_is_not_locked_is_a_broken_rule() -> None:
    railroad = Railroad()
    railroad.state.occupied[TRAIN].append("dn_e")

    assert broken(railroad.state) == [
        "freight_1 occupies dn_e, which is locked to nobody"
    ]


def test_a_second_train_through_the_same_sensor_changes_nothing_for_the_first() -> None:
    """`dn_w.A` is the exit `freight_1` left `dn_w` by, its move still being
    followed: a train coming in through it later reads nothing for it."""
    railroad = Railroad()
    railroad.deliver(POWER, {"power": "off"})
    railroad.deliver(PLACEMENT_WANTED, {"train": TRAIN, "block": "dn_w"})
    railroad.deliver(POWER, {"power": ON})
    railroad.request("r-1", "dn_w.A", "yard_w.B")
    railroad.read("dn_w.A")
    railroad.clear("dn_w.A")
    railroad.lists("yard_w.B")
    assert railroad.on() == [T1]
    locks = {r for r, by in railroad.state.locks.items() if by == TRAIN}

    railroad.read("dn_w.A")
    railroad.clear("dn_w.A")

    assert railroad.on() == [T1]
    assert {r for r, by in railroad.state.locks.items() if by == TRAIN} == locks
