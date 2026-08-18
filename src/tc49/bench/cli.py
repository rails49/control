"""`tc49 bench <scenario>`, `tc49 sweep`, `tc49 live <scenario>`,
`tc49 layout show <layout>`, `tc49 serve`, `tc49 symbols`.

`bench` runs one named scenario under both locking strategies and prints the
comparison. `live` runs a session an outside client can join: wall-clock
ticks, the bridge relaying `tc49/#` out and `request_submitted` in, the
store served over HTTP, and no file scheduler (ADR-0016 exclusivity). `sweep` takes no arguments: the grid of BENCHMARKS.md is the
research design, not a knob, and that page is its single source of truth.
`layout show` prints the layout derived from a drawing, which is the topology
review that a committed layout file used to give in a diff (ADR-0015).
`symbols` regenerates the editor's TypeScript view of the symbol library.
"""

import argparse
import sys
import threading
from pathlib import Path
from typing import TextIO

from tc49.bench.metrics import Metrics, Stall, metrics
from tc49.bench.runner import (
    DEFAULT_K,
    STRATEGIES,
    assemble_live,
    find_root,
    run_scenario,
)
from tc49.bench.sweep import sweep
from tc49.lib.bridge import Bridge
from tc49.lib.layout import Layout
from tc49.lib.scenario import Scenario
from tc49.store import AssetStore
from tc49.store.server import make_server
from tc49.store.symbols import GENERATED, render

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


def format_layout(layout: Layout) -> str:
    """The whole derived topology: blocks with their lengths, and each
    connection's transits and concurrent pairs. Terminal blocks are marked
    because they are derived too, and nothing else shows them."""
    counted = f"{len(layout.blocks)} blocks, {len(layout.connections)} connections"
    lines = [f"{layout.name}  ({counted})", "", "blocks"]
    width = max(len(block) for block in layout.blocks) + 2
    for block in sorted(layout.blocks):
        terminal = "  terminal" if block in layout.terminal_blocks else ""
        lines.append(f"  {block.ljust(width)}{layout.blocks[block]:>6}{terminal}")

    for name in sorted(layout.connections):
        connection = layout.connections[name]
        lines += ["", name]
        width = max(len(transit) for transit in connection.transits) + 2
        for transit in sorted(connection.transits):
            ends = "  ".join(sorted(connection.transits[transit]))
            lines.append(f"  {transit.ljust(width)}{ends}")
        for pair in sorted(sorted(p) for p in connection.concurrent):
            lines.append(f"  concurrent  {pair[0]} + {pair[1]}")
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

    commands.add_parser("sweep", help="run the fixed grid of docs/bench/BENCHMARKS.md")

    live_parser = commands.add_parser(
        "live", help="run a live session an outside client can join (ui/PANEL.md)"
    )
    live_parser.add_argument(
        "scenario", help="stock, placement, and facing, e.g. gotthard/meet"
    )
    live_parser.add_argument(
        "--period",
        type=float,
        default=1.0,
        help="seconds per tick (default 1.0; the panel work tunes it by eye)",
    )
    live_parser.add_argument(
        "--port", type=int, default=8766, help="the bridge's WebSocket port"
    )
    live_parser.add_argument(
        "--store-port", type=int, default=8765, help="the store's HTTP port"
    )

    serve_parser = commands.add_parser(
        "serve", help="serve the asset store over HTTP, for the layout editor"
    )
    serve_parser.add_argument("--port", type=int, default=8765)

    symbols_parser = commands.add_parser(
        "symbols", help=f"write {GENERATED} from the symbol library"
    )
    symbols_parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / GENERATED,
        help=f"where to write it (default {GENERATED} in the checkout)",
    )

    layout_parser = commands.add_parser("layout", help="inspect a drawn railroad")
    layout_commands = layout_parser.add_subparsers(dest="layout_command", required=True)
    show_parser = layout_commands.add_parser(
        "show", help="print the layout derived from a drawing"
    )
    show_parser.add_argument("layout", help="e.g. crossover-yard")

    args = parser.parse_args(argv)
    if args.command == "bench":
        results = bench(args.scenario, args.k)
        out.write(format_comparison(args.scenario, args.k, results))
        if args.trace:
            out.write(results[args.trace][0])
        return 0

    if args.command == "live":
        layout, scenario = load(AssetStore(ROOT), args.scenario)
        assembly = assemble_live(layout, scenario)
        bridge = Bridge(assembly.bus, args.port)
        store_server = make_server(ROOT, args.store_port)
        threading.Thread(
            target=store_server.serve_forever, name="store", daemon=True
        ).start()
        out.write(
            f"live: {args.scenario} at {args.period}s per tick\n"
            f"  bridge  ws://127.0.0.1:{bridge.port}\n"
            f"  store   http://127.0.0.1:{args.store_port}\n"
            "no file scheduler runs; Ctrl-C ends the session, and a restart"
            " comes up fresh from the scenario\n"
        )
        out.flush()
        try:
            assembly.simulator.run_live(args.period)
        except KeyboardInterrupt:
            pass
        return 0

    if args.command == "serve":
        server = make_server(ROOT, args.port)
        out.write(f"serving {ROOT} on http://127.0.0.1:{server.server_port}\n")
        out.flush()
        server.serve_forever()
        return 0

    if args.command == "symbols":
        path: Path = args.out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render())
        out.write(f"wrote {path}\n")
        return 0

    if args.command == "layout":
        layout = AssetStore(ROOT).get(args.layout)
        assert isinstance(layout, Layout)
        out.write(format_layout(layout))
        return 0

    out.write(f"wrote {sweep()} rows\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
