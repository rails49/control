"""`tc49 bench <scenario>`, `tc49 sweep`, `tc49 live [railroad]`,
`tc49 layout show <layout>`, `tc49 serve`, `tc49 generate`.

`bench` runs one named scenario under both locking strategies and prints the
comparison. `live` runs a session an outside client can join: wall-clock
boundaries, the bridge relaying `tc49/#` out and gestures in, the store served
over HTTP, and no timetable while `at` is a boundary count (ADR-0036). It is
built from a **railroad** — a drawing, its roster, and a person who places the
trains (#171) — and the railroad it comes up on is an argument the panel may
override, the socket path naming the one a client wants (#148). `--scenario`
is the harness's own test run: it comes up on the railroad the scenario names
and replays the document as gestures (`bench/replay.py`). `sweep` takes no
arguments:
the grid of BENCHMARKS.md is the research design, not a knob, and that page is
its single source of truth.
`layout show` prints the layout derived from a drawing, which is the topology
review that a committed layout file used to give in a diff (ADR-0015).
`generate` rewrites every TypeScript file the UI is handed rather than
keeps by hand: the symbol library, and the set of rejection reasons.
"""

import argparse
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from tc49.bench.metrics import Metrics, Stall, metrics
from tc49.bench.runner import DEFAULT_K, STRATEGIES, find_root, load, run_scenario
from tc49.bench.session import Session
from tc49.bench.sweep import sweep
from tc49.lib import rejection
from tc49.lib.layout import Layout
from tc49.store import AssetStore, symbols
from tc49.store.server import make_server

ROOT = find_root()

LIVE_PERIOD_S = 10.0
"""Seconds a live session spends on each grant boundary, unless `--period`
says otherwise. Picked by watching the panel, the way the two seconds before
it were: each boundary moves trains, grants and releases locks, realigns
points and changes aspects, and at two the next one landed before a person
had finished reading the last (ui/PANEL.md). Not the replay transport's
number, which is a rate in boundaries per second and stays where it is."""

GENERATORS: dict[str, Callable[[], str]] = {
    symbols.GENERATED_PATH: symbols.render,
    rejection.GENERATED_PATH: rejection.render,
}
"""Every file the UI is handed rather than keeps by hand, and what writes it.
Keyed by the path each takes inside a checkout, so one command writes them
all and one flag says which checkout (ADR-0014)."""


def bench(
    scenario_id: str, k: int = DEFAULT_K, root: Path = ROOT
) -> dict[str, tuple[str, Metrics]]:
    """One scenario under every strategy: (trace, metrics) per strategy."""
    layout, roster, scenario = load(AssetStore(root), scenario_id)
    results: dict[str, tuple[str, Metrics]] = {}
    for name, strategy in STRATEGIES.items():
        trace = run_scenario(layout, roster, scenario, strategy, k)
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
        ("crosses/boundary", [_ratio(results[n][1].mean_parallelism) for n in names]),
        ("completed", [str(len(results[n][1].completed)) for n in names]),
        ("rejected", [str(len(results[n][1].rejected)) for n in names]),
        ("boundaries", [str(results[n][1].boundaries) for n in names]),
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


def command_line() -> argparse.ArgumentParser:
    """Every command and flag `tc49` takes. Apart from `main` so that a
    default can be read without running the command that carries it."""
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
    # One or the other, never both: a scenario names the railroad it is over,
    # so giving one alongside it could only agree or contradict.
    coming_up = live_parser.add_mutually_exclusive_group()
    coming_up.add_argument(
        "railroad",
        nargs="?",
        help="the railroad to come up on, e.g. gotthard; with none the session"
        " waits to be told, and either way the panel may switch it",
    )
    coming_up.add_argument(
        "--scenario",
        help="run a scenario as a test run, e.g. gotthard/meet: the session"
        " comes up on the railroad it names and replays it as gestures —"
        " a placement per train, then its requests at their boundaries."
        " Not with --state, which comes up on the last session's placement",
    )
    live_parser.add_argument(
        "--period",
        type=float,
        default=LIVE_PERIOD_S,
        help=f"seconds per boundary (default {LIVE_PERIOD_S}, picked by watching"
        " the panel — as much as a boundary's worth of change takes to read)",
    )
    live_parser.add_argument(
        "--port", type=int, default=8766, help="the bridge's WebSocket port"
    )
    live_parser.add_argument(
        "--state",
        type=Path,
        help="keep the runs' pictures beside this path, one file per railroad,"
        " so a restart comes up where each railroad stopped rather than with an"
        " empty layout",
    )
    live_parser.add_argument(
        "--store-port", type=int, default=8765, help="the store's HTTP port"
    )
    live_parser.add_argument(
        "--no-store",
        action="store_true",
        help="leave the store to a `tc49 serve` already running (scripts/dev.sh)",
    )

    serve_parser = commands.add_parser(
        "serve", help="serve the asset store over HTTP, for the layout editor"
    )
    serve_parser.add_argument("--port", type=int, default=8765)

    generate_parser = commands.add_parser(
        "generate", help="write the UI's generated TypeScript from its Python source"
    )
    generate_parser.add_argument(
        "--out",
        type=Path,
        default=ROOT,
        help="the checkout to write into (default this one)",
    )

    layout_parser = commands.add_parser("layout", help="inspect a drawn railroad")
    layout_commands = layout_parser.add_subparsers(dest="layout_command", required=True)
    show_parser = layout_commands.add_parser(
        "show", help="print the layout derived from a drawing"
    )
    show_parser.add_argument("layout", help="e.g. crossover-yard")
    return parser


def restart_note(state: Path | None) -> str:
    """What the live banner promises about coming back up. With no file the
    session forgets the railroad when the process ends, and the banner has
    said so since #71; with one it comes up where the railroad stopped, and
    the banner must stop promising the other thing (#151)."""
    if state is None:
        return "a restart comes up with an empty layout"
    return f"a restart adopts the placement and facing kept beside {state}"


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    args = command_line().parse_args(argv)
    if args.command == "bench":
        results = bench(args.scenario, args.k)
        out.write(format_comparison(args.scenario, args.k, results))
        if args.trace:
            out.write(results[args.trace][0])
        return 0

    if args.command == "live":
        # Two sources for one placement, and no reason to choose between
        # them: `--state` comes up standing the trains where the last session
        # left them, and a replay's placements would then be refused one by
        # one for the blocks those trains hold — a run silently unlike the
        # document, with no diagnostic (#171). Before the session, because a
        # session serves from construction and a refusal that came after it
        # would leave the bridge port bound (#179).
        if args.scenario is not None and args.state is not None:
            out.write(
                "--scenario replays a document onto an empty layout and"
                " --state comes up on the last session's placement; name one\n"
            )
            return 2
        session = Session(ROOT, args.period, args.port, args.state)
        # What the session comes up on, and the refusal if it cannot: a
        # scenario names its own railroad and replays onto it, a railroad
        # comes up empty, and with neither the session waits to be told.
        opening: str | None = None
        if args.scenario is not None:
            opening = session.plays(args.scenario)
        elif args.railroad is not None:
            opening = session.wants(args.railroad)
        if opening is not None:
            # This one needs the session — only a session can say whether the
            # store opens a railroad — so the port it took is given back here
            # instead (#179).
            session.bridge.close()
            out.write(f"{opening}\n")
            return 2
        # A session carries a store so that one command is all a browser
        # needs. Where one is already serving — scripts/dev.sh, whose store
        # outlives any session — a second would only fail to bind the port.
        store_line = ""
        if not args.no_store:
            store_server = make_server(ROOT, args.store_port)
            threading.Thread(
                target=store_server.serve_forever, name="store", daemon=True
            ).start()
            store_line = f"  store   http://127.0.0.1:{args.store_port}\n"
        out.write(
            f"live: {args.period}s per boundary\n"
            f"  bridge  ws://127.0.0.1:{session.bridge.port}/<railroad>\n"
            f"{store_line}"
            "the panel names the railroad and may switch it; there is no"
            f" timetable; Ctrl-C ends the session, and {restart_note(args.state)}\n"
        )
        out.flush()
        try:
            session.run(out)
        except KeyboardInterrupt:
            pass
        return 0

    if args.command == "serve":
        server = make_server(ROOT, args.port)
        out.write(f"serving {ROOT} on http://127.0.0.1:{server.server_port}\n")
        out.flush()
        server.serve_forever()
        return 0

    if args.command == "generate":
        root: Path = args.out
        for generated, render in GENERATORS.items():
            path = root / generated
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
