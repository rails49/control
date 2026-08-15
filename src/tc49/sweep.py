"""`tc49 sweep`: the seeded workload generator and the fixed grid.

The grid of BENCHMARKS.md is the research design, not a knob, so this takes
no arguments and that page is its single source of truth. One JSONL row per
run — every axis plus every metric — goes to a gitignored output directory;
no aggregation is baked in, because sweep output is a research finding
rather than a contract and committing it would churn.

Everything a workload contains is drawn from a single seeded RNG in one
fixed order, so a `(layout, trains, workings, |dest|, seed)` tuple names one
exact workload and regenerates it byte for byte. `k` and the locking
strategy are *run* axes, not workload axes: the same request list is run
under every cell of the rest of the grid.
"""

import json
import random
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tc49.layout import Layout
from tc49.metrics import metrics
from tc49.runner import STRATEGIES, find_root, run_scenario
from tc49.store import AssetStore, RequestSpec, Scenario, TrainSpec

LAYOUT = "gotthard"

# The two stations' through tracks. Sidings are deliberately absent: every
# generated request stays a long run that faces the line choice, and a
# uniform-over-all-blocks generator would dilute the one signal the sweep
# exists to find (BENCHMARKS.md, workloads).
STATIONS: dict[str, tuple[str, ...]] = {
    "claro": ("claro_1", "claro_2", "claro_3"),
    "airolo": ("airolo_1", "airolo_2", "airolo_3"),
}
STATION_TRACKS = tuple(track for tracks in STATIONS.values() for track in tracks)

# The sweep axes, exactly as BENCHMARKS.md fixes them.
TRAIN_COUNTS = (2, 3, 4, 5)
WORKINGS = 3
SEEDS = tuple(range(10))
DEST_SIZES = (1, 2, 6)
K_VALUES = (1, 2, 4, 6)


def train_length(index: int) -> int:
    """Fixed per train id so the fit check is deterministic; any length that
    fits every station track will do, and Airolo's 1200 is the tightest."""
    return 600 + 100 * index


def station_of(track: str) -> str:
    return track.partition("_")[0]


def other_station(track: str) -> str:
    return "airolo" if station_of(track) == "claro" else "claro"


@dataclass(frozen=True)
class Workload:
    """The axes that name one exact request list."""

    layout: str
    trains: int
    workings: int
    dest: int
    seed: int


def generate(workload: Workload) -> Scenario:
    """The generator of BENCHMARKS.md, drawing in its documented order."""
    rng = random.Random(workload.seed)

    # 1. Placement — distinct station tracks, one train each.
    placements = rng.sample(STATION_TRACKS, workload.trains)
    trains = {
        f"t{i + 1}": TrainSpec(train_length(i), track)
        for i, track in enumerate(placements)
    }

    # 2. Workings — per train in id order, a chained walk between the stations.
    requests: list[RequestSpec] = []
    for train, placement in zip(trains, placements):
        here = placement
        for working in range(workload.workings):
            end = rng.choice(["A", "B"])  # uniform, never "the end facing the route"
            target = other_station(here)
            arrivals = _arrivals(rng, target, workload.dest)
            requests.append(
                RequestSpec(
                    train,
                    # Only a train's first working can state a block: where a
                    # later one departs is a dispatcher choice among the
                    # previous working's arrival ends.
                    f"{placement}.{end}" if working == 0 else end,
                    arrivals,
                    0,  # 3. Arrival — batch, every request at tick 0.
                )
            )
            here = STATIONS[target][0]  # only the station matters from here on

    # 4. Redraw — until every train's first request can eventually launch.
    # A head-on swap makes each train's arrival blocks the other's standing
    # lock and the run dead at tick 0 (#36); redraw each stuck request, end
    # first then arrival ends, keeping the workings count (BENCHMARKS.md).
    placement_of = dict(zip(trains, placements))
    first = {requests[i].train: i for i in range(0, len(requests), workload.workings)}
    while stuck := _stuck_trains(
        placement_of, {t: requests[i].arrivals for t, i in first.items()}
    ):
        for train in stuck:
            placement = placement_of[train]
            end = rng.choice(["A", "B"])
            arrivals = _arrivals(rng, other_station(placement), workload.dest)
            requests[first[train]] = RequestSpec(
                train, f"{placement}.{end}", arrivals, 0
            )

    return Scenario(_name(workload), workload.layout, trains, tuple(requests))


def _stuck_trains(
    placements: dict[str, str], arrivals: dict[str, tuple[str, ...]]
) -> list[str]:
    """Trains whose first request no dispatcher could ever launch, in id order.

    A train can launch once some arrival block is free, and a block frees
    once its occupant launches; anything outside that fixed point is stuck.
    Any placement that leaves a station track free admits a draw with
    nothing stuck, so the redraw loop terminates — and could not at six
    trains, which is one reason the trains axis ends at five."""
    occupant = {block: train for train, block in placements.items()}
    launchable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for train, ends in arrivals.items():
            if train in launchable:
                continue
            blocks = {end.partition(".")[0] for end in ends}
            if any(
                occupant.get(block) is None or occupant[block] in launchable
                for block in blocks
            ):
                launchable.add(train)
                changed = True
    return [train for train in arrivals if train not in launchable]


def _arrivals(rng: random.Random, station: str, dest: int) -> tuple[str, ...]:
    """The three intents of the `|dest|` axis, as Gotthard's three-track
    stations make them: one station, one track, one end."""
    tracks = STATIONS[station]
    if dest == 6:
        return tracks  # any track at the other station, either way round
    track = rng.choice(tracks)
    if dest == 2:
        return (track,)  # one track, either way round — the old semantics
    return (f"{track}.{rng.choice(['A', 'B'])}",)  # one track, one way round


def _name(workload: Workload) -> str:
    return (
        f"sweep-{workload.trains}t-{workload.workings}w"
        f"-d{workload.dest}-s{workload.seed}"
    )


def cells() -> Iterator[tuple[Workload, int, str]]:
    """The fixed grid: one (workload, k, locking) triple per run.

    `k` is capped at `|dest|`. Gotthard yields exactly one minimal route per
    arrival end, so the candidate set is exhausted at `|dest|` and the next
    tier is a six-transit detour — cells beyond are dead by construction.
    """
    for trains in TRAIN_COUNTS:
        for dest in DEST_SIZES:
            for seed in SEEDS:
                workload = Workload(LAYOUT, trains, WORKINGS, dest, seed)
                for k in K_VALUES:
                    if k > dest:
                        continue
                    for locking in STRATEGIES:
                        yield workload, k, locking


def row(workload: Workload, k: int, locking: str, trace: str) -> dict[str, Any]:
    """One JSONL row: every axis, then every metric."""
    m = metrics(trace)
    return {
        **asdict(workload),
        "k": k,
        "locking": locking,
        "status": m.status,
        "makespan": m.makespan,
        "ticks": m.ticks,
        "completed": len(m.completed),
        "rejected": len(m.rejected),
        "mean_latency": m.mean_latency,
        "max_latency": m.max_latency,
        "mean_utilization": m.mean_utilization,
        "mean_parallelism": m.mean_parallelism,
        "stalls": [asdict(stall) for stall in m.stalls],
    }


def sweep(out_dir: Path | None = None, root: Path | None = None) -> int:
    """Run the grid, writing one row per run. Returns the row count."""
    root = root or find_root()
    layout = AssetStore(root).get(LAYOUT)
    assert isinstance(layout, Layout)
    destination = out_dir or root / "out"
    destination.mkdir(parents=True, exist_ok=True)

    generated: dict[Workload, Scenario] = {}
    rows = 0
    with (destination / "sweep.jsonl").open("w") as out:
        for workload, k, locking in cells():
            if workload not in generated:  # dict.setdefault is not lazy
                generated[workload] = generate(workload)
            scenario = generated[workload]
            try:
                trace = run_scenario(layout, scenario, STRATEGIES[locking], k)
            except RuntimeError as exhausted:  # the live-lock backstop tripped
                raise RuntimeError(
                    f"{scenario.name} under {locking} at k={k}: {exhausted}"
                ) from exhausted
            out.write(json.dumps(row(workload, k, locking, trace)) + "\n")
            rows += 1
    return rows
