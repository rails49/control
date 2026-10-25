"""The layout interface under the assembly, driven by gestures and hardware.

`test_gestures_and_readings.py` runs the simulator as the layout binding, and
the simulator's trains carry no addresses, so nothing generated drives
`layout`, which writes the traction, point and signal rows and whose bugs stop
a train on the steel (#1041). This is the same kind of state machine over
`LayoutInterface`, the scheduler, the dispatcher and the driver on one bus,
with the bench railroad and roster of `tests/layout/railroad.py` (#1053). The
test plays the hardware: no translator runs, and the device rows are the ones
it publishes — a detector's reading, a point's position, the supply and a
link — whatever was asked for, including readings no train caused.

Each step is one publish and a drain, or time passing and the settling it
drives. After every message the invariants over what the bus shows hold
(`tests/invariants.py`, ADR-0096), and no handler raises.
"""

import unittest
from typing import cast

from hypothesis import note, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, precondition, rule

from tc49.bench.runner import DEFAULT_K, NONCE
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.layout.interface import SETTLING_S, THROTTLE_SILENCE_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tc49.scheduler import Scheduler
from tests.invariants import checked
from tests.layout.railroad import (
    ALLOCATION,
    DEVICE_LINK,
    DEVICE_SENSOR,
    DEVICE_TRACK,
    DRIVING_WANTED,
    POINTS,
    POWER_WANTED,
    TAKE_WANTED,
    THROTTLE_ALIVE,
    THROTTLE_WANTED,
    elapse,
    railroad,
    settle,
    stock,
)

DEVICE_POINT = "tc49/layout/state/device/point"

UNMINTED = "nobody-minted-this"
"""A request id no scheduler minted: a stale or forged gesture's."""

THROTTLES = ("t-1", "t-2")
"""Two throttle pages, so a take can find a train another throttle holds."""

LINKS = ("dccex", "detectors")
"""Two participants, so one's `up` cannot stand for the other's `down`."""

ADDRS = sorted({point["addr"] for way in POINTS.values() for point in way})
"""The bench railroad's addressed points, `12` and `13`."""


@settings(deadline=None, stateful_step_count=40, max_examples=1500)
class LayoutUnderTheAssembly(RuleBasedStateMachine):
    """One run of the bench railroad, driven one publish at a time."""

    bus: InProcessBus
    app: LayoutInterface
    clock: Clock
    minted: list[str]

    @initialize(data=st.data())
    def come_up(self, data: st.DataObject) -> None:
        self.layout = railroad()
        self.roster = stock()
        self.clock = Clock()
        self.bus = InProcessBus(self.clock)
        self.minted = []
        self.app = LayoutInterface(self.bus, self.layout, self.roster, self.clock)
        Scheduler(self.bus, self.layout, {}, nonce=NONCE)
        Dispatcher(
            self.bus,
            self.layout,
            self.roster,
            {},
            Incremental(self.layout, DEFAULT_K),
        )
        Driver(self.bus)
        self.bus.drain()
        checked(self.bus, self.layout, self.roster, Incremental)

        def collect(topic: str, payload: Payload) -> None:
            self.minted.append(str(payload["id"]))

        self.bus.subscribe("tc49/dispatch/request_submitted", collect)
        self.press(DRIVING_WANTED, {"driving": AUTOMATIC})
        # A train or two standing and the power on, as #1042's run starts
        # from a scenario's: from nothing, few of 40 steps would move a train,
        # and with all three blocks full none can. Only the one-car trains
        # fit a block of this railroad, so only they can stand on it.
        shortest = min(self.layout.blocks.values())
        fits = sorted(
            name
            for name, train in self.roster.trains.items()
            if train.length <= shortest
        )
        blocks = data.draw(st.permutations(sorted(self.layout.blocks)))
        standing = data.draw(
            st.lists(st.sampled_from(fits), min_size=1, max_size=2, unique=True)
        )
        for train, block in zip(standing, blocks):
            self.press(
                "tc49/dispatch/placement_wanted", {"train": train, "block": block}
            )
        self.press(POWER_WANTED, {"power": "on"})
        self.press(DEVICE_TRACK, {"power": "on"})

    def press(self, topic: str, payload: Payload) -> None:
        note(f"{topic} {payload}")
        self.bus.publish(topic, payload)
        self.bus.drain()

    def trains(self) -> st.SearchStrategy[str]:
        """A train of the roster, the ones standing first: a train off the
        railroad goes nowhere, so drawn evenly most drags would move nothing."""
        everyone = st.sampled_from(sorted(self.roster.trains))
        placed = self.bus.last_values.get(ALLOCATION, {}).get("trains", {})
        return st.sampled_from(sorted(placed)) | everyone if placed else everyone

    def ids(self) -> st.SearchStrategy[str]:
        return st.sampled_from([*self.minted, UNMINTED])

    def ends(self) -> st.SearchStrategy[str]:
        return st.sampled_from(
            sorted(f"{block}.{end}" for block in self.layout.blocks for end in "AB")
        )

    # -- a person's gestures, as #1042 draws them -------------------------

    @rule(data=st.data())
    def drag(self, data: st.DataObject) -> None:
        dest = data.draw(st.lists(self.ends(), min_size=1, max_size=2, unique=True))
        self.press(
            "tc49/schedule/request_wanted",
            {"train": data.draw(self.trains()), "dest": dest},
        )

    @rule(data=st.data())
    def cancel(self, data: st.DataObject) -> None:
        self.press("tc49/dispatch/cancel_wanted", {"id": data.draw(self.ids())})

    @rule(data=st.data())
    def reorder(self, data: st.DataObject) -> None:
        self.press(
            "tc49/dispatch/reorder_wanted",
            {
                "id": data.draw(self.ids()),
                "before": data.draw(st.none() | self.ids()),
            },
        )

    @rule(
        addr=st.sampled_from(ADDRS),
        position=st.sampled_from(["closed", "thrown"]),
    )
    def point(self, addr: str, position: str) -> None:
        self.press("tc49/dispatch/point_wanted", {"addr": addr, "position": position})

    @rule(power=st.sampled_from(["on", "draining", "off"]))
    def power(self, power: str) -> None:
        self.press(POWER_WANTED, {"power": power})

    @rule(data=st.data())
    def placement(self, data: st.DataObject) -> None:
        self.press(
            "tc49/dispatch/placement_wanted",
            {
                "train": data.draw(self.trains()),
                "block": data.draw(
                    st.none() | st.sampled_from(sorted(self.layout.blocks))
                ),
            },
        )

    # -- a throttle, and the driving mode ---------------------------------

    @rule(data=st.data())
    def take(self, data: st.DataObject) -> None:
        self.press(
            TAKE_WANTED,
            {
                "train": data.draw(self.trains()),
                "throttle": data.draw(st.none() | st.sampled_from(THROTTLES)),
            },
        )

    @rule(
        data=st.data(),
        speed=st.sampled_from([-1.0, -0.5, 0.0, 0.5, 1.0]),
    )
    def lever(self, data: st.DataObject, speed: float) -> None:
        self.press(
            THROTTLE_WANTED,
            {
                "train": data.draw(self.trains()),
                "speed": speed,
                "throttle": data.draw(st.sampled_from(THROTTLES)),
            },
        )

    @rule(throttle=st.sampled_from(THROTTLES))
    def alive(self, throttle: str) -> None:
        self.press(THROTTLE_ALIVE, {"throttle": throttle})

    @rule(driving=st.sampled_from([AUTOMATIC, MANUAL]))
    def driving(self, driving: str) -> None:
        self.press(DRIVING_WANTED, {"driving": driving})

    # -- the hardware -----------------------------------------------------

    @rule(data=st.data(), level=st.sampled_from(["occupied", "clear", "unknown"]))
    def reading(self, data: st.DataObject, level: str) -> None:
        """A detector's level at any end, which no train need have caused."""
        end = data.draw(self.ends())
        self.press(f"{DEVICE_SENSOR}/{end}", {"addr": end, "occupancy": level})

    @precondition(
        lambda self: bool(self.app._crossing)  # pyright: ignore[reportPrivateUsage]
    )
    @rule(data=st.data())
    def train_moves(self, data: st.DataObject) -> None:
        """What a train `layout` holds as crossing reads next: its head in
        the entered block, fully in at its far end, or its tail out of the
        block behind."""
        crossings = self.app._crossing  # pyright: ignore[reportPrivateUsage]
        block = data.draw(st.sampled_from(sorted(crossings)))
        crossing = crossings[block]
        near = f"{block}.A" if crossing.far.endswith(".B") else f"{block}.B"
        step = data.draw(st.sampled_from(["head", "in", "tail"]))
        if step == "tail":
            ends = [f"{crossing.origin}.A", f"{crossing.origin}.B"]
            level = "clear"
        else:
            ends = [near if step == "head" else crossing.far]
            level = "occupied"
        note(f"{crossing.train}: {step}")
        for end in ends:
            self.press(f"{DEVICE_SENSOR}/{end}", {"addr": end, "occupancy": level})

    @rule(addr=st.sampled_from(ADDRS), position=st.sampled_from(["closed", "thrown"]))
    def point_reports(self, addr: str, position: str) -> None:
        self.press(f"{DEVICE_POINT}/{addr}", {"addr": addr, "position": position})

    @rule(power=st.sampled_from(["on", "off"]))
    def track_reports(self, power: str) -> None:
        self.press(DEVICE_TRACK, {"power": power})

    @rule(link=st.sampled_from(LINKS), state=st.sampled_from(["up", "down"]))
    def link_reports(self, link: str, state: str) -> None:
        self.press(f"{DEVICE_LINK}/{link}", {"id": link, "link": state})

    # -- time -------------------------------------------------------------

    @rule(
        seconds=st.sampled_from(
            [SETTLING_S / 2, SETTLING_S, THROTTLE_SILENCE_S, 2 * THROTTLE_SILENCE_S]
        )
    )
    def time_passes(self, seconds: float) -> None:
        note(f"{seconds} s pass, and the settling time")
        elapse(self.clock, seconds)
        settle(self.bus, self.app, self.clock)


# Hypothesis builds the class at run time, so it is untyped to pyright.
TestLayoutUnderTheAssembly = cast(
    type[unittest.TestCase],
    LayoutUnderTheAssembly.TestCase,  # pyright: ignore[reportUnknownMemberType]
)
