"""`tc49 bench <scenario>` and `tc49 sweep`.

`bench` runs one named scenario under both locking strategies and prints the
comparison. `sweep` takes no arguments: the grid of BENCHMARKS.md is the
research design, not a knob, and that page is its single source of truth.
"""

import argparse
import sys
from pathlib import Path
from typing import TextIO

from tc49.layout import Layout
from tc49.metrics import Metrics, Stall, metrics
from tc49.runner import DEFAULT_K, STRATEGIES, find_root, run_scenario
from tc49.store import AssetStore, Scenario
from tc49.sweep import sweep

ROOT = find_root()


def load(store: AssetStore, scenario_id: str) -> tuple[Layout, Scenario]:
    scenario = store.get(scenario_id)
    assert isinstance(scenario, Scenario)
    layout = store.get(scenario.layout)
    assert isinstance(layout, Layout)
    return layout, scenario


def bench(
    scenario_id: str, k: int = DEFAULT_K, root: Path = ROOT
) -> dict[str, tuple[str, Metrics]]:
    """One scenario under every strategy: (trace, metrics) per strategy."""
    layout, scenario = load(AssetStore(root), scenario_id)
    results: dict[str, tuple[str, Metrics]] = {}
    for name, strategy in STRATEGIES.items():
        trace = run_scenario(layout, scenario, strategy, k)
        results[name] = (trace, metrics(trace))
    return results


def format_comparison(
    scenario_id: str, k: int, results: dict[str, tuple[str, Metrics]]
) -> str:
    """The comparison table, plus a stall diagnosis for any stalled run."""
    names = list(results)
    rows: list[tuple[str, list[str]]] = [
        ("status", [results[n][1].status for n in names]),
        ("makespan", [_whole(results[n][1].makespan) for n in names]),
        ("latency mean", [_ratio(results[n][1].mean_latency) for n in names]),
        ("latency max", [_whole(results[n][1].max_latency) for n in names]),
        ("utilization", [_ratio(results[n][1].mean_utilization) for n in names]),
        ("crosses/tick", [_ratio(results[n][1].mean_parallelism) for n in names]),
        ("completed", [str(len(results[n][1].completed)) for n in names]),
        ("rejected", [str(len(results[n][1].rejected)) for n in names]),
        ("ticks", [str(results[n][1].ticks) for n in names]),
    ]
    width = max(len(label) for label, _ in rows) + 2
    column = max(max(len(n) for n in names), 11) + 2

    lines = [f"{scenario_id}  (k = {k})", ""]
    lines.append(" " * width + "".join(n.rjust(column) for n in names))
    for label, values in rows:
        lines.append(label.rjust(width) + "".join(v.rjust(column) for v in values))

    for name in names:
        for stall in results[name][1].stalls:
            lines.append(f"\n{name}: {_diagnosis(stall)}")
        for rid in results[name][1].rejected:
            lines.append(f"\n{name}: {rid} rejected — the run never attempted it")
    return "\n".join(lines) + "\n"


def _diagnosis(stall: Stall) -> str:
    if stall.reason == "queued":
        # Never attempted: an earlier working of the same train is itself
        # still pending, so there is no resource and no holder to name.
        return f"{stall.id} stalled — queued behind an earlier working"
    return (
        f"{stall.id} stalled — '{stall.resource}' held by '{stall.holder}'"
        f" ({stall.reason}, {stall.candidates_blocked} candidate(s) blocked)"
    )


def _whole(value: int | None) -> str:
    return "—" if value is None else str(value)


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(prog="tc49")
    commands = parser.add_subparsers(dest="command", required=True)

    bench_parser = commands.add_parser("bench", help="run one named scenario")
    bench_parser.add_argument("scenario", help="e.g. crossover-yard/meet")
    bench_parser.add_argument(
        "-k",
        type=int,
        default=DEFAULT_K,
        help=f"candidate route budget (default {DEFAULT_K}; goldens are at the default)",
    )
    bench_parser.add_argument(
        "--trace",
        metavar="STRATEGY",
        choices=list(STRATEGIES),
        help="also dump that strategy's JSONL event trace",
    )

    commands.add_parser("sweep", help="run the fixed grid of docs/BENCHMARKS.md")

    args = parser.parse_args(argv)
    if args.command == "bench":
        results = bench(args.scenario, args.k)
        out.write(format_comparison(args.scenario, args.k, results))
        if args.trace:
            out.write(results[args.trace][0])
        return 0

    out.write(f"wrote {sweep()} rows\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
