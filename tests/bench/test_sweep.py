"""The seeded generator and the fixed grid (#32, docs/bench/BENCHMARKS.md)."""

import json
from pathlib import Path

from tc49.bench.metrics import metrics
from tc49.bench.runner import STRATEGIES, run_scenario
from tc49.bench.sweep import (
    DEST_SIZES,
    K_VALUES,
    LAYOUT,
    SEEDS,
    STATION_TRACKS,
    STATIONS,
    TRAIN_COUNTS,
    WORKINGS,
    Workload,
    cells,
    generate,
    sweep,
)
from tc49.lib.layout import block_of
from tc49.lib.scenario import Scenario
from tests.harness import ROOT, load

SIDINGS = {"claro_4", "claro_5", "claro_6", "claro_7", "airolo_4"}


def every_workload() -> list[Workload]:
    return sorted(
        {workload for workload, _, _ in cells()},
        key=lambda w: (w.trains, w.dest, w.seed),
    )


def test_a_workload_tuple_names_one_exact_request_list() -> None:
    # The acceptance criterion, taken literally: the same tuple regenerates a
    # byte-identical request list. Only the seeded draw order makes that true,
    # so it is worth pinning rather than assuming.
    for workload in every_workload():
        first, second = generate(workload), generate(workload)
        assert first == second
        assert json.dumps([r.__dict__ for r in first.requests]) == json.dumps(
            [r.__dict__ for r in second.requests]
        )


def test_different_seeds_draw_different_workloads() -> None:
    drawn = {
        json.dumps(
            [r.__dict__ for r in generate(Workload(LAYOUT, 5, 3, 6, s)).requests]
        )
        for s in SEEDS
    }
    assert len(drawn) > 1, "the seed must actually reach the draws"


def test_only_a_first_working_states_a_departure_block() -> None:
    for workload in every_workload():
        scenario = generate(workload)
        seen: set[str] = set()
        for request in scenario.requests:
            if request.train in seen:
                # A chained working cannot state its block: where the previous
                # one parked the train is a dispatcher choice.
                assert request.depart in ("A", "B"), request
            else:
                assert request.depart == f"{scenario.trains[request.train].at}.{
                    request.depart[-1]
                }"
                seen.add(request.train)


def test_departure_ends_are_uniform_over_a_and_b() -> None:
    ends = [
        request.depart[-1]
        for workload in every_workload()
        for request in generate(workload).requests
    ]
    share = ends.count("A") / len(ends)
    assert 0.4 < share < 0.6, f"departure ends are skewed: {share:.2f} are 'A'"


def test_sidings_never_appear_as_generated_destinations() -> None:
    for workload in every_workload():
        scenario = generate(workload)
        assert {spec.at for spec in scenario.trains.values()} <= set(STATION_TRACKS)
        for request in scenario.requests:
            for arrival in request.arrivals:
                assert block_of(arrival) not in SIDINGS


def test_arrival_sets_are_the_swept_dest_size_at_the_other_station() -> None:
    for workload in every_workload():
        scenario = generate(workload)
        for request in scenario.requests:
            ends = sum(1 if "." in a else 2 for a in request.arrivals)
            assert ends == workload.dest
            station = request.arrivals[0].partition("_")[0]
            # Every entry names a track of one station, and it is the station
            # the train is not at — line workings run claro <-> airolo.
            assert all(a.startswith(station) for a in request.arrivals)
            if workload.dest == 6:
                assert set(request.arrivals) == set(STATIONS[station])


def test_no_drawn_workload_is_dead_at_boundary_zero() -> None:
    # #36: a draw where every train's arrival blocks are held by trains that
    # are themselves stuck (a head-on swap at its smallest) is unsatisfiable
    # by any dispatcher, so the generator must redraw it. Run at k = |dest|,
    # the full candidate budget, so the workload is what is measured rather
    # than the lexicographic bias of a truncated k. A run that moves and
    # *then* stalls is still allowed: a finished train parked across a route
    # is a legitimate finding, not a generator defect.
    layout, _ = load(f"{LAYOUT}/meet")
    for workload in every_workload():
        scenario = generate(workload)
        for locking in STRATEGIES:
            trace = run_scenario(layout, scenario, STRATEGIES[locking], workload.dest)
            m = metrics(trace)
            assert (
                m.completed or not m.stalled
            ), f"{scenario.name} under {locking} is dead at boundary 0"


def test_every_request_arrives_at_boundary_zero() -> None:
    for workload in every_workload():
        assert all(r.at == 0 for r in generate(workload).requests)


def test_generated_workloads_load_as_real_scenarios() -> None:
    layout, _ = load(f"{LAYOUT}/meet")
    for workload in every_workload():
        scenario = generate(workload)
        assert isinstance(scenario, Scenario)
        assert len(scenario.trains) == workload.trains
        assert len(scenario.requests) == workload.trains * workload.workings
        for train in scenario.trains.values():
            assert train.at in layout.blocks
            assert train.length <= min(
                layout.blocks[t] for t in STATION_TRACKS
            ), "every train must fit every station track"


def test_the_grid_matches_benchmarks_md_with_dead_cells_skipped() -> None:
    grid = list(cells())
    axes = {(w.trains, w.dest, w.seed, k, locking) for w, k, locking in grid}
    assert len(grid) == len(axes), "the grid must not repeat a cell"

    for trains, dest, seed, k, _ in axes:
        assert trains in TRAIN_COUNTS
        assert dest in DEST_SIZES
        assert seed in SEEDS
        assert k in K_VALUES
        assert k <= dest, "k > |dest| is a dead cell and is not swept"

    # 1 + 2 + 4 live k values at |dest| 1, 2 and 6, times two strategies.
    per_workload = 2 * sum(len([k for k in K_VALUES if k <= d]) for d in DEST_SIZES)
    assert len(grid) == len(TRAIN_COUNTS) * len(SEEDS) * per_workload
    assert {w.workings for w, _, _ in grid} == {WORKINGS}


def test_sweep_writes_one_jsonl_row_per_run(tmp_path: Path) -> None:
    # A slice of the grid, so the test stays fast; `tc49 sweep` runs all of it.
    written = _sweep_subset(tmp_path)
    rows = [
        json.loads(line) for line in (tmp_path / "sweep.jsonl").read_text().splitlines()
    ]
    assert len(rows) == written
    for row in rows:
        assert set(row) == {
            "layout",
            "trains",
            "workings",
            "dest",
            "seed",
            "k",
            "locking",
            "status",
            "makespan",
            "boundaries",
            "completed",
            "rejected",
            "mean_latency",
            "max_latency",
            "mean_utilization",
            "mean_parallelism",
            "stalls",
        }
        assert row["status"] in ("ok", "stalled", "rejected")
        # A stalled row carries its status and its diagnosis, and no makespan.
        if row["status"] == "stalled":
            assert row["makespan"] is None
            assert row["stalls"] and all(
                set(s) == {"id", "reason", "resource", "holder", "candidates_blocked"}
                for s in row["stalls"]
            )


def _sweep_subset(tmp_path: Path, trains: int = 2) -> int:
    """Run the grid for one train count by narrowing the axis in place."""
    import tc49.bench.sweep as module

    original = module.TRAIN_COUNTS
    module.TRAIN_COUNTS = (trains,)
    try:
        return sweep(out_dir=tmp_path, root=ROOT)
    finally:
        module.TRAIN_COUNTS = original
