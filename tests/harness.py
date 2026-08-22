"""The real assembly over the in-process bus, shared by the suite.

The wiring itself lives in `tc49.bench.runner`, so the suite and the benchmark CLI
drive an identical assembly; what is here is the loading and trace-reading
convenience the tests want.
"""

import json
from typing import Any

import pytest

from tc49.bench.runner import (
    Assembly,
    StrategyFactory,
    assemble,
    find_root,
    run_scenario,
)
from tc49.bench.runner import load as load_scenario
from tc49.lib.bus import Payload
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore

__all__ = [
    "ROOT",
    "RUN_WANTED",
    "Assembly",
    "StrategyFactory",
    "build",
    "events",
    "leaves",
    "load",
    "press",
    "run",
    "run_wanted",
    "runs",
    "ticks",
    "timetabled",
]

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


def press(assembly: Assembly, topic: str, payload: Payload) -> None:
    """A gesture as a page puts it on the bus, delivered where a person's
    press lands: between boundaries, and never inside a grant phase."""
    assembly.bus.publish(topic, payload)
    assembly.bus.drain()


def ticks(
    assembly: Assembly,
    count: int,
    at: dict[int, tuple[str, Payload]] | None = None,
) -> None:
    """`count` boundaries on one counter, with the gesture `at` keys pressed
    just before the boundary each is keyed to.

    The live loop rather than the batch one: it does not stop on quiescence,
    which is exactly what a test of a railroad standing still needs.
    """
    now = 0
    plan = at or {}

    def stop() -> bool:
        nonlocal now
        if now >= count:
            return True
        if now in plan:
            assembly.bus.publish(*plan[now])
        now += 1
        return False

    assembly.simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


RUN_WANTED = "tc49/ui/run_wanted"
"""The leaf a person's press of the run's one button lands on. Every
dispatcher suite that drives the run names it, so it is named here once."""


@pytest.fixture
def timetabled() -> Assembly:
    """`crossover-yard/meet` with its timetable on: three workings minted
    into the run, two at boundary 0 and freight_1's return at boundary 12."""
    return build(*load("crossover-yard/meet"))


def run_wanted(word: str) -> tuple[str, Payload]:
    """A press of the run's one button, as `ticks` plans one."""
    return (RUN_WANTED, {"run": word})


def leaves(assembly: Assembly, leaf: str) -> list[Payload]:
    """The trace's lines for one event leaf."""
    return events(assembly.trace, leaf)


def runs(assembly: Assembly) -> list[str]:
    """Every word `tc49/dispatch/state/run` took, in the order it took them."""
    return [str(line["run"]) for line in leaves(assembly, "run")]
