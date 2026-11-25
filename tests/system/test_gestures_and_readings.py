"""A person's gestures and detector faults, at any moment, over the assembly.

The five properties of ARCHITECTURE.md draw placements and request sequences
and then let the railroad run. The railroad also gets a person's gestures at
any moment, and detector readings no train caused, and the bugs those inputs
made were found by review rather than by a test (#806, #836, #811, #791).
This drives them as a Hypothesis state machine over the live assembly: each
step is one gesture, one reading or one turn of the live loop, and after
every message the bus delivers the lock table's rules hold (#1042), and a
train granted a move has no permanent obstacle on what is left of its route
(#1150): a reading or a placement can leave `safe()` false, so it is not what
holds here. The invariants over what the bus shows hold too
(`tests/invariants.py`, ADR-0096).

The readings are what the layout interface publishes, standing in for
hardware that reports a block emptying under a standing train or filling
with nothing there (#1154). The simulator is the binding: the physical one
publishes the same two events.
"""

import unittest
from typing import Any, cast

import pytest
from hypothesis import note, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    precondition,
    rule,
)

from tc49.dispatcher import Incremental
from tc49.dispatcher.dispatch import broken
from tc49.dispatcher.locking import state_view
from tc49.lib.bus import Payload
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.lib.scenario import TrainSpec
from tests.generate import ENDS, LAYOUTS, ROSTERS, fixture_yaml, scenarios
from tests.harness import (
    Assembly,
    assemble_live,
    left_crossing,
    press,
    settled,
    ticks,
)
from tests.invariants import check as check_invariants

ALLOCATION = "tc49/dispatch/state/allocation"

UNMINTED = "nobody-minted-this"
"""A request id no scheduler minted: a stale or forged gesture's."""

UNKNOWN_ADDR = "unknown-point"
"""A point address no railroad of the library wears. The library railroads
have no points at all, so without it the point rule would draw from nothing;
a press naming an address nobody wears is still a gesture a page can send."""


def assembled(
    layout: Layout, roster: Roster, trains: dict[str, TrainSpec]
) -> tuple[Assembly, list[str]]:
    """The live assembly with `trains` standing, the lock table's rules and the
    grant's held after every message and the invariants checked, and the ids
    of the requests submitted on it, a list that grows."""
    assembly = assemble_live(layout, roster, trains, Incremental)
    check_invariants(assembly, Incremental)
    minted: list[str] = []

    def collect(topic: str, payload: Payload) -> None:
        minted.append(str(payload["id"]))

    def lock_table(topic: str, payload: Payload) -> None:
        assert broken(assembly.dispatcher.state) == [], f"after {topic} {payload}"

    def grant(topic: str, payload: Payload) -> None:
        state = assembly.dispatcher.state
        train = str(payload["train"])
        if train in state.active:
            _cur, rem, idle, _held = state_view(state)
            assert not set(rem[train]) & set(idle), f"after granting {payload}"

    assembly.bus.subscribe("tc49/dispatch/request_submitted", collect)
    assembly.bus.subscribe("#", lock_table)
    assembly.bus.subscribe("tc49/dispatch/move_granted", grant)
    assembly.bus.drain()
    return assembly, minted


def test_a_run_without_sensors_ended_by_arrived() -> None:
    """The setting on, `t1` dragged from west_1 to e_main and said to have
    arrived, and the setting off: the rules below in that order (#1324)."""
    layout_id = "single-track-meet"
    assembly, minted = assembled(
        LAYOUTS[layout_id], ROSTERS[layout_id], {"t1": TrainSpec("west_1", "A-to-B")}
    )
    press(assembly, "tc49/layout/power_wanted", {"power": "on"})
    press(assembly, "tc49/layout/settings_wanted", {"without_sensors": True})
    press(
        assembly, "tc49/schedule/request_wanted", {"train": "t1", "dest": ["e_main.A"]}
    )
    press(assembly, "tc49/dispatch/arrival_wanted", {"id": minted[-1]})
    press(assembly, "tc49/layout/settings_wanted", {"without_sensors": False})

    assert assembly.dispatcher.state.block_of == {"t1": "e_main"}


def test_on_a_run_without_sensors_launched_for_a_train_left_crossing() -> None:
    """`t1` is granted its move out of west by sensors, the setting goes on,
    which ends the request and leaves the train crossing, and `t1` is dragged
    again. The launch kept the crossing, so the train was active with no move
    and crossing, which the lock table forbids (#1324). Found by the state
    machine below.
    """
    layout_id = "facing-pair"
    assembly, _minted = assembled(
        LAYOUTS[layout_id], ROSTERS[layout_id], {"t1": TrainSpec("west", "A-to-B")}
    )
    press(assembly, "tc49/schedule/request_wanted", {"train": "t1", "dest": ["east.A"]})
    press(assembly, "tc49/layout/settings_wanted", {"without_sensors": True})
    press(assembly, "tc49/schedule/request_wanted", {"train": "t1", "dest": ["east.A"]})

    picture = assembly.bus.last_values[ALLOCATION]
    assert picture["crossing"] == {}
    assert picture["occupied"] == {"t1": ["west", "gap.east_A__west_B", "east"]}


@pytest.mark.xfail(
    reason="a train a restart or a change of without_sensors leaves crossing is"
    " launched by sensors and granted a move while crossing (ADR-0047): #1326",
    strict=True,
)
def test_on_a_drag_by_sensors_for_a_train_left_crossing() -> None:
    """`t1` is granted its move out of west by sensors, the setting goes on and
    off again, which ends the request and leaves the train crossing, and `t1`
    is dragged again. Nothing resolves a crossing with no move behind it but a
    placement or a removal, and the launch grants a move over the transit the
    train is listed crossing. A restart's crossing hint does the same. Found
    by the state machine below, which draws no drag for such a train
    (`left_crossing`)."""
    layout_id = "facing-pair"
    assembly, _minted = assembled(
        LAYOUTS[layout_id], ROSTERS[layout_id], {"t1": TrainSpec("west", "A-to-B")}
    )
    press(assembly, "tc49/schedule/request_wanted", {"train": "t1", "dest": ["east.A"]})
    press(assembly, "tc49/layout/settings_wanted", {"without_sensors": True})
    press(assembly, "tc49/layout/settings_wanted", {"without_sensors": False})
    press(assembly, "tc49/schedule/request_wanted", {"train": "t1", "dest": ["east.A"]})


@settings(deadline=None, stateful_step_count=40, max_examples=1000)
class GesturesAndReadings(RuleBasedStateMachine):
    """One live run, driven one gesture, reading or turn at a time."""

    assembly: Assembly
    layout: Layout
    roster: Roster
    layout_id: str
    minted: list[str]

    @initialize(case=scenarios())
    def come_up(self, case: tuple[dict[str, Any], Any, Any, Any]) -> None:
        doc, layout, roster, scenario = case
        note(fixture_yaml(doc))
        self.layout = layout
        self.roster = roster
        self.layout_id = doc["layout"]
        # The scenario's trains stand where it puts them; its requests are not
        # used, every request here being a drag drawn by the rules.
        self.assembly, self.minted = assembled(layout, roster, scenario.trains)

    def press(self, topic: str, payload: Payload) -> None:
        note(f"{topic} {payload}")
        press(self.assembly, topic, payload)

    def trains(self) -> st.SearchStrategy[str]:
        """A train of the roster, the ones standing on the layout first: the
        library rosters hold far more trains than a case places, and a train
        off the layout goes nowhere, so drawn evenly most drags would move
        nothing."""
        placed = sorted(self.assembly.dispatcher.state.block_of)
        everyone = st.sampled_from(sorted(self.roster.trains))
        return st.sampled_from(placed) | everyone if placed else everyone

    def ids(self) -> st.SearchStrategy[str]:
        return st.sampled_from([*self.minted, UNMINTED])

    def blocks(self) -> st.SearchStrategy[str]:
        return st.sampled_from(sorted(self.layout.blocks))

    @rule(data=st.data())
    def drag(self, data: st.DataObject) -> None:
        dest = data.draw(
            st.lists(
                st.sampled_from(ENDS[self.layout_id]),
                min_size=1,
                max_size=2,
                unique=True,
            )
        )
        train = data.draw(self.trains())
        if left_crossing(self.assembly.bus.last_values, train):
            note(f"no drag for {train}, left crossing")
            return
        self.press("tc49/schedule/request_wanted", {"train": train, "dest": dest})

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

    @rule(data=st.data())
    def point(self, data: st.DataObject) -> None:
        addrs = sorted(
            {
                point.addr
                for connection in self.layout.connections.values()
                for way in connection.points.values()
                for point in way
            }
        )
        self.press(
            "tc49/dispatch/point_wanted",
            {
                "addr": data.draw(st.sampled_from([*addrs, UNKNOWN_ADDR])),
                "position": data.draw(st.sampled_from(["closed", "thrown"])),
            },
        )

    @rule(data=st.data())
    def arrived(self, data: st.DataObject) -> None:
        self.press("tc49/dispatch/arrival_wanted", {"id": data.draw(self.ids())})

    @rule(without_sensors=st.booleans())
    def setting(self, without_sensors: bool) -> None:
        self.press("tc49/layout/settings_wanted", {"without_sensors": without_sensors})

    @rule(power=st.sampled_from(["on", "draining", "off"]))
    def power(self, power: str) -> None:
        self.press("tc49/layout/power_wanted", {"power": power})

    @rule(data=st.data())
    def placement(self, data: st.DataObject) -> None:
        self.press(
            "tc49/dispatch/placement_wanted",
            {
                "train": data.draw(self.trains()),
                "block": data.draw(st.none() | self.blocks()),
            },
        )

    @precondition(lambda self: bool(self.assembly.dispatcher.state.block_of))
    @rule(data=st.data())
    def dropout(self, data: st.DataObject) -> None:
        held = sorted(set(self.assembly.dispatcher.state.block_of.values()))
        self.press(*settled(f"{data.draw(st.sampled_from(held))}.A", False))

    @rule(data=st.data())
    def reading(self, data: st.DataObject) -> None:
        self.press(*settled(f"{data.draw(self.blocks())}.A"))

    @rule()
    def time_passes(self) -> None:
        note("a turn of the live loop")
        ticks(self.assembly, 1)


# Hypothesis builds the class at run time, so it is untyped to pyright.
TestGesturesAndReadings = cast(
    type[unittest.TestCase],
    GesturesAndReadings.TestCase,  # pyright: ignore[reportUnknownMemberType]
)
