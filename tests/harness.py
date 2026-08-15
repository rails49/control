"""The real assembly over the in-process bus, shared by the suite.

The wiring itself lives in `tc49.runner`, so the suite and the benchmark CLI
drive an identical assembly; what is here is the loading and trace-reading
convenience the tests want.
"""

import json
from pathlib import Path
from typing import Any

from tc49.layout import Layout
from tc49.runner import Assembly, StrategyFactory, assemble, run_scenario
from tc49.store import AssetStore, Scenario

__all__ = ["ROOT", "Assembly", "StrategyFactory", "build", "events", "load", "run"]

ROOT = Path(__file__).parent.parent

build = assemble
run = run_scenario


def load(scenario_id: str) -> tuple[Layout, Scenario]:
    store = AssetStore(ROOT)
    scenario = store.get(scenario_id)
    assert isinstance(scenario, Scenario)
    layout = store.get(scenario.layout)
    assert isinstance(layout, Layout)
    return layout, scenario


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
