"""Assembling the components on one bus and running a scenario to quiescence.

The wiring the CLI and the test suite share, so there is exactly one of it.
Nothing here is a contract — the components find each other by topic, not by
this module — but the order matters for the trace: the tap subscribes first,
so it sees every event, and the simulator last, so a tick's cascade is fully
processed before it decides whether to advance (SYSTEM.md, the bus).
"""

import io
from collections.abc import Callable
from dataclasses import dataclass

from tc49.bus import Bus
from tc49.dispatch import Dispatcher
from tc49.driver import Driver
from tc49.layout import Layout
from tc49.locking import FullRoute, LockingStrategy
from tc49.scheduler import Scheduler
from tc49.sim import Simulator
from tc49.store import Scenario
from tc49.trace import TraceTap

StrategyFactory = Callable[[Layout, int], LockingStrategy]

DEFAULT_K = 2  # BENCHMARKS.md records its golden numbers at this budget


@dataclass
class Assembly:
    """Everything wired on one bus, held so a caller can peek at live state."""

    bus: Bus
    dispatcher: Dispatcher
    simulator: Simulator
    layout: Layout
    scenario: Scenario
    k: int
    _out: io.StringIO

    @property
    def trace(self) -> str:
        return self._out.getvalue()


def assemble(
    layout: Layout,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
) -> Assembly:
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)
    Scheduler(bus, scenario)
    dispatcher = Dispatcher(bus, layout, scenario, make_strategy(layout, k))
    Driver(bus)
    return Assembly(bus, dispatcher, Simulator(bus, scenario), layout, scenario, k, out)


def run_scenario(
    layout: Layout,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = DEFAULT_K,
    tick_limit: int = 10_000,
) -> str:
    """Wire everything on one bus, run to quiescence, return the trace."""
    assembly = assemble(layout, scenario, make_strategy, k)
    assembly.simulator.run(tick_limit)
    return assembly.trace
