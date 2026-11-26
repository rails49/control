"""A timetable recorded and run again, with every app that has a say in it on
one bus (#1345, #1355).

The scheduler, the dispatcher, the driver and the simulator as the layout
binding on crossover-yard, with `tc49.lib.invariants` held throughout. The
scheduler's store client holds its documents in memory. The simulator has a
fast clock that runs one minute for each second of its run clock, and a train
is three of those seconds over a move. Nothing sleeps: the simulator's live
loop is run with its waits not slept.

A person records three drags and a turn-round, moves the trains away with
Record off, and loads the recording with power off. With power on the trains
are driven to their start blocks, the clock is set to the start time and each
entry goes out at its time.

    yard_w.B -+- dn_w.A  dn_w.B -+- dn_e.A  dn_e.B -+- yard_e.A
              +- up_w.A  up_w.B -+- up_e.A  up_e.B -+

`freight_1` starts in `dn_w` nose to `dn_w.B`, and `express_2` in `up_e` nose
to `up_e.A`.
"""

from collections.abc import Callable
from typing import Any

from tc49.bench.runner import DEFAULT_K, NONCE, facing, placement
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.clock_row import FastClockRow
from tc49.lib.fast_clock import FastClock, KeptClock
from tc49.lib.inventory import leaf
from tc49.lib.scenario import TrainSpec
from tc49.scheduler import Scheduler
from tc49.simulator import Simulator
from tests.harness import load
from tests.invariants import checked
from tests.scheduler.test_recording import Store

FREIGHT = "freight_1"
EXPRESS = "express_2"

STANDS = {
    FREIGHT: TrainSpec("dn_w", "A-to-B"),
    EXPRESS: TrainSpec("up_e", "B-to-A"),
}
"""Where the two trains stand when the run begins."""

SIX = 6 * 3600
"""06:00 in seconds since midnight, where the fast clock starts."""

SPEED_UP = 60.0
"""A fast-clock minute for each second of run clock."""

POWER_WANTED = "tc49/layout/power_wanted"
POWER = "tc49/layout/state/power"
CLOCK = "tc49/layout/state/clock"
REQUEST_WANTED = "tc49/schedule/request_wanted"
REVERSAL_WANTED = "tc49/schedule/reversal_wanted"
TIMETABLE_WANTED = "tc49/schedule/timetable_wanted"
RECORD_WANTED = "tc49/schedule/timetable_record_wanted"
TIMETABLE = "tc49/schedule/state/timetable"
FACING = "tc49/schedule/state/facing"
ALLOCATION = "tc49/dispatch/state/allocation"
MOVING = "tc49/dispatch/state/moving"

type Document = dict[str, Any]

TO_DN_E: Document = {"at": "06:02", "train": FREIGHT, "to": ["dn_e.A", "dn_e.B"]}
TO_YARD_W: Document = {"at": "06:03", "train": EXPRESS, "to": ["yard_w.A", "yard_w.B"]}
TURN: Document = {"at": "06:08", "train": FREIGHT, "turn": True}
TO_DN_W: Document = {"at": "06:09", "train": FREIGHT, "to": ["dn_w.A", "dn_w.B"]}
ENTRIES = [TO_DN_E, TO_YARD_W, TURN, TO_DN_W]
"""The four entries the person records, in the timetable's order."""

RECORDED: Document = {
    "timetable": "untitled",
    "layout": "crossover-yard",
    "start": "06:00",
    "trains": {
        EXPRESS: {"at": "up_e", "facing": "B-to-A"},
        FREIGHT: {"at": "dn_w", "facing": "A-to-B"},
    },
    "entries": ENTRIES,
}
"""The document the store holds once the person has made three drags and a
turn-round."""


class Railroad:
    """Every app on one bus on crossover-yard, the two trains standing as
    `STANDS` has them and power off. `heard` is every message since, each
    with the minute the clock row before it read."""

    def __init__(self) -> None:
        layout, roster, _scenario = load("crossover-yard/meet")
        self.store = Store()
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        self.reads = ""
        self.heard: list[tuple[str, str, Payload]] = []
        self.bus.subscribe("#", self._hear)
        stood = placement(STANDS)
        clock = FastClockRow(
            self.bus,
            FastClock(SIX, SPEED_UP, self.clock.now),
            KeptClock(SIX, SPEED_UP),
            lambda: self.clock.now,
            lambda kept: None,
        )
        self.simulator = Simulator(
            self.bus, layout, self.clock, stood, transit_s=1.0, clear_s=1.0, fast=clock
        )
        Scheduler(
            self.bus, layout, facing(layout, STANDS), nonce=NONCE, store=self.store
        )
        Dispatcher(self.bus, layout, roster, stood, Incremental(layout, DEFAULT_K))
        Driver(self.bus)
        checked(self.bus, layout, roster)
        self.bus.drain()

    def _hear(self, topic: str, payload: Payload) -> None:
        if topic == CLOCK:
            time = payload["time"]
            self.reads = f"{time // 3600:02d}:{time // 60 % 60:02d}"
        self.heard.append((self.reads, topic, payload))

    def press(self, topic: str, payload: Payload) -> None:
        """A gesture as a page puts it on the bus."""
        self.bus.publish(topic, payload)
        self.bus.drain()

    def runs(self, until: Callable[[], bool]) -> None:
        """The simulator's live loop, its waits not slept, until `until`
        holds."""
        left = 100

        def stop() -> bool:
            nonlocal left
            if until():
                return True
            assert left, "the railroad did not get there in 100 turns"
            left -= 1
            return False

        self.simulator.run_live(3600.0, sleep=lambda seconds: None, stop=stop)

    def runs_to(self, minute: str) -> None:
        """The run goes on until a clock row reads `minute`."""
        self.runs(lambda: self.reads == minute)

    def said(self, name: str, since: int = 0) -> list[Payload]:
        """Every payload heard on the topics whose leaf is `name`, in order,
        from position `since` of `heard` on."""
        return [
            payload
            for _minute, topic, payload in self.heard[since:]
            if leaf(topic) == name
        ]

    def leaves(self, since: int, *names: str) -> list[str]:
        """The leaf of each message heard from position `since` of `heard`
        on that is one of `names`, in order."""
        found = [leaf(topic) for _minute, topic, _payload in self.heard[since:]]
        return [one for one in found if one in names]

    def submitted(self, since: int = 0) -> list[tuple[str, str, str, list[str]]]:
        """Each request submitted from position `since` of `heard` on: the
        minute the clock read, the train, its departure end and its arrival
        ends."""
        return [
            (minute, payload["train"], payload["depart"], payload["dest"])
            for minute, topic, payload in self.heard[since:]
            if leaf(topic) == "request_submitted"
        ]

    def faced(self, train: str, since: int = 0) -> list[tuple[str, str]]:
        """Each facing `train` took from position `since` of `heard` on, with
        the minute the clock read."""
        took: list[tuple[str, str]] = []
        for minute, topic, payload in self.heard[since:]:
            if topic == FACING and (
                not took or took[-1][1] != payload["facing"][train]
            ):
                took.append((minute, payload["facing"][train]))
        return took

    def row(self) -> dict[str, Any]:
        """The timetable row, less its stamp."""
        said = dict(self.bus.last_values[TIMETABLE])
        del said["at"]
        return said

    def completed(self, since: int = 0) -> list[str]:
        """The ids of the requests that completed, in order, from position
        `since` of `heard` on."""
        return [payload["id"] for payload in self.said("request_completed", since)]

    def moving(self) -> bool:
        """Whether the dispatcher says a train is moving."""
        return bool(self.bus.last_values[MOVING]["moving"])

    def stand(self) -> dict[str, str]:
        """The block each train stands in, as the dispatcher says it."""
        return dict(self.bus.last_values[ALLOCATION]["trains"])

    def drags(self, train: str, to: str) -> str:
        """A person's drag of `train` to the middle of the block `to`,
        which a page sends as both of its ends. The id of the request it was
        composed into."""
        ends = [f"{to}.A", f"{to}.B"]
        self.press(REQUEST_WANTED, {"train": train, "dest": ends})
        submitted = self.said("request_submitted")[-1]
        assert (submitted["train"], submitted["dest"]) == (train, ends)
        return str(submitted["id"])


def test_a_timetable_is_recorded_and_run_again() -> None:
    railroad = Railroad()

    # 1. Power on, with two trains placed: the scheduler makes `untitled`.
    railroad.press(POWER_WANTED, {"power": "on"})
    railroad.runs_to("06:00")
    assert railroad.row() == {
        "timetable": "untitled",
        "phase": "running",
        "record": True,
        "start": "06:00",
        "trains": RECORDED["trains"],
        "positioning": [],
        "entries": [],
    }

    # 2. Three drags and a turn-round, the clock moving between them.
    railroad.runs_to("06:02")
    out = railroad.drags(FREIGHT, "dn_e")
    railroad.runs_to("06:03")
    west = railroad.drags(EXPRESS, "yard_w")
    railroad.runs_to("06:08")
    assert railroad.completed() == [out, west]
    railroad.press(REVERSAL_WANTED, {"train": FREIGHT})
    railroad.runs_to("06:09")
    back = railroad.drags(FREIGHT, "dn_w")
    railroad.runs(lambda: back in railroad.completed())
    assert railroad.completed() == [out, west, back]

    # 3. The document has the four entries and where the trains stood.
    assert railroad.store.document("untitled") == RECORDED

    # 4. Record off, and the trains dragged elsewhere: the document stays.
    railroad.press(RECORD_WANTED, {"record": False})
    away = [railroad.drags(EXPRESS, "yard_e"), railroad.drags(FREIGHT, "yard_w")]
    railroad.runs(lambda: set(away) <= set(railroad.completed()))
    assert railroad.stand() == {EXPRESS: "yard_e", FREIGHT: "yard_w"}
    assert railroad.row()["record"] is False
    assert railroad.store.document("untitled") == RECORDED

    # 5. Power off.
    assert railroad.moving() is False
    railroad.press(POWER_WANTED, {"power": "off"})
    assert railroad.bus.last_values[POWER]["power"] == "off"

    # 6. The person loads `untitled`: each train is sent to its start block,
    # to the end that leaves it facing as recorded. Power on.
    loaded = len(railroad.heard)
    railroad.press(TIMETABLE_WANTED, {"timetable": "untitled"})
    assert railroad.submitted(loaded) == [
        (railroad.reads, EXPRESS, "yard_e.A", ["up_e.B"]),
        (railroad.reads, FREIGHT, "yard_w.B", ["dn_w.A"]),
    ]
    to_start = [payload["id"] for payload in railroad.said("request_submitted", loaded)]
    assert railroad.row() == {
        "timetable": "untitled",
        "phase": "loaded",
        "record": False,
        "start": "06:00",
        "trains": RECORDED["trains"],
        "positioning": to_start,
        "entries": [entry | {"state": "later"} for entry in ENTRIES],
    }
    railroad.press(POWER_WANTED, {"power": "on"})

    # 7. Each train is driven to its start block. Then the clock is asked
    # for the start time and the timetable runs.
    railroad.runs(lambda: railroad.row()["phase"] == "running")
    assert sorted(railroad.completed(loaded)) == sorted(to_start)
    assert railroad.stand() == {EXPRESS: "up_e", FREIGHT: "dn_w"}
    assert railroad.bus.last_values[FACING]["facing"] == {
        EXPRESS: "up_e.B-to-A",
        FREIGHT: "dn_w.A-to-B",
    }
    assert railroad.leaves(loaded, "request_completed", "clock_wanted") == [
        "request_completed",
        "request_completed",
        "clock_wanted",
    ]
    assert railroad.said("clock_wanted") == [{"time": SIX}]
    assert railroad.reads == "06:00"
    assert (railroad.row()["phase"], railroad.row()["positioning"]) == ("running", [])
    started = len(railroad.heard)

    # 8. Each entry goes out as the clock reaches its time, and completes.
    railroad.runs(lambda: len(railroad.completed(started)) == 2)
    assert railroad.submitted(started) == [
        ("06:02", FREIGHT, "dn_w.B", ["dn_e.A", "dn_e.B"]),
        ("06:03", EXPRESS, "up_e.A", ["yard_w.A", "yard_w.B"]),
    ]
    assert railroad.reads == "06:07"

    # 9. Between two entries, with no train moving, power off: the clock
    # rows repeat one time and no entry is released.
    assert railroad.moving() is False
    railroad.press(POWER_WANTED, {"power": "off"})
    stood = len(railroad.heard)
    railroad.runs(lambda: len(railroad.said("clock", stood)) == 5)
    assert [said["time"] for said in railroad.said("clock", stood)] == [
        SIX + 7 * 60
    ] * 5
    assert railroad.submitted(stood) == []
    assert [entry["state"] for entry in railroad.row()["entries"]] == [
        "ended",
        "ended",
        "later",
        "later",
    ]

    # Power on, and the run goes on to the last entry. The turn-round turns
    # the train before the entry after it leaves, by the end it now faces.
    railroad.press(POWER_WANTED, {"power": "on"})
    railroad.runs(lambda: len(railroad.completed(started)) == 3)
    assert railroad.submitted(stood) == [
        ("06:09", FREIGHT, "dn_e.A", ["dn_w.A", "dn_w.B"]),
    ]
    assert railroad.faced(FREIGHT, started) == [
        ("06:03", "dn_e.A-to-B"),
        ("06:08", "dn_e.B-to-A"),
        ("06:10", "dn_w.B-to-A"),
    ]
    first, second, last = (
        payload["id"] for payload in railroad.said("request_submitted", started)
    )
    assert railroad.completed(started) == [first, second, last]
    assert railroad.row()["entries"] == [
        TO_DN_E | {"state": "ended", "request": first, "ended": 5 * 60},
        TO_YARD_W | {"state": "ended", "request": second, "ended": 7 * 60},
        TURN | {"state": "ended"},
        TO_DN_W | {"state": "ended", "request": last, "ended": 12 * 60},
    ]
    assert railroad.store.document("untitled") == RECORDED
