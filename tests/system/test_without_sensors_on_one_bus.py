"""A railroad run without sensors, then by them, with every app that has a say in
it on one bus (#1324).

`layout`, the scheduler, the dispatcher and the driver on the four-block line of
`test_far_sensor_stop.py`, in `automatic`, with `tc49.lib.invariants` held
throughout. The owner turns the setting on, drags a train, drives it over,
presses "arrived", drags it on, and later turns the setting off and runs by
sensors. No sensor row is published until then.
"""

from tc49.bench.runner import DEFAULT_K, NONCE
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC
from tc49.lib.roster import Coupled, Roster, Train
from tc49.scheduler import Scheduler
from tests.invariants import checked
from tests.layout.railroad import (
    ALIGN,
    ALLOCATION,
    FACING,
    MOVE,
    PLACED,
    POWER_WANTED,
    SETTINGS_WANTED,
    commanded,
    energised,
    heard,
    loco,
    reads,
    settle,
    speeds,
    switches,
)
from tests.system.test_far_sensor_stop import (
    BLOCKS,
    MOVE_GRANTED,
    REQUEST_COMPLETED,
    TRAIN,
    line,
)

ARRIVAL_WANTED = "tc49/dispatch/arrival_wanted"
REQUEST_SUBMITTED = "tc49/dispatch/request_submitted"
ROUTE_CHOSEN = "tc49/dispatch/route_chosen"

AS_A_SHORT_TRAIN_BACK = [
    ("d.A", "clear"),
    ("c.B", "occupied"),
    ("c.B", "clear"),
    ("c.A", "occupied"),
    ("c.A", "clear"),
    ("b.B", "occupied"),
    ("b.B", "clear"),
    ("b.A", "occupied"),
    ("b.A", "clear"),
    ("a.B", "occupied"),
    ("a.B", "clear"),
]
"""A short train from `d.A` to `a`: clear behind before each block's entry
sensor reads it, and one sensor at a time everywhere."""


class Unsensed:
    """Every app on one bus, `freight` standing in `block` facing `facing`, the
    railroad set to run without sensors, live and in `automatic`, and no
    sensor heard."""

    def __init__(self, block: str = "a", facing: str = "a.A-to-B") -> None:
        layout = line()
        roster = Roster("line", {TRAIN: Train((Coupled(loco("3")),))})
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        stood = {TRAIN: block}
        self.app = LayoutInterface(
            self.bus, layout, roster, self.clock, position=stood, sensor_silence_s=60.0
        )
        Scheduler(self.bus, layout, {TRAIN: facing}, nonce=NONCE)
        Dispatcher(self.bus, layout, roster, stood, Incremental(layout, DEFAULT_K))
        Driver(self.bus)
        checked(self.bus, layout, roster)
        self.setting(True)
        switches(self.bus, AUTOMATIC)
        self.bus.publish(POWER_WANTED, {"power": "on"})
        energised(self.bus)
        self.aligns = heard(self.bus, ALIGN)
        self.moves = heard(self.bus, MOVE)
        self.granted = heard(self.bus, MOVE_GRANTED)
        self.submitted = heard(self.bus, REQUEST_SUBMITTED)
        self.chosen = heard(self.bus, ROUTE_CHOSEN)
        self.completed = heard(self.bus, REQUEST_COMPLETED)
        self.placed = heard(self.bus, PLACED)
        self.written: list[tuple[str, Payload]] = commanded(self.bus)
        self.bus.drain()
        self.written.clear()

    def setting(self, without_sensors: bool) -> None:
        self.bus.publish(SETTINGS_WANTED, {"without_sensors": without_sensors})
        self.bus.drain()

    def requests(self, dest: str) -> None:
        self.bus.publish(
            "tc49/schedule/request_wanted", {"train": TRAIN, "dest": [dest]}
        )
        self.bus.drain()

    def latest(self) -> str:
        """The id of the request submitted last."""
        return str(self.submitted[-1][1]["id"])

    def arrived(self) -> None:
        self.bus.publish(ARRIVAL_WANTED, {"id": self.latest()})
        self.bus.drain()

    def facing(self) -> str:
        return str(self.bus.last_values[FACING]["facing"][TRAIN])

    def read(self, end: str, level: str = "occupied") -> None:
        reads(self.bus, end, level)
        settle(self.bus, self.app, self.clock)


def test_two_runs_without_sensors_and_one_by_them() -> None:
    railroad = Unsensed()

    # A drag sets the route and nothing drives the train.
    railroad.requests("c.A")
    assert [payload["route"] for _topic, payload in railroad.chosen] == [
        ["a", "ab.t", "b", "bc.t", "c"]
    ]
    assert [
        (payload["connection"], payload["transit"])
        for _topic, payload in railroad.aligns
    ] == [(None, None)]
    assert railroad.granted == []
    assert railroad.moves == []
    assert railroad.written == []

    # "Arrived": the train stands in `c`, nose-first from `a`, so its nose
    # points away from `c.A`, the end it came in by.
    first = railroad.latest()
    railroad.arrived()
    assert [payload["id"] for _topic, payload in railroad.completed] == [first]
    assert [payload for _topic, payload in railroad.placed] == [
        {"train": TRAIN, "block": "c"}
    ]
    assert railroad.facing() == "c.A-to-B"
    assert railroad.app.position[TRAIN] == "c"

    # The next drag leaves `c` by the end facing `d`.
    railroad.requests("d.A")
    assert railroad.submitted[-1][1]["depart"] == "c.B"
    assert railroad.chosen[-1][1]["route"] == ["c", "cd.t", "d"]
    railroad.arrived()
    assert len(railroad.completed) == 2
    # `d.B` is a wall, so the train faces the one end it can leave by.
    assert railroad.facing() == "d.B-to-A"
    assert railroad.granted == []
    assert railroad.written == []

    # The setting off, and every sensor reporting as the steel would make it
    # read with the train at `d.A`: a drag back to `a` is run by them.
    railroad.setting(False)
    for block in BLOCKS:
        railroad.read(f"{block}.A", "occupied" if block == "d" else "clear")
        railroad.read(f"{block}.B", "clear")
    railroad.requests("a.B")
    assert railroad.submitted[-1][1]["depart"] == "d.A"
    assert [payload["into"] for _topic, payload in railroad.granted] == ["c"]
    # `layout` drove the move, so the train stood at its near end and faced it.
    assert [speed for _addr, speed in speeds(railroad.written)][-1] > 0.0

    for end, level in AS_A_SHORT_TRAIN_BACK:
        railroad.read(end, level)
    assert [payload["into"] for _topic, payload in railroad.granted] == [
        "c",
        "b",
        "a",
    ]
    assert len(railroad.completed) == 3
    picture = railroad.bus.last_values[ALLOCATION]
    assert picture["locks"] == {"a": TRAIN}
    assert picture["trains"] == {TRAIN: "a"}


def test_a_propelled_run_without_sensors_faces_the_end_entered() -> None:
    """`freight` stands in `b` with its nose at `b.A` and is sent out of
    `b.B`, its tail end. A drag departs by the nose, so the request is
    submitted as the scenario's requests are, or as a page may submit one
    (ADR-0019). Propelled into `c` through `c.A`, its nose points at that end,
    and the next drag leaves by it."""
    railroad = Unsensed("b", "b.B-to-A")

    railroad.bus.publish(
        REQUEST_SUBMITTED,
        {"id": "freight-1", "train": TRAIN, "depart": "b.B", "dest": ["c.A"]},
    )
    railroad.bus.drain()
    assert [payload["route"] for _topic, payload in railroad.chosen] == [
        ["b", "bc.t", "c"]
    ]
    assert [
        (payload["connection"], payload["transit"])
        for _topic, payload in railroad.aligns
    ] == [(None, None)]
    assert railroad.granted == []
    assert railroad.moves == []
    assert railroad.written == []

    railroad.arrived()
    assert [payload["id"] for _topic, payload in railroad.completed] == ["freight-1"]
    assert [payload for _topic, payload in railroad.placed] == [
        {"train": TRAIN, "block": "c"}
    ]
    assert railroad.facing() == "c.B-to-A"

    railroad.requests("a.B")
    assert railroad.submitted[-1][1]["depart"] == "c.A"
    assert railroad.chosen[-1][1]["route"] == ["c", "bc.t", "b", "ab.t", "a"]
