"""Golden numbers for the named scenarios (#31, docs/BENCHMARKS.md).

Golden numbers are viable here, which they usually are not, for a specific
reason: every metric is in **ticks**, not wall-clock, and the determinism
property already guarantees byte-identical traces. A makespan is exactly
reproducible on any machine, so a throughput regression fails CI with a
readable diff instead of going unnoticed.

The goldens were recorded from the first run made *after* the Hypothesis
properties (#28) and the boundary-condition tests (#29) passed, at the
default `k = 2`, and the comparison table was reviewed by the owner before
they were committed. Any later intentional change to a golden states its
reason in the commit.

To re-record after an intended change:

    TC49_REGEN_GOLDENS=1 uv run pytest tests/test_benchmarks.py

then read the diff before committing it.
"""

import json
import os
from pathlib import Path

import pytest

from tc49.cli import bench
from tc49.metrics import Metrics
from tc49.runner import DEFAULT_K
from tests.harness import ROOT

EXPECTED = ROOT / "benchmarks" / "expected"

NAMED_SCENARIOS = [
    "crossover-yard/meet",
    "gotthard/meet",
    "gotthard/saturation",
    "gotthard/obstacle",
    "gotthard/flexibility",
]


def summary(m: Metrics) -> dict[str, object]:
    """The golden view of a run: throughput, and why it stopped if it stalled.

    Floats are rounded so the file diffs on a real change rather than on a
    repr, and the rounding is far finer than any regression worth catching.
    """
    return {
        "status": m.status,
        "makespan": m.makespan,
        "ticks": m.ticks,
        "completed": len(m.completed),
        "rejected": len(m.rejected),
        "mean_latency": None if m.mean_latency is None else round(m.mean_latency, 4),
        "max_latency": m.max_latency,
        "mean_utilization": round(m.mean_utilization, 4),
        "mean_parallelism": round(m.mean_parallelism, 4),
        "stalls": [
            {
                "id": s.id,
                "reason": s.reason,
                "resource": s.resource,
                "holder": s.holder,
                "candidates_blocked": s.candidates_blocked,
            }
            for s in m.stalls
        ],
    }


def record(scenario_id: str, k: int = DEFAULT_K) -> dict[str, object]:
    return {
        "scenario": scenario_id,
        "k": k,
        "strategies": {
            name: summary(m) for name, (_, m) in bench(scenario_id, k).items()
        },
    }


def golden_path(scenario_id: str) -> Path:
    return EXPECTED / f"{scenario_id.replace('/', '-')}.json"


@pytest.mark.parametrize("scenario_id", NAMED_SCENARIOS)
def test_named_scenario_matches_its_golden_numbers(scenario_id: str) -> None:
    measured = record(scenario_id)
    path = golden_path(scenario_id)
    if os.environ.get("TC49_REGEN_GOLDENS"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(measured, indent=2) + "\n")
    assert json.loads(path.read_text()) == measured


def test_incremental_splits_the_gotthard_meet_across_two_lines() -> None:
    """The story `gotthard/meet` exists to tell, asserted rather than quoted.

    `FullRoute` locks `south`'s whole route over blue 2 and `north` ends up
    serialised behind it on the same line. `Incremental` locks only the first
    increment, so `north`'s launch finds blue 2 held, falls through to its
    second candidate, and takes the yellow — the two trains then run
    simultaneously and the run is two ticks shorter.
    """
    results = {name: m for name, (_, m) in bench("gotthard/meet").items()}
    assert results["Incremental"].makespan is not None
    assert results["FullRoute"].makespan is not None
    assert results["Incremental"].makespan < results["FullRoute"].makespan
    assert (
        results["Incremental"].mean_parallelism > results["FullRoute"].mean_parallelism
    )


def test_incremental_drains_gotthard_saturation_faster() -> None:
    """The headline makespan gap: both strategies complete all fifteen
    workings, and `Incremental` does it in materially fewer ticks."""
    results = {name: m for name, (_, m) in bench("gotthard/saturation").items()}
    for m in results.values():
        assert m.status == "ok"
        assert len(m.completed) == 15
    baseline, incremental = results["FullRoute"], results["Incremental"]
    assert incremental.makespan is not None and baseline.makespan is not None
    assert incremental.makespan < baseline.makespan
    assert incremental.max_latency is not None and baseline.max_latency is not None
    assert incremental.max_latency < baseline.max_latency


def test_the_obstacle_scenario_stalls_and_names_the_obstacle() -> None:
    """`stranded` departs claro_3.B, which blue 1 alone serves, so the
    departure end fixes the line and the widest arrival set on the layout
    changes nothing. Both strategies stall, and both name the same block and
    the same train."""
    for _, m in bench("gotthard/obstacle").values():
        assert m.status == "stalled"
        assert m.makespan is None  # excluded from makespan aggregates
        [stall] = m.stalls
        assert stall.id == "stranded-1"
        assert (stall.resource, stall.holder) == ("line_blue_1", "stock")


def test_flexibility_is_the_difference_between_stalling_and_finishing() -> None:
    """Two Airolo -> Claro workings against one obstruction, differing only in
    how many arrival ends each names."""
    for _, m in bench("gotthard/flexibility").values():
        assert m.status == "stalled"
        assert m.completed == ("flexible-1",)  # |dest| = 6 finishes
        [stall] = m.stalls
        assert stall.id == "fixed-1"  # |dest| = 1 does not
        assert (stall.resource, stall.holder) == ("claro_2", "resident")
