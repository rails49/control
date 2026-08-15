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
from tc49.locking import FullRoute, Incremental
from tc49.metrics import Metrics, metrics
from tc49.runner import DEFAULT_K, StrategyFactory, run_scenario
from tc49.store import AssetStore, Scenario

STRATEGIES: dict[str, StrategyFactory] = {
    "FullRoute": FullRoute,
    "Incremental": Incremental,
}

ROOT = Path(__file__).parent.parent.parent


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
        ("makespan", [_num(results[n][1].makespan) for n in names]),
        ("latency mean", [_num(results[n][1].mean_latency) for n in names]),
        ("latency max", [_num(results[n][1].max_latency) for n in names]),
        ("utilization", [_num(results[n][1].mean_utilization) for n in names]),
        ("crosses/tick", [_num(results[n][1].mean_parallelism) for n in names]),
        ("completed", [str(len(results[n][1].completed)) for n in names]),
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
            lines.append(
                f"\n{name}: {stall.id} stalled — {stall.reason}"
                f" on '{stall.resource}' held by '{stall.holder}'"
                f" ({stall.candidates_blocked} candidate(s) blocked)"
            )
    return "\n".join(lines) + "\n"


def _num(value: float | None) -> str:
    if value is None:
        return "—"
    return str(value) if isinstance(value, int) else f"{value:.3f}"


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

    from tc49.sweep import sweep

    out.write(f"wrote {sweep()} rows\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
