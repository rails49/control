"""Assembling the components on one bus and running a scenario to quiescence.

The wiring the CLI and the test suite share, so there is exactly one of it.
Nothing here is a contract — the components find each other by topic, not by
this module — but the order matters for the trace: the tap subscribes first,
so it sees every event, and the simulator last, so a boundary's cascade is
fully processed before it decides whether to advance (SYSTEM.md, the bus).
"""

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tc49.dispatcher import Dispatcher, FullRoute, Incremental, LockingStrategy
from tc49.driver import Driver
from tc49.lib.bus import Bus
from tc49.lib.layout import Layout, leaving_end
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
    """Train to the end it would leave by: what the scheduler takes of the
    same placement. Through `leaving_end`, so a train standing in a terminal
    block faces its one connected end however the document writes it (#145).
    """
    return {
        train: leaving_end(layout, f"{spec.at}.{spec.facing}")
        for train, spec in sorted(trains.items())
    }


@dataclass
class Assembly:
    """Everything wired on one bus, held so a caller can peek at live state."""

    bus: Bus
    dispatcher: Dispatcher
    simulator: Simulator
    layout: Layout
    roster: Roster
    k: int
    _out: io.StringIO

    @property
    def trace(self) -> str:
        return self._out.getvalue()


def assemble(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
) -> Assembly:
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)
    stood = placement(scenario.trains)
    Scheduler(bus, layout, facing(layout, scenario.trains), scenario.requests)
    dispatcher = Dispatcher(bus, layout, roster, stood, make_strategy(layout, k))
    Driver(bus)
    return Assembly(bus, dispatcher, Simulator(bus, stood), layout, roster, k, out)


def assemble_live(
    layout: Layout,
    roster: Roster,
    trains: dict[str, TrainSpec] | None = None,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    state: Path | None = None,
) -> Assembly:
    """The live-session wiring (#71): **a railroad and its roster**, and no
    timetable. That is the whole of what `tc49 live` builds a run from (#171)
    — a drawing, the trains the railroad owns, and a person who places them.
    The bridge a caller attaches to the bus is the only inbound path.

    Which sources a run has is configuration rather than a rule (ADR-0036), and
    a live run is given no timetable at all: a scenario's `at` is a boundary
    count, so releasing one into a ten-second wall clock would dump a
    timetable on an operator in the first minute.

    `trains` stands them before the first boundary instead, and is the
    harness's own: the suite's runs, and the baseline `tc49 live --scenario`'s
    replay is measured against. `tc49 live` itself passes none — a run an
    operator drives comes up with an empty layout and held, and the trains
    arrive as gestures (ADR-0039).

    `state` makes the session outlive the process (#123): the bus keeps its
    retained values there and each app adopts its own coming up, so placement
    and facing are the last session's rather than the seed's. The simulator
    keeps the steel's own memory beside it, which is its business and on no
    topic (ADR-0030).
    """
    stood = trains or {}
    bus = Bus(state)
    out = io.StringIO()
    TraceTap(bus, out)
    Scheduler(bus, layout, facing(layout, stood))
    dispatcher = Dispatcher(
        bus, layout, roster, placement(stood), make_strategy(layout, k)
    )
    Driver(bus)
    steel = None if state is None else placement_file(state)
    return Assembly(
        bus,
        dispatcher,
        Simulator(bus, placement(stood), steel),
        layout,
        roster,
        k,
        out,
    )


def run_scenario(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    tick_limit: int = 10_000,
) -> str:
    """Wire everything on one bus, run to quiescence, return the trace."""
    assembly = assemble(layout, roster, scenario, make_strategy, k)
    assembly.simulator.run(tick_limit)
    return assembly.trace
