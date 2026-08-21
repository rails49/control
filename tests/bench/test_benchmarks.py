"""Golden numbers for the named scenarios (#31, docs/bench/BENCHMARKS.md).

Golden numbers are viable here, which they usually are not, for a specific
reason: every metric is in **boundaries**, not wall-clock, and the
determinism property already guarantees byte-identical traces. A makespan is exactly
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

from tc49.bench.cli import bench
from tc49.bench.metrics import Metrics, metrics
from tc49.bench.runner import DEFAULT_K, STRATEGIES, run_scenario
from tc49.bench.sweep import ARRIVALS, station_of
from tc49.lib.layout import block_of
from tc49.lib.scenario import RequestSpec, Scenario
from tests.harness import ROOT, load

EXPECTED = ROOT / "benchmarks" / "expected"

# Both railroads. `gotthard` is the one on the bench and carries the claims
# below; `gotthard-v0` is frozen and carries only numbers, so that the evidence
# ADR-0006, ADR-0012 and ADR-0029 cite stays reproducible rather than merely
# archived (#161). If a v0 golden ever moves, the dispatcher changed — not the
# railroad.
NAMED_SCENARIOS = [
    "crossover-yard/meet",
    "gotthard/meet",
    "gotthard/saturation",
    "gotthard/obstacle",
    "gotthard/flexibility",
    "gotthard-v0/meet",
    "gotthard-v0/saturation",
    "gotthard-v0/obstacle",
    "gotthard-v0/flexibility",
]


def summary(m: Metrics) -> dict[str, object]:
    """The golden view of a run: throughput, and why it stopped if it stalled.

    Floats are rounded so the file diffs on a real change rather than on a
    repr, and the rounding is far finer than any regression worth catching.
    """
    return {
        "status": m.status,
        "makespan": m.makespan,
        "boundaries": m.boundaries,
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


def test_batch_trace_is_pinned_byte_identical() -> None:
    """The batch loop is the research harness's ground truth: live mode (#69)
    and everything after must leave its traces byte-identical, so one full
    trace is pinned alongside the golden numbers. Regenerate like the goldens,
    with TC49_REGEN_GOLDENS=1, and read the diff before committing it."""
    layout, scenario = load("crossover-yard/meet")
    trace = run_scenario(layout, scenario)
    path = EXPECTED / "crossover-yard-meet.trace.jsonl"
    if os.environ.get("TC49_REGEN_GOLDENS"):
        path.write_text(trace)
    assert path.read_text() == trace


def test_a_two_block_route_leaves_incremental_nothing_to_withhold() -> None:
    """`gotthard/meet` no longer splits, and the reason is worth pinning.

    Its routes are two blocks long, and an increment plus the one asked for
    ahead of it (ADR-0029) is exactly two blocks — so `Incremental` locks the
    whole route at the first grant and *is* `FullRoute` here. `south` takes
    the airolo transit at boundary 1 and holds it until it crosses, `north` is
    refused `transit_conflict` twice, and only then falls through to the
    yellow. That is the cost ADR-0026 named as holding track speculatively,
    seen at the smallest scale that can show it.

    The strategies part company again as soon as a route is longer than the
    lookahead; `gotthard/saturation` below is where that is asserted. If this
    test ever fails, the lookahead or the route length changed, and the two
    should be compared afresh rather than the numbers simply re-recorded.
    """
    results = {name: m for name, (_, m) in bench("gotthard/meet").items()}
    baseline, incremental = results["FullRoute"], results["Incremental"]
    assert incremental.makespan is not None and baseline.makespan is not None
    assert incremental.makespan == baseline.makespan
    assert incremental.mean_parallelism == baseline.mean_parallelism


def test_incremental_drains_gotthard_saturation_faster() -> None:
    """The headline makespan gap: both strategies complete all eighteen
    workings, and `Incremental` does it in materially fewer boundaries.

    Re-derived on the railroad on the bench (#161), where the workload is six
    trains rather than five because the station tracks are seven rather than
    six. The gap did not merely survive the move — it widened, from 24 vs 20
    boundaries on `gotthard-v0` to 25 vs 19 here.
    """
    results = {name: m for name, (_, m) in bench("gotthard/saturation").items()}
    for m in results.values():
        assert m.status == "ok"
        assert len(m.completed) == 18
    baseline, incremental = results["FullRoute"], results["Incremental"]
    assert incremental.makespan is not None and baseline.makespan is not None
    assert incremental.makespan < baseline.makespan
    assert incremental.max_latency is not None and baseline.max_latency is not None
    assert incremental.max_latency < baseline.max_latency


def test_saturation_widened_to_six_arrival_ends_drains_at_default_k() -> None:
    """The `|dest| = 6, k = 2` criterion of #33 and #34, met in two steps.

    Before congestion-aware costing (#33) the widened workload stalled
    outright — every train tried `claro_1` then `claro_2`, both occupied,
    and the rotation never started (0 of 15 workings, dead at boundary 1).
    Costing started the rotation but left it at 11 of 15: the last airolo
    slots went to older trains parking there for good, because no candidate
    ordering can stop an older pending request from taking a free slot.
    That is queue order, and the aging rule (#34) finishes the job — the
    starved through-traffic outranks the fresher final parks once its
    refusals accumulate, and the workload drains under both strategies.
    The committed scenario stays at `|dest| = 2`, the column the sweep
    reads every other against.

    That account is `gotthard-v0`'s history and its counts are v0's. What is
    asserted is the criterion itself, on the railroad on the bench: widened to
    every line-facing end, the workload still drains at the default `k`.

    Two of the eighteen workings are the track-3 shunt, `C3b` to `C3a`, which
    the rotation cannot avoid — Claro has four station tracks and Airolo three,
    so a cycle through all seven has one Claro-to-Claro hop. A shunt has no
    `|dest|` axis: it arrives at `C3a.A`, an end that faces only the other half
    of track 3 and is not a station-to-station arrival end at all. Widening it
    would replace it with ends it cannot mean, turning the shunt into a line
    working and dissolving the rotation this test is about. So the sixteen line
    workings widen and the two shunts are left alone.
    """
    layout, scenario = load("gotthard/saturation")
    line_facing = {end for tracks in ARRIVALS.values() for t in tracks for end in t}

    def widen(req: RequestSpec) -> RequestSpec:
        resolved = {
            end
            for arrival in req.arrivals
            for end in (
                (arrival,) if "." in arrival else (f"{arrival}.A", f"{arrival}.B")
            )
        }
        if not resolved <= line_facing:
            return req  # a shunt; see above
        station = station_of(block_of(req.arrivals[0]))
        return RequestSpec(
            req.train,
            req.depart,
            tuple(end for t in ARRIVALS[station] for end in t),
            req.at,
        )

    widened = Scenario(
        scenario.name,
        scenario.layout,
        scenario.trains,
        tuple(widen(req) for req in scenario.requests),
    )
    assert sum(a is not b for a, b in zip(scenario.requests, widened.requests)) == 16
    for strategy in STRATEGIES.values():
        trace = run_scenario(layout, widened, strategy, DEFAULT_K)
        m = metrics(trace)
        assert m.status == "ok"
        assert len(m.completed) == 18


def test_the_obstacle_scenario_stalls_and_names_the_obstacle() -> None:
    """`stranded` departs `C3b.A`, which blue 1 alone serves, so the departure
    end fixes the line and the widest arrival set on the layout changes
    nothing. Both strategies stall, and both name the same block and the same
    train.

    Track 3's east end is `C3b.A` and there is no other: `C3a` has no east end,
    and from `C3a.B` the yellow is available, which would dissolve the premise.
    """
    for _, m in bench("gotthard/obstacle").values():
        assert m.status == "stalled"
        assert m.makespan is None  # excluded from makespan aggregates
        [stall] = m.stalls
        assert stall.id == "stranded-1"
        assert (stall.resource, stall.holder) == ("CE1", "stock")


def test_flexibility_is_the_difference_between_stalling_and_finishing() -> None:
    """Two Airolo -> Claro workings against one obstruction, differing only in
    how many arrival ends each names."""
    for _, m in bench("gotthard/flexibility").values():
        assert m.status == "stalled"
        assert m.completed == ("flexible-1",)  # |dest| = 6 finishes
        [stall] = m.stalls
        assert stall.id == "fixed-1"  # |dest| = 1 does not
        assert (stall.resource, stall.holder) == ("C2", "resident")
