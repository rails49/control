"""A person's gestures and detector faults, at any moment, over the assembly.

The five properties of ARCHITECTURE.md draw placements and request sequences
and then let the railroad run. The railroad also gets a person's gestures at
any moment, and detector readings no train caused, and the bugs those inputs
made were found by review rather than by a test (#806, #836, #811, #791).
This drives them as a Hypothesis state machine over the live assembly: each
step is one gesture, one reading or one turn of the live loop, and after
every message the bus delivers the lock table's rules hold, and after every
grant `safe()` does (#1042). The invariants over what the bus shows hold too
(`tests/invariants.py`, ADR-0096).

The readings are what the layout interface publishes, standing in for
hardware that reports a block emptying under a standing train or filling
with nothing there (ADR-0048). The simulator is the binding: the physical one
publishes the same two events.
"""

import unittest
from typing import Any, cast

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
from tc49.dispatcher.locking import safety_view
from tc49.dispatcher.safety import safe
from tc49.lib.bus import Payload
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tests.generate import ENDS, fixture_yaml, scenarios
from tests.harness import Assembly, assemble_live, press, ticks
from tests.invariants import check as check_invariants

UNMINTED = "nobody-minted-this"
"""A request id no scheduler minted: a stale or forged gesture's."""

UNKNOWN_ADDR = "unknown-point"
"""A point address no railroad of the library wears. The library railroads
have no points at all, so without it the point rule would draw from nothing;
a press naming an address nobody wears is still a gesture a page can send."""


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
        self.minted = []
        # The scenario's trains stand where it puts them; its requests are not
        # used, every request here being a drag drawn by the rules.
        self.assembly = assemble_live(layout, roster, scenario.trains, Incremental)
        check_invariants(self.assembly, Incremental)
        bus = self.assembly.bus

        def collect(topic: str, payload: Payload) -> None:
            self.minted.append(str(payload["id"]))

        def lock_table(topic: str, payload: Payload) -> None:
            assert (
                broken(self.assembly.dispatcher.state) == []
            ), f"after {topic} {payload}"

        def grant(topic: str, payload: Payload) -> None:
            assert safe(
                *safety_view(self.assembly.dispatcher.state)
            ), f"unsafe state after granting {payload}"

        bus.subscribe("tc49/dispatch/request_submitted", collect)
        bus.subscribe("#", lock_table)
        bus.subscribe("tc49/dispatch/move_granted", grant)
        bus.drain()

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
        self.press(
            "tc49/layout/block_vacated", {"block": data.draw(st.sampled_from(held))}
        )

    @rule(data=st.data())
    def reading(self, data: st.DataObject) -> None:
        self.press("tc49/layout/block_occupied", {"block": data.draw(self.blocks())})

    @rule()
    def time_passes(self) -> None:
        note("a turn of the live loop")
        ticks(self.assembly, 1)


# Hypothesis builds the class at run time, so it is untyped to pyright.
TestGesturesAndReadings = cast(
    type[unittest.TestCase],
    GesturesAndReadings.TestCase,  # pyright: ignore[reportUnknownMemberType]
)
