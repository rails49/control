"""The lock table follows a train by what its sensors read, with every app that
has a say in it on one bus (#1171).

`layout`, the scheduler, the dispatcher and the driver on a line of four blocks,
with `tc49.lib.invariants` held throughout, the sensors told what the steel would
make them read as a long train and as a short one pass from `a` to `d`. Each runs
with no stop until `d`'s far sensor, its request completes, and every lock but `d`
is released. Then the same on the simulator as the binding.
"""

import pytest

from tc49.bench.runner import assemble_live
from tc49.dispatcher import Incremental
from tc49.lib.scenario import TrainSpec
from tests.harness import events, press, stock, ticks
from tests.invariants import check
from tests.system.test_far_sensor_stop import TRAIN, Railroad, line

AS_A_LONG_TRAIN = [
    ("b.A", "occupied"),
    ("a.B", "clear"),
    ("b.B", "occupied"),
    ("b.A", "clear"),
    ("c.A", "occupied"),
    ("b.B", "clear"),
    ("c.B", "occupied"),
    ("c.A", "clear"),
    ("d.A", "occupied"),
    ("c.B", "clear"),
]
"""Its tail is on each block's exit sensor as its head reaches the next block's
entry sensor, so that block's move is granted with the tail behind it."""

AS_A_SHORT_TRAIN = [
    ("a.B", "clear"),
    ("b.A", "occupied"),
    ("b.A", "clear"),
    ("b.B", "occupied"),
    ("b.B", "clear"),
    ("c.A", "occupied"),
    ("c.A", "clear"),
    ("c.B", "occupied"),
    ("c.B", "clear"),
    ("d.A", "occupied"),
]
"""Clear behind before each block's entry sensor reads it, and one sensor at a
time everywhere."""


@pytest.mark.parametrize(
    "readings",
    [AS_A_LONG_TRAIN, AS_A_SHORT_TRAIN],
    ids=["a long train", "a short train"],
)
def test_a_train_runs_from_a_to_d_with_no_stop_short_of_ds_far_sensor(
    readings: list[tuple[str, str]],
) -> None:
    railroad = Railroad()
    railroad.requests("d.A")

    for end, level in readings:
        railroad.read(end, level)
        assert railroad.stops() == 0, f"stopped at {end} {level}"

    assert [p["into"] for _topic, p in railroad.granted] == ["b", "c", "d"]
    assert railroad.completed == []

    railroad.read("d.A", "clear")
    assert railroad.stops() == 0
    assert len(railroad.completed) == 1
    assert railroad.moving() is False

    railroad.read("d.B")
    assert railroad.stops() == 1

    picture = railroad.bus.last_values["tc49/dispatch/state/allocation"]
    assert picture["locks"] == {"d": TRAIN}
    assert picture["occupied"] == {TRAIN: ["d"]}
    assert picture["trains"] == {TRAIN: "d"}


def test_the_same_run_on_the_simulator() -> None:
    layout = line()
    roster = stock(**{TRAIN: 500})
    assembly = assemble_live(
        layout, roster, {TRAIN: TrainSpec("a", "A-to-B")}, Incremental
    )
    check(assembly)
    press(
        assembly,
        "tc49/schedule/request_wanted",
        {"train": TRAIN, "dest": ["d.A"]},
    )

    ticks(assembly, 10)

    assert [line["into"] for line in events(assembly.trace, "move_granted")] == [
        "b",
        "c",
        "d",
    ]
    assert len(events(assembly.trace, "request_completed")) == 1
    picture = events(assembly.trace, "allocation")[-1]
    assert picture["locks"] == {"d": TRAIN}
    assert picture["occupied"] == {TRAIN: ["d"]}
