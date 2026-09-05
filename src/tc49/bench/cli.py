"""`tc49 bench <scenario>`, `tc49 sweep`, `tc49 layout show <layout>`,
`tc49 serve`, `tc49 readings`, `tc49 generate`.

`bench` runs one named scenario under both locking strategies and prints the
comparison.
`readings` is a person's keyboard as **a client of the broker**: with each app
in a process of its own there is nothing holding both, so the person publishing
the rows a detector will publish connects to the broker like the camera that
replaces them, and reads the railroad off the store to know which block ends
there are (ADR-0059, decision 5, #379). It stays here rather than becoming an
app because what it stands in for is hardware.
`sweep` takes no arguments: the grid of BENCHMARKS.md is the research design,
not a knob, and that page is its single source of truth.
`layout show` prints the layout derived from a drawing, which is the topology
review that a committed layout file used to give in a diff (ADR-0015).
`generate` rewrites every TypeScript file the UI is handed rather than
keeps by hand: the symbol library, and the set of rejection reasons.

**Two things called `--store`, on either side of a process boundary.** `serve`
opens a store **directory** on this machine, because it is what serves it.
`readings` is given the store's **URL** instead, as the app containers are: it
runs where the keyboard is and the documents are wherever they are served
from, so it reads the one it needs over HTTP and waits for the store to answer
(`lib/documents.py`).

**Two roots, and which command reads which.** `bench` and `sweep` run on the
committed fixtures and find them by searching for the checkout they are in
(`find_root`, `find_assets`), so what a person has in their own store cannot
move a number in BENCHMARKS.md. `serve` opens the **installation's** store
instead — `~/tc49/` unless `--store` or `TC49_STORE` says otherwise
(`tc49.store.root`, #320) — and never looks for a checkout at all, which is
what lets it run from an installed wheel. `layout show` is the topology
review of a committed drawing and stays with the fixtures; `generate` writes
into a checkout, which is what it is for.

**Whichever process serves the store backs it up**, git being what keeps a
copy of documents that are on one disk (ADR-0053, store/BACKUP.md). The saves
that arrive over the HTTP face arm an idle timer that a watch thread lets
fire, and quitting commits what it had not reached yet — Ctrl-C, or the
SIGTERM a deploy stops the container with, which end `serve` the same way
(#410).
"""

import argparse
import contextlib
import signal
import sys
import threading
from collections.abc import Callable, Generator
from pathlib import Path
from types import FrameType
from typing import TextIO

from tc49.bench.detector import CLIENT_ID, serve
from tc49.bench.metrics import Metrics, Stall, metrics
from tc49.bench.runner import (
    DEFAULT_K,
    STRATEGIES,
    find_assets,
    find_root,
    load,
    run_scenario,
)
from tc49.bench.sweep import sweep
from tc49.lib import rejection
from tc49.lib.documents import Documents
from tc49.lib.layout import Layout
from tc49.lib.mqtt import BROKER_EXAMPLE, MqttBus, address
from tc49.store import DEFAULT_STORE, STORE_ENV, AssetStore, Backup, store_root, symbols
from tc49.store.backup import IDLE_S, PUSH_S, Watch
from tc49.store.server import make_server

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
"""What the store binds unless told otherwise. Loopback was the whole of the
authorization until a reverse proxy stood in front of it, and that proxy runs
in a container, which cannot reach a macOS host's loopback (ADR-0042)."""


def reachable(host: str) -> str:
    """The host to put in a banner's URL. A wildcard bind is every interface
    and not an address anyone can paste, so loopback stands for it: it is one
    of the interfaces bound, and it is the one the reader is on."""
    return LOOPBACK if host in ("0.0.0.0", "::") else host


def store_flag(parser: argparse.ArgumentParser) -> None:
    """`--store`, on the one command that opens the installation's store.

    A function rather than the argument written inline, because the
    environment belongs in the help beside it: `scripts/dev.sh` serves the
    checkout's fixtures rather than an installation, and pointing this and
    whatever apps a developer starts at one store is what `TC49_STORE` is for.
    """
    parser.add_argument(
        "--store",
        type=Path,
        metavar="PATH",
        help=f"the installation's store to read and serve (default"
        f" {DEFAULT_STORE}, or ${STORE_ENV} where it is set; this flag wins)."
        " The benchmark fixtures are not in it — name bench/ to serve one"
        " of them",
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

    serve_parser = commands.add_parser(
        "serve", help="serve the asset store over HTTP, for the layout editor"
    )
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument(
        "--host", default=LOOPBACK, help=f"the address it binds (default {LOOPBACK})"
    )
    store_flag(serve_parser)
    serve_parser.add_argument(
        "--keys",
        type=Path,
        metavar="DIR",
        help="where the store keeps the deploy key its backups push with; a"
        " key is made there on first use, and its public half is shown in the"
        " backup dialog (#355). Without it, git pushes with whatever ssh key"
        " this machine already has",
    )

    readings_parser = commands.add_parser(
        "readings",
        help="publish the block readings a person types, standing in for the"
        " detector nothing has yet (#315)",
    )
    readings_parser.add_argument(
        "--broker",
        required=True,
        metavar="HOST:PORT",
        help=f"the broker the railroad runs on, e.g. {BROKER_EXAMPLE}",
    )
    readings_parser.add_argument(
        "--railroad",
        required=True,
        help="the railroad this broker runs, as the store lists it: a typed"
        " block end is checked against its layout, a reading for a block"
        " nothing has being one the dispatcher could not explain",
    )
    readings_parser.add_argument(
        "--store",
        required=True,
        metavar="URL",
        help="where the store serves the documents, e.g. http://127.0.0.1:8765;"
        " waited for until it answers. A URL and not a directory: this runs"
        " where the keyboard is, and the documents are served from wherever"
        " they are",
    )

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


def noting(out: TextIO) -> Callable[[str], None]:
    """Where backup says what came of a commit or a push: the same stream the
    banner went to.

    It is written from the watch thread as well as from the one quitting, so
    it flushes each line — a push that could not reach the remote is the whole
    of what a person gets to see about it, and a buffered one arrives after
    the process it was explaining."""

    def note(words: str) -> None:
        out.write(f"{words}\n")
        out.flush()

    return note


def backing(backup: Backup) -> str:
    """The banner's line about backup: whether the store is being copied
    anywhere, and what stands in the way where something does.

    Whichever process serves the store backs it up, and one process serves it:
    a save is what arms the idle timer, and two committing one store would
    each be committing the other's half-finished work (#321).
    """
    missing = backup.needs()
    if not backup.automatic:
        stands = "off" + (f": {missing[0]}" if missing else "")
    elif missing:
        stands = f"on, but {missing[0]}"
    else:
        stands = (
            f"on: a commit after {IDLE_S:.0f}s of quiet, and a push every {PUSH_S:.0f}s"
        )
    return f"  backup  {stands}\n"


@contextlib.contextmanager
def ending_as_ctrl_c_does(taken: int = signal.SIGTERM) -> Generator[None]:
    """SIGTERM raising the interrupt Ctrl-C raises, for the length of the
    block.

    The store's server is PID 1 in its container, and PID 1 gets no default
    action for SIGTERM: `docker stop` — which every `compose up` that
    recreates the service does, and `scripts/deploy.sh` recreates it on each
    deploy — waited ten seconds and then killed it, so the commit on quit was
    never made and the store was unreachable for those ten seconds (#410).

    Raising the interrupt rather than calling the server's shutdown, because
    a handler runs on the thread that is already inside `serve_forever` and
    that shutdown waits there for it to return. It is the one exit path too:
    Ctrl-C and a deploy leave by the same door rather than by two that have
    to be kept in step.

    The handler that was there is put back on the way out, so a `serve` run
    inside another process leaves that process's handling as it found it.
    """

    def interrupt(_signal: int, _frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    was = signal.signal(taken, interrupt)
    try:
        yield
    finally:
        signal.signal(taken, was)


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    args = command_line().parse_args(argv)
    if args.command == "bench":
        results = bench(args.scenario, args.k)
        out.write(format_comparison(args.scenario, args.k, results))
        if args.trace:
            out.write(results[args.trace][0])
        return 0

    if args.command == "readings":
        # The broker before the store, because a mistyped address is the one
        # refusal this command can make on its own: everything else it needs is
        # waited for rather than refused, and a person who cannot publish has
        # nothing to type at.
        try:
            host, port = address(args.broker)
        except ValueError as refused:
            out.write(f"{refused}\n")
            return 2
        # Connecting from construction, so the connection is being made while
        # the store is asked for the drawing: neither is ordered by the other
        # coming up first (ADR-0059, decision 5).
        bus = MqttBus(host, port, client_id=CLIENT_ID)
        try:
            # `serve` here is the detector's loop and not the `serve` command:
            # what a person types, published until the input ends or Ctrl-C
            # raises. Refusals go to `out`, beside the line that earned one.
            with contextlib.suppress(KeyboardInterrupt):
                layout = Documents(args.store).layout(args.railroad)
                serve(bus, layout, sys.stdin, out, threading.Event())
        finally:
            bus.close()
        return 0

    if args.command == "serve":
        root = store_root(args.store)
        backup = Backup(root, log=noting(out), keys=args.keys)
        server = make_server(root, args.port, args.host, backup)
        watch = Watch(backup)
        watch.start()
        # The banner is inside the handling, and not before it, so that a
        # deploy's SIGTERM arriving in the first milliseconds of the process
        # is the tidy exit too rather than the default kill.
        with ending_as_ctrl_c_does():
            try:
                out.write(
                    f"serving {root} on"
                    f" http://{reachable(args.host)}:{server.server_port}\n"
                    f"  {holding(AssetStore(root))}\n"
                    f"{backing(backup)}"
                )
                out.flush()
                server.serve_forever()
            except KeyboardInterrupt:
                # Ctrl-C is how this ends by hand and SIGTERM how a deploy
                # ends it; both arrive here, and there is one thing left to do
                pass
        watch.stop()
        backup.quit()
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
