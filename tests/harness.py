"""The real assembly over the in-process bus, shared by the suite.

The wiring itself lives in `tc49.bench.runner`, so the suite and the benchmark CLI
drive an identical assembly; what is here is the loading and trace-reading
convenience the tests want.
"""

import json
from typing import Any

from tc49.bench.runner import (
    Assembly,
    StrategyFactory,
    assemble,
    find_root,
    run_scenario,
)
from tc49.bench.runner import load as load_scenario
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore

__all__ = ["ROOT", "Assembly", "StrategyFactory", "build", "events", "load", "run"]

ROOT = find_root()  # one definition of where the railroads live

build = assemble
run = run_scenario


def load(scenario_id: str) -> tuple[Layout, Scenario]:
    """The wiring module's loader against the one root the suite uses."""
    return load_scenario(AssetStore(ROOT), scenario_id)


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
