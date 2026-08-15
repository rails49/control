"""The real assembly over the in-process bus, shared by the suite."""

import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tc49.bus import Bus
from tc49.dispatch import Dispatcher
from tc49.driver import Driver
from tc49.layout import Layout
from tc49.locking import FullRoute, LockingStrategy
from tc49.scheduler import Scheduler
from tc49.sim import Simulator
from tc49.store import AssetStore, Scenario
from tc49.trace import TraceTap

ROOT = Path(__file__).parent.parent

StrategyFactory = Callable[[Layout, int], LockingStrategy]


def load(scenario_id: str) -> tuple[Layout, Scenario]:
    store = AssetStore(ROOT)
    scenario = store.get(scenario_id)
    assert isinstance(scenario, Scenario)
    layout = store.get(scenario.layout)
    assert isinstance(layout, Layout)
    return layout, scenario


def run(
    layout: Layout,
    scenario: Scenario,
    make_strategy: StrategyFactory = FullRoute,
    k: int = 2,
) -> str:
    """Wire everything on one bus, run to quiescence, return the trace."""
    bus = Bus()
    out = io.StringIO()
    TraceTap(bus, out)
    Scheduler(bus, scenario)
    Dispatcher(bus, layout, scenario, make_strategy(layout, k))
    Driver(bus)
    Simulator(bus, scenario).run()
    return out.getvalue()


def events(
    trace: str, leaf: str | None = None, rid: str | None = None
) -> list[dict[str, Any]]:
    """Parsed trace lines, optionally filtered by event leaf and request id."""
    lines = [json.loads(line) for line in trace.splitlines()]
    return [
        line
        for line in lines
        if (leaf is None or line["event"] == leaf)
        and (rid is None or line.get("id") == rid)
    ]
