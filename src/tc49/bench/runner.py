"""Assembling the components on one bus and running a scenario to quiescence.

The wiring the CLI and the test suite share, so there is exactly one of it.
Nothing here is a contract — the components find each other by topic, not by
this module — but the order matters for the trace: the tap subscribes first,
so it sees every event (SYSTEM.md, the bus).

A live run is built on **one** binding of the layout interface: the simulator,
or `layout` with the `dccex` translator under it where a command station is
named (#314, ADR-0030). The branch is the last step of `assemble_live` and the
one loop `Assembly.run` picks; everything above it is wired the same either
way and none of it knows which it got.
"""

import asyncio
import contextlib
import io
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from tc49.bench.detector import HandFed
from tc49.dccex import DccEx
from tc49.dispatcher import Dispatcher, FullRoute, Incremental, LockingStrategy
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.lib.bus import Bus
from tc49.lib.clock import Clock
from tc49.lib.layout import Layout, connected_facing
from tc49.lib.roster import Roster
from tc49.lib.scenario import Scenario, TrainSpec
from tc49.lib.trace import TraceTap
from tc49.scheduler import Scheduler
from tc49.simulator import Simulator, placement_file
from tc49.store import AssetStore

StrategyFactory = Callable[[Layout, int], LockingStrategy]

DEFAULT_K = 2  # BENCHMARKS.md records its golden numbers at this budget

STRATEGIES: dict[str, StrategyFactory] = {
    "FullRoute": FullRoute,
    "Incremental": Incremental,
}


def find_root(start: Path | None = None) -> Path:
    """The repo root: the nearest ancestor holding `layouts/`.

    The railroads and the scenarios are repo data, not package data — the
    wheel ships `src/tc49` alone — so the benchmark commands only mean
    anything inside a checkout. Searching for the data rather than counting
    `..` from `__file__` makes that work from any subdirectory and fail with
    a sentence instead of a `FileNotFoundError` on a path nobody wrote.
    """
    for candidate in (start or Path(__file__)).resolve().parents:
        if (candidate / "layouts").is_dir():
            return candidate
    raise FileNotFoundError(
        "no 'layouts/' directory in any parent — `tc49 bench` and `tc49 sweep`"
        " read the railroads and scenarios from a checkout of the repository,"
        " and are not usable from an installed wheel"
    )


def load(store: AssetStore, scenario_id: str) -> tuple[Layout, Roster, Scenario]:
    """A scenario, and the layout and roster of the railroad it names — which
    is what assembling wants. The three are one railroad's: the drawing it
    derives from, the trains it owns, and where this run stands them
    (ADR-0039)."""
    scenario = store.get(scenario_id)
    assert isinstance(scenario, Scenario)
    layout = store.get(scenario.layout)
    assert isinstance(layout, Layout)
    return layout, store.roster(scenario.layout), scenario


def railroad(store: AssetStore, name: str) -> tuple[Layout, Roster]:
    """A railroad: the layout its drawing derives to, and the trains it owns.

    The whole of what a live run is built from (#171). A drawing that does not
    derive raises `ValueError` here, where a session can refuse the name on
    the joining client's own thread instead of taking a running railroad down
    with it; a name the store answers with anything but a layout is not a
    railroad's, and reads as one that is not there.
    """
    layout = store.get(name)
    if not isinstance(layout, Layout):
        raise FileNotFoundError(f"no railroad '{name}'")
    return layout, store.roster(name)


def placement(trains: dict[str, TrainSpec]) -> dict[str, str]:
    """Train to the block it starts in: what the dispatcher and the simulator
    take of a document's placement. Neither reads facing (ADR-0019)."""
    return {train: spec.at for train, spec in trains.items()}


def facing(layout: Layout, trains: dict[str, TrainSpec]) -> dict[str, str]:
    """Train to the run it would make across its block: what the scheduler
    takes of the same placement, the document's bare `A-to-B` qualified by the
    block it is written beside. Through `connected_facing`, so a train
    standing in a terminal block is turned off the wall however the document
    writes it (#145).
    """
    return {
        train: connected_facing(layout, f"{spec.at}.{spec.facing}")
        for train, spec in sorted(trains.items())
    }


@dataclass
class Assembly:
    """Everything wired on one bus, held so a caller can peek at live state.

    **One binding of the layout interface, and never both** (ADR-0030): a run
    holds either a `simulator` or the `interface`/`dccex` pair that drives
    steel, and the fields say which by being there. Nothing above them knows
    the difference, and neither one knows the other exists.
    """

    bus: Bus
    dispatcher: Dispatcher
    simulator: Simulator | None
    layout: Layout
    roster: Roster
    k: int
    _out: io.StringIO
    clock: Clock
    # The physical binding, both present or both absent: the core app that
    # answers the commands, and the translator that puts its device rows on a
    # command station (ADR-0043).
    interface: LayoutInterface | None = None
    dccex: DccEx | None = None
    # The hand-fed detector, where a physical run was given an input to read:
    # nothing publishes a level on steel yet, so a person types them (#315).
    # Only ever beside the pair above — a simulated run has its own sensors
    # and must not grow a second source of them.
    detector: HandFed | None = None

    @property
    def trace(self) -> str:
        return self._out.getvalue()

    @property
    def simulation(self) -> Simulator:
        """The simulator this run is bound to.

        What a caller that wants the engine itself goes through: the batch
        loop, and a live loop a test paces turn by turn rather than on a wall
        clock. It asserts rather than answering nothing, because there is no
        second thing to do — a caller reaching here has already decided which
        binding it is looking at.
        """
        assert self.simulator is not None, "this run has no simulator"
        return self.simulator

    def run(
        self,
        period_s: float,
        sleep: Callable[[float], None] = time.sleep,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        """Work this run on a wall clock until `stop`, whichever binding it
        was built on.

        Two loops with a signature in common and **nothing else** — no
        protocol over them, deliberately. The simulator's is a discrete-event
        queue slept on a wall clock; the physical one is asyncio owning a TCP
        session to a command station. An interface spanning the two would send
        a reader looking for simulation behind something that is not there
        (ADR-0030).

        `sleep` is the simulator branch's, and is how a session cuts a pending
        transit delay short when the panel names another railroad. The
        physical branch waits on its own loop instead: a session with a
        station switches to no other railroad, the station being one physical
        railroad.
        """
        if self.simulator is not None:
            self.simulator.run_live(period_s, sleep=sleep, stop=stop)
            return
        asyncio.run(self._driven(period_s, stop))

    async def _driven(self, period_s: float, stop: Callable[[], bool]) -> None:
        """The physical run: the link to the command station and the pacer
        beside it, and the railroad stood down when either ends.

        **asyncio owns this branch and only this branch.** `DccEx._send`
        writes to an `asyncio.StreamWriter` from inside a bus subscriber, so
        whichever thread drains the bus is the thread that writes to the
        station. With the loop owning the process every subscriber runs on the
        loop thread and that write is already where it belongs; a daemon
        thread under a sync owner would mean marshalling a cross-thread write
        that does not exist today.

        Ctrl-C arrives here as a cancellation, `asyncio.run` cancelling the
        task it is waiting on, so the stand-down is in a `finally` and the
        interrupt goes on out to the command that catches it. Standing down
        comes **before** the link is let go: cancelling `DccEx.run` closes the
        writer, and zeros sent after that have nowhere to go.
        """
        dccex, interface = self.dccex, self.interface
        assert dccex is not None and interface is not None, "this run drives nothing"
        if self.detector is not None:
            # Reading starts with the run and not with the assembly: a line
            # typed at a session that is not running yet would sit in a queue
            # nothing drains, and every construction but a session's reads
            # nothing at all.
            self.detector.opens()
        link = asyncio.create_task(dccex.run())
        try:
            await self._pace(interface, period_s, stop)
        finally:
            await dccex.shutdown()
            link.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await link

    async def _pace(
        self, interface: LayoutInterface, period_s: float, stop: Callable[[], bool]
    ) -> None:
        """A turn of the physical loop: the three jobs the simulator's does
        besides popping events it scheduled itself, and the readings a person
        typed since the last one.

        Advance the run clock to wall time — steel keeps its own time and
        nothing else here moves the clock. Publish whatever was typed, which
        is where a detector's levels come from until a camera publishes them
        (#315): a line typed between two turns is seen on this one, delivered
        by this turn's drain and settled on a later one, exactly as a level
        that arrived off a wire between turns would be. Settle:
        `LayoutInterface.settle()` acts on a level that has stood long enough
        and **nothing schedules it**, so a session that never called it would
        never notice an arrival. Drain, which is what carries a gesture from a
        client's handler thread into the run.

        `period_s` is what bounds the resolution: 0.1 s against 300 ms of
        settling has a settled level acted on between 0.3 s and 0.4 s after
        it stood.
        """
        started = time.monotonic()
        self.bus.drain()  # the startup cascade, as the other loop opens with
        while not stop():
            await asyncio.sleep(period_s)
            self.clock.advance(time.monotonic() - started)
            if self.detector is not None:
                self.detector.typed()
            interface.settle()
            self.bus.drain()


def assemble(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
) -> Assembly:
    clock = Clock()
    bus = Bus(clock)
    out = io.StringIO()
    TraceTap(bus, out, clock)
    stood = placement(scenario.trains)
    Scheduler(bus, layout, facing(layout, scenario.trains), scenario.requests)
    dispatcher = Dispatcher(bus, layout, roster, stood, make_strategy(layout, k))
    Driver(bus)
    return Assembly(
        bus,
        dispatcher,
        Simulator(bus, layout, clock, stood),
        layout,
        roster,
        k,
        out,
        clock,
    )


def assemble_live(
    layout: Layout,
    roster: Roster,
    trains: dict[str, TrainSpec] | None = None,
    make_strategy: StrategyFactory = Incremental,
    k: int = DEFAULT_K,
    state: Path | None = None,
    station: tuple[str, int] | None = None,
    startup: Path | None = None,
    readings: TextIO | None = None,
    reports: TextIO | None = None,
) -> Assembly:
    """The live-session wiring (#71): **a railroad and its roster**, and no
    timetable. That is the whole of what `tc49 live` builds a run from (#171)
    — a drawing, the trains the railroad owns, and a person who places them.
    The bridge a caller attaches to the bus is the only inbound path.

    Which sources a run has is configuration rather than a rule (ADR-0036), and
    a live run is given no timetable at all: a scenario is the harness's file
    format, and `tc49 live --scenario` replays one as gestures instead.

    `trains` stands them before anything runs instead, and is the
    harness's own: the suite's runs, and the baseline `tc49 live --scenario`'s
    replay is measured against. `tc49 live` itself passes none — a run an
    operator drives comes up with an empty layout and held, and the trains
    arrive as gestures (ADR-0039).

    Locking is **incremental** here, where `assemble` keeps the `FullRoute`
    baseline (#165). It is what the panel's two colours mean: an increment
    is the next transit with the block beyond it, so green creeps along a
    cyan path and its length says how far the train may go (ui/PANEL.md).
    Claiming a whole route up front is a measurement baseline, not the
    behaviour to hand an operator on a shared railroad.

    `state` makes the session outlive the process (#123): the bus keeps its
    retained values there and each app adopts its own coming up, so placement
    and facing are the last session's rather than the seed's. The simulator
    keeps the steel's own memory beside it, which is its business and on no
    topic (ADR-0030).

    `station` is where a command station is served, `host` and `port`, and its
    presence is what puts the **physical binding** where the simulator would
    be: `LayoutInterface` answering the commands and `DccEx` putting its
    device rows on the station (#314, ADR-0043). A run has one binding of the
    layout interface and neither knows the other exists, so no simulator is
    constructed in this mode and nothing branches on which mode it is past
    this line. `startup` is the file of raw station commands `DccEx` sends on
    powering the rails — the per-district trip currents (docs/dccex/README.md)
    — and is the station's to carry, so it means nothing without one.

    `readings` is where a person types a detector's levels and `reports` is
    where a line that is not one is said (#315). Nothing publishes
    `device/sensor` on steel yet, so a physical run given an input reads it and
    one given none is blind — which is every construction but a session's, the
    suite included. It is the station's to carry too: a simulated run has its
    own sensors, and a second source of them would be two things saying what
    one block end reads.

    One function and not two, branching only at the last step: a sibling would
    duplicate the scheduler, dispatcher and driver wiring above, or need a
    third helper to hold this docstring. `bench` is the one place in the tree
    allowed to wire apps to each other.
    """
    document = trains or {}
    stood = placement(document)
    clock = Clock()
    bus = Bus(clock, state)
    out = io.StringIO()
    TraceTap(bus, out, clock)
    Scheduler(bus, layout, facing(layout, document))
    dispatcher = Dispatcher(bus, layout, roster, stood, make_strategy(layout, k))
    Driver(bus)
    simulator: Simulator | None = None
    interface: LayoutInterface | None = None
    dccex: DccEx | None = None
    detector: HandFed | None = None
    if station is None:
        # The steel's own memory, which the physical branch has no use for:
        # there the trains really are still standing where they were left.
        steel = None if state is None else placement_file(state)
        simulator = Simulator(bus, layout, clock, stood, steel)
    else:
        # The interface first, so the dark railroad it opens by wanting is
        # already retained when the translator subscribes and is the first
        # thing a fresh link is handed.
        interface = LayoutInterface(bus, layout, roster, clock)
        dccex = DccEx(bus, station[0], station[1], startup=startup)
        if readings is not None:
            detector = HandFed(bus, layout, readings, reports or sys.stdout)
    return Assembly(
        bus,
        dispatcher,
        simulator,
        layout,
        roster,
        k,
        out,
        clock,
        interface,
        dccex,
        detector,
    )


def run_scenario(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    event_limit: int = 100_000,
) -> str:
    """Wire everything on one bus, run to quiescence, return the trace."""
    assembly = assemble(layout, roster, scenario, make_strategy, k)
    assembly.simulation.run(event_limit)
    return assembly.trace
