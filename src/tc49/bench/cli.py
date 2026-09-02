"""`tc49 bench <scenario>`, `tc49 sweep`, `tc49 live [railroad]`,
`tc49 layout show <layout>`, `tc49 serve`, `tc49 generate`.

`bench` runs one named scenario under both locking strategies and prints the
comparison. `live` runs a session an outside client can join: the simulator
pacing its delays on a wall clock, the bridge relaying `tc49/#` out and
gestures in, the store served over HTTP, and no timetable (ADR-0036). It is
built from a **railroad** — a drawing, its roster, and a person who places the
trains (#171) — and the railroad it comes up on is an argument the panel may
override, the socket path naming the one a client wants (#148). `--scenario`
is the harness's own test run: it comes up on the railroad the scenario names
and replays the document as gestures (`bench/replay.py`). `--station` puts the
**physical binding** where the simulator would be — the layout interface and
the `dccex` translator, driving a real command station (#314) — and pins the
session to the railroad named, a station being one physical railroad. That
session reads its own input, where a person types the detector's levels no
camera publishes yet (`bench/detector.py`, #315).
`sweep` takes no arguments: the grid of BENCHMARKS.md is the research design,
not a knob, and that page is its single source of truth.
`layout show` prints the layout derived from a drawing, which is the topology
review that a committed layout file used to give in a diff (ADR-0015).
`generate` rewrites every TypeScript file the UI is handed rather than
keeps by hand: the symbol library, and the set of rejection reasons.

**Two roots, and which command reads which.** `bench` and `sweep` run on the
committed fixtures and find them by searching for the checkout they are in
(`find_root`, `find_assets`), so what a person has in their own store cannot
move a number in BENCHMARKS.md. `live` and `serve` open the **installation's**
store instead — `~/tc49/` unless `--store` or `TC49_STORE` says otherwise
(`tc49.store.root`, #320) — and never look for a checkout at all, which is
what lets them run from an installed wheel. `layout show` is the topology
review of a committed drawing and stays with the fixtures; `generate` writes
into a checkout, which is what it is for.
"""

import argparse
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from tc49.bench.detector import LEVELS, SHAPE
from tc49.bench.metrics import Metrics, Stall, metrics
from tc49.bench.runner import (
    DEFAULT_K,
    STRATEGIES,
    find_assets,
    find_root,
    load,
    run_scenario,
)
from tc49.bench.session import Session
from tc49.bench.sweep import sweep
from tc49.lib import rejection
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.store import DEFAULT_STORE, STORE_ENV, AssetStore, store_root, symbols
from tc49.store.server import make_server

LIVE_PERIOD_S = 0.1
"""Seconds a live session waits between polls for commands arriving over the
bridge, unless `--period` says otherwise. The railroad's own pacing is the
simulator's transit delays (ADR-0047); this only bounds how long a gesture
sits in the queue before it is drained, so it stays small."""

STATION_EXAMPLE = "dccex-usb:2560"
"""What a station address looks like, for the help and for a refusal. The
`dccex-usb` mirror serves the command station on 2560 (docs/dccex_usb), and a
person running the two on one machine types this."""


def station(text: str) -> tuple[str, int]:
    """`<host>:<port>` as the address a connection is opened to.

    One argument and not two, because an address is one thing a person copies
    off a running `dccex-usb`. The port is split off the right, so an IPv6
    host written in brackets keeps its colons.
    """
    host, _, port = text.rpartition(":")
    if not host or not port.isdigit():
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a station address — write it <host>:<port>,"
            f" e.g. {STATION_EXAMPLE}"
        )
    return host, int(port)


def addressed(roster: Roster) -> tuple[int, int]:
    """How many of a railroad's trains have at least one addressed car, and
    how many have none.

    The one count a physical run's banner adds. A `move` for a train whose
    cars carry no address writes no traction row at all, so this is what turns
    "my train did nothing" into a one-line diagnosis.

    A count and not a refusal: a railroad whose stock is only partly addressed
    is an ordinary state rather than a fault. It reads what the roster in
    front of it says and assumes nothing about where that roster came from —
    the ones committed here are benchmark fixtures, and the stock somebody
    actually owns belongs in an installation's own documents (#318).
    """
    driveable = sum(
        any(coupled.car.addr is not None for coupled in train.cars)
        for train in roster.trains.values()
    )
    return driveable, len(roster.trains) - driveable


GENERATORS: dict[str, Callable[[], str]] = {
    symbols.GENERATED_PATH: symbols.render,
    rejection.GENERATED_PATH: rejection.render,
}
"""Every file the UI is handed rather than keeps by hand, and what writes it.
Keyed by the path each takes inside a checkout, so one command writes them
all and one flag says which checkout (ADR-0014)."""


def bench(
    scenario_id: str, k: int = DEFAULT_K, root: Path | None = None
) -> dict[str, tuple[str, Metrics]]:
    """One scenario under every strategy: (trace, metrics) per strategy.

    Over the fixtures the checkout carries, found rather than configured: a
    benchmark reads the documents BENCHMARKS.md records its numbers against,
    and what a person keeps in their own store is none of its business
    (#320)."""
    layout, roster, scenario = load(AssetStore(root or find_assets()), scenario_id)
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
        ("makespan", [_secs(results[n][1].makespan) for n in names]),
        ("latency mean", [_secs(results[n][1].mean_latency) for n in names]),
        ("latency max", [_secs(results[n][1].max_latency) for n in names]),
        ("utilization", [_ratio(results[n][1].mean_utilization) for n in names]),
        ("moves/min", [_ratio(results[n][1].moves_per_minute) for n in names]),
        ("completed", [str(len(results[n][1].completed)) for n in names]),
        ("rejected", [str(len(results[n][1].rejected)) for n in names]),
        ("cancelled", [str(len(results[n][1].cancelled)) for n in names]),
        ("seconds", [_secs(results[n][1].seconds) for n in names]),
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


def _secs(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


LOOPBACK = "127.0.0.1"
"""What the store and the bridge bind unless told otherwise. Loopback was the
whole of the authorization until a reverse proxy stood in front of them, and
that proxy runs in a container, which cannot reach a macOS host's loopback
(ADR-0042)."""


def reachable(host: str) -> str:
    """The host to put in a banner's URL. A wildcard bind is every interface
    and not an address anyone can paste, so loopback stands for it: it is one
    of the interfaces bound, and it is the one the reader is on."""
    return LOOPBACK if host in ("0.0.0.0", "::") else host


def store_flag(parser: argparse.ArgumentParser) -> None:
    """`--store`, on each of the two commands that open the installation's
    store.

    One function rather than two copies of the help, because the two are the
    same question — which store this is — and a person reading `tc49 live
    --help` beside `tc49 serve --help` must not find two answers. The
    environment is named in it: a session and the server that outlives it are
    usually started separately (scripts/dev.sh), and pointing both at one
    store is what `TC49_STORE` is for.
    """
    parser.add_argument(
        "--store",
        type=Path,
        metavar="PATH",
        help=f"the installation's store to read and serve (default"
        f" {DEFAULT_STORE}, or ${STORE_ENV} where it is set; this flag wins)."
        " The benchmark fixtures are not in it — name bench/ to run a live"
        " session on one of them",
    )


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
        help="the railroad to come up on, e.g. reversing-loops; with none the session"
        " waits to be told, and either way the panel may switch it",
    )
    coming_up.add_argument(
        "--scenario",
        help="run a scenario as a test run, e.g. reversing-loops/meet: the session"
        " comes up on the railroad it names and replays it as gestures —"
        " a placement per train, then its requests in order."
        " Not with --state, which comes up on the last session's placement",
    )
    live_parser.add_argument(
        "--period",
        type=float,
        default=LIVE_PERIOD_S,
        help=f"seconds between command polls (default {LIVE_PERIOD_S}; the"
        " railroad's pacing is the simulator's own transit delays)",
    )
    live_parser.add_argument(
        "--station",
        type=station,
        metavar="HOST:PORT",
        help="drive a real command station at that address, e.g."
        f" {STATION_EXAMPLE}: the layout interface and the dccex translator"
        " come up where the simulator would, and no simulator is built."
        " Requires the railroad, a station being one physical railroad, and"
        " is not for use with --scenario. Such a session reads its own input,"
        f" a typed '{SHAPE}' standing in for the detector nothing has yet",
    )
    live_parser.add_argument(
        "--startup",
        type=Path,
        help="a file of raw station commands sent when the rails are powered,"
        " where each of this railroad's power districts states the trip"
        " current it really takes (docs/dccex/README.md). Needs --station",
    )
    live_parser.add_argument(
        "--port", type=int, default=8766, help="the bridge's WebSocket port"
    )
    live_parser.add_argument(
        "--host",
        default=LOOPBACK,
        help=f"the address the bridge and the store bind (default {LOOPBACK};"
        " scripts/dev.sh binds every interface, which is what lets the proxy"
        " in front of them reach them — docs/DEPLOY.md)",
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
    store_flag(live_parser)
    live_parser.add_argument(
        "--no-store",
        action="store_true",
        help="leave the store to a `tc49 serve` already running (scripts/dev.sh)",
    )

    serve_parser = commands.add_parser(
        "serve", help="serve the asset store over HTTP, for the layout editor"
    )
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--host", default=LOOPBACK, help=f"the address it binds (default {LOOPBACK})"
    )
    store_flag(serve_parser)

    generate_parser = commands.add_parser(
        "generate", help="write the UI's generated TypeScript from its Python source"
    )
    generate_parser.add_argument(
        "--out",
        type=Path,
        help="the checkout to write into (default the one this runs in)",
    )

    layout_parser = commands.add_parser("layout", help="inspect a drawn railroad")
    layout_commands = layout_parser.add_subparsers(dest="layout_command", required=True)
    show_parser = layout_commands.add_parser(
        "show", help="print the layout derived from a drawing"
    )
    show_parser.add_argument("layout", help="e.g. crossover-yard")
    return parser


def station_note(where: tuple[str, int], name: str, roster: Roster) -> str:
    """What a physical run says about itself that a simulated one does not:
    which station it drives and that it stays on this railroad, how much of
    the stock it can move, and who its detectors are.

    **The session sees only what is typed, and says so.** No camera publishes
    `tc49/layout/state/device/sensor` yet, so the levels that complete a move
    are a person's, typed a line at a time on this session's own input
    (`bench/detector.py`, #315). It is said here rather than refused: a live
    run comes up **held**, and held admits and commits nothing, so lifting it
    is already a deliberate gesture. A second lock that existed only until a
    camera published would be a mechanism somebody has to remember to delete.
    """
    driveable, unaddressed = addressed(roster)
    trains = driveable + unaddressed
    return (
        f"  station {where[0]}:{where[1]}, driving {name} — one physical"
        " railroad, so this session switches to no other\n"
        f"  {driveable} of {trains} trains carry an address; a move for one of"
        f" the other {unaddressed} writes nothing\n"
        "this session sees what you type: no camera publishes yet, so type"
        f" '{SHAPE}' — {', '.join(LEVELS[:-1])} or {LEVELS[-1]} — and a move"
        " finishes on the pair a crossing trips\n"
    )


def holding(store: AssetStore) -> str:
    """What the store a command opened has in it, for the banner beside the
    root it was opened at.

    **An empty store is an ordinary state and is said, not refused** (#320). A
    fresh installation has drawn no railroad and nothing seeds one, so a
    person whose panel offers nothing to load needs to read which directory
    was looked in and that it was empty — otherwise an empty store and a
    mistyped `--store` are the same silence.
    """
    return ", ".join(store.list()) or (
        "no railroad yet — a fresh store is empty and nothing seeds one"
    )


def picking(pinned: bool) -> str:
    """What the banner promises about the railroad. A session ordinarily runs
    whichever railroad a client names and switches when another does (#148);
    one driving a command station stays where it is, and the banner must not
    go on offering the other thing."""
    if pinned:
        return "the panel joins this railroad and may not switch it"
    return "the panel names the railroad and may switch it"


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
        # A scenario is a document replayed onto an empty layout, and a
        # station is steel standing where somebody left it: replaying
        # placements onto it would command a railroad into a picture the
        # trains are not in. `--state` is the one combination hardware
        # improves, and is allowed (#314).
        if args.scenario is not None and args.station is not None:
            out.write(
                "--scenario replays a document as gestures and --station"
                " drives real trains standing where they were left; name one\n"
            )
            return 2
        # The station is one physical railroad, so the railroad is not the
        # first client's to pin. Both refusals come before the session,
        # because a session serves from construction and one decided after it
        # would leave the bridge port bound (#179).
        if args.station is not None and args.railroad is None:
            out.write(
                "--station drives one physical railroad; name the railroad it"
                " is under\n"
            )
            return 2
        # The installation's store and never the checkout's: a session runs
        # the railroads somebody drew, and the fixtures are the benchmark's
        # (#320). `--store bench` is what runs a session on one of those, and
        # is the developer flow scripts/dev.sh takes.
        root = store_root(args.store)
        # A physical session reads this process's own input, which is where a
        # person types the readings nothing else on a real railroad publishes
        # yet (#315). A simulated one is handed none: the simulator has its
        # own sensors, and a `tc49 live` in a pipeline reads nothing it was
        # not asked to.
        session = Session(
            root,
            args.period,
            args.port,
            args.state,
            args.host,
            args.station,
            args.startup,
            sys.stdin if args.station is not None else None,
        )
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
        # What a physical run says about itself. The roster is read here and
        # not held from the argument check above, because the session has
        # already opened the railroad by now: this is the stock it is running
        # and not a second opinion about whether the railroad is there.
        physical = ""
        if args.station is not None:
            named = args.railroad
            assert isinstance(named, str)  # named, by the refusal above
            physical = station_note(args.station, named, AssetStore(root).roster(named))
        # A session carries a store so that one command is all a browser
        # needs. Where one is already serving — scripts/dev.sh, whose store
        # outlives any session — a second would only fail to bind the port.
        store_line = ""
        if not args.no_store:
            store_server = make_server(root, args.store_port, args.host)
            threading.Thread(
                target=store_server.serve_forever, name="store", daemon=True
            ).start()
            store_line = f"  store   http://{reachable(args.host)}:{args.store_port}\n"
        out.write(
            f"live: polling commands every {args.period}s\n"
            f"  bridge  ws://{reachable(args.host)}:{session.bridge.port}/<railroad>\n"
            f"{store_line}"
            f"  rooted  {root}: {holding(AssetStore(root))}\n"
            f"{physical}"
            f"{picking(args.station is not None)}; there is no timetable;"
            f" Ctrl-C ends the session, and {restart_note(args.state)}\n"
        )
        out.flush()
        try:
            session.run(out)
        except KeyboardInterrupt:
            pass
        # The zeros and the track off have gone by here, the assembly having
        # stood its railroad down before letting the loop go (#314). Said
        # rather than assumed: leaving a live railroad behind is what this
        # prevents, and a person watching the process end wants to read that
        # it did not.
        if args.station is not None:
            out.write(
                "stood the railroad down: zero to every locomotive commanded,"
                " then the track off\n"
            )
        return 0

    if args.command == "serve":
        root = store_root(args.store)
        server = make_server(root, args.port, args.host)
        out.write(
            f"serving {root} on http://{reachable(args.host)}:{server.server_port}\n"
            f"  {holding(AssetStore(root))}\n"
        )
        out.flush()
        server.serve_forever()
        return 0

    if args.command == "generate":
        # The checkout this is running in unless another is named: the
        # generated sources are a checkout's and not a store's, so this is the
        # one command that still goes looking for one (ADR-0014).
        checkout: Path = args.out or find_root()
        for generated, render in GENERATORS.items():
            path = checkout / generated
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render())
            out.write(f"wrote {path}\n")
        return 0

    if args.command == "layout":
        # The fixtures: this is the topology review a committed layout file
        # used to give in a diff (ADR-0015), and what it reviews is what the
        # checkout carries.
        layout = AssetStore(find_assets()).get(args.layout)
        assert isinstance(layout, Layout)
        out.write(format_layout(layout))
        return 0

    out.write(f"wrote {sweep()} rows\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
