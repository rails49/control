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
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.lib.scenario import Scenario
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


@dataclass
class Assembly:
    """Everything wired on one bus, held so a caller can peek at live state."""

    bus: Bus
    dispatcher: Dispatcher
    simulator: Simulator
    layout: Layout
    roster: Roster
    scenario: Scenario
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
    Scheduler(bus, layout, scenario)
    dispatcher = Dispatcher(bus, layout, roster, scenario, make_strategy(layout, k))
    Driver(bus)
    return Assembly(
        bus, dispatcher, Simulator(bus, scenario), layout, roster, scenario, k, out
    )


def assemble_live(
    layout: Layout,
    roster: Roster,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    state: Path | None = None,
) -> Assembly:
    """The live-session wiring (#71): the batch assembly with the timetable
    off. Which sources a session has is configuration rather than a rule
    (ADR-0036) — a scenario's `at` is still a boundary count, so releasing it
    into a two-second wall clock would dump a timetable on an operator in the
    first minute. The scenario contributes stock, placement, and facing; the
    bridge a caller attaches to the bus is the only inbound path.

    `state` makes the session outlive the process (#123): the bus keeps its
    retained values there and each app adopts its own coming up, so placement
    and facing are the last session's rather than the scenario's. The
    simulator keeps the steel's own memory beside it, which is its business
    and on no topic (ADR-0030).
    """
    bus = Bus(state)
    out = io.StringIO()
    TraceTap(bus, out)
    Scheduler(bus, layout, scenario, timetable=False)
    dispatcher = Dispatcher(bus, layout, roster, scenario, make_strategy(layout, k))
    Driver(bus)
    placement = None if state is None else placement_file(state)
    return Assembly(
        bus,
        dispatcher,
        Simulator(bus, scenario, placement),
        layout,
        roster,
        scenario,
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
