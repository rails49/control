"""A train with no further grant stops at its block's far sensor, with every app
that has a say in it on one bus (#1169).

`layout`, the scheduler, the dispatcher and the driver on a line of four blocks,
in `automatic`, with `tc49.lib.invariants` held throughout. The sensors are told
what the steel would make them read. What this measures is the case that was
stranded when the first sensor stopped the train: with its tail still on the
last exit sensor as its head reached the next block's entry, the train stopped
and its move never ended.
"""

from tc49.bench.runner import DEFAULT_K, NONCE
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC
from tc49.lib.layout import Layout
from tc49.lib.roster import Coupled, Roster, Train
from tc49.scheduler import Scheduler
from tests.invariants import checked
from tests.layout.railroad import (
    MOVING,
    POWER_WANTED,
    commanded,
    energised,
    heard,
    loco,
    reads,
    settle,
    speeds,
    switches,
)

BLOCKS = ("a", "b", "c", "d")
TRAIN = "freight"
REQUEST_COMPLETED = "tc49/dispatch/request_completed"
MOVE_GRANTED = "tc49/dispatch/move_granted"


def line() -> Layout:
    return Layout.from_document(
        {
            "layout": "line",
            "blocks": {block: {"length": 1000} for block in BLOCKS},
            "connections": {
                "ab": {"transits": {"t": ["a.B", "b.A"]}},
                "bc": {"transits": {"t": ["b.B", "c.A"]}},
                "cd": {"transits": {"t": ["c.B", "d.A"]}},
            },
        }
    )


class Railroad:
    """Every app on one bus, `freight` standing in `a` nose to `a.B`, with its
    whole length at that end and the railroad live and in `automatic`."""

    def __init__(self) -> None:
        layout = line()
        roster = Roster("line", {TRAIN: Train((Coupled(loco("3")),))})
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        stood = {TRAIN: "a"}
        self.app = LayoutInterface(
            self.bus, layout, roster, self.clock, position=stood, sensor_silence_s=60.0
        )
        Scheduler(self.bus, layout, {TRAIN: "a.A-to-B"}, nonce=NONCE)
        Dispatcher(self.bus, layout, roster, stood, Incremental(layout, DEFAULT_K))
        Driver(self.bus)
        checked(self.bus, layout, roster)
        switches(self.bus, AUTOMATIC)
        self.bus.publish(POWER_WANTED, {"power": "on"})
        energised(self.bus)
        for block in BLOCKS:
            reads(self.bus, f"{block}.A", "clear")
            reads(self.bus, f"{block}.B", "occupied" if block == "a" else "clear")
        self.settle()
        self.granted = heard(self.bus, MOVE_GRANTED)
        self.completed = heard(self.bus, REQUEST_COMPLETED)
        self.written: list[tuple[str, Payload]] = commanded(self.bus)
        self.bus.drain()
        self.written.clear()

    def settle(self) -> None:
        settle(self.bus, self.app, self.clock)

    def read(self, end: str, level: str = "occupied") -> None:
        reads(self.bus, end, level)
        self.settle()

    def requests(self, dest: str) -> None:
        self.bus.publish(
            "tc49/schedule/request_wanted", {"train": TRAIN, "dest": [dest]}
        )
        self.bus.drain()

    def stops(self) -> int:
        """How many times the train has been written `0.0`."""
        return sum(speed == 0.0 for _addr, speed in speeds(self.written))

    def moving(self) -> bool:
        return bool(self.bus.last_values[MOVING]["moving"])


def test_a_train_with_its_tail_on_the_exit_sensor_runs_on_to_its_far_sensor() -> None:
    railroad = Railroad()
    railroad.requests("b.A")
    assert railroad.written, "the train was given no speed"
    assert railroad.stops() == 0

    # The head reaches the next block's entry with the tail on the last exit
    # sensor: both blocks read occupied, and the train runs on.
    railroad.read("b.A")
    assert railroad.stops() == 0
    assert railroad.completed == []

    # The tail clears, and the tail clears the entry sensor behind it.
    railroad.read("a.B", "clear")
    assert railroad.stops() == 0
    railroad.read("b.A", "clear")
    assert railroad.stops() == 0

    # The far sensor stops it, standing at its signal.
    railroad.read("b.B")
    assert speeds(railroad.written)[-1] == ("3", 0.0)
    assert railroad.stops() == 1
    assert len(railroad.completed) == 1
    assert railroad.moving() is False


def test_a_train_with_its_next_move_granted_before_the_far_sensor_runs_through() -> (
    None
):
    railroad = Railroad()
    railroad.requests("c.A")

    railroad.read("b.A")
    railroad.read("a.B", "clear")
    # Its first move ended on those two, so its second is granted with the
    # train between the sensors of `b`.
    assert [payload["into"] for _topic, payload in railroad.granted] == ["b", "c"]
    railroad.read("b.A", "clear")
    railroad.read("b.B")
    assert railroad.stops() == 0

    railroad.read("c.A")
    assert railroad.stops() == 0
    railroad.read("b.B", "clear")
    assert railroad.stops() == 0
    railroad.read("c.A", "clear")
    assert railroad.stops() == 0

    railroad.read("c.B")
    assert speeds(railroad.written)[-1] == ("3", 0.0)
    assert railroad.stops() == 1
    assert len(railroad.completed) == 1
    assert railroad.moving() is False
