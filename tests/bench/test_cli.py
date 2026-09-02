"""`tc49 bench`: the comparison table, the k flag, the trace dump (#30),
`tc49 layout show` (#45), `tc49 generate` (#52, #126), and what `tc49 live`
takes and refuses (#179)."""

import io
import json
import socket
from pathlib import Path

import pytest

from tc49.bench.cli import (
    GENERATORS,
    backing,
    command_line,
    holding,
    main,
    restart_note,
)
from tc49.bench.metrics import metrics
from tc49.bench.runner import find_assets, find_root
from tc49.store import STORE_ENV, AssetStore, Backup, store_root
from tests.harness import ASSETS, ROOT, railroads


def run_cli(*argv: str) -> str:
    out = io.StringIO()
    assert main(list(argv), out) == 0
    return out.getvalue()


def test_bench_prints_the_metrics_for_both_strategies() -> None:
    printed = run_cli("bench", "crossover-yard/meet")
    assert "crossover-yard/meet  (k = 2)" in printed
    assert "FullRoute" in printed and "Incremental" in printed
    for metric in ("status", "makespan", "latency mean", "latency max"):
        assert metric in printed
    assert "utilization" in printed and "moves/min" in printed
    assert "stalled" not in printed


def test_bench_reports_the_stall_diagnosis_instead_of_a_makespan() -> None:
    printed = run_cli("bench", "single-track-meet/arrival-obstruction")
    assert "stalled" in printed
    assert "—" in printed  # no makespan for a stalled run
    assert "fixed-1 stalled" in printed
    assert "'east_1' held by 'squatter'" in printed
    assert "2 candidate(s) blocked" in printed


def test_k_is_overridable_and_changes_what_a_launch_may_try() -> None:
    # Congestion-aware costing (#33) sorts the obstructed candidate last, so
    # k = 1 no longer stalls the flexible request here — what k still caps is
    # how many candidates a refused launch tries, visible in the stall
    # diagnosis of the genuinely blocked one.
    at_two = run_cli("bench", "reversing-loops-v0/flexibility")
    at_one = run_cli("bench", "-k", "1", "reversing-loops-v0/flexibility")
    assert "(k = 1)" in at_one
    assert "fixed-1 stalled — 'station_c_2' held by 'resident' (held, 1" in at_one
    assert "fixed-1 stalled — 'station_c_2' held by 'resident' (held, 2" in at_two


def test_the_trace_flag_dumps_the_jsonl_events() -> None:
    printed = run_cli("bench", "crossover-yard/meet", "--trace", "Incremental")
    lines = [
        json.loads(line)
        for line in printed.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
    assert lines, "the trace should be dumped as JSONL"
    assert metrics("".join(json.dumps(line) + "\n" for line in lines)).status == "ok"
    assert {line["event"] for line in lines} >= {
        "request_admitted",
        "route_chosen",
        "move",
        "request_completed",
    }


def test_an_unknown_scenario_fails_loudly() -> None:
    with pytest.raises(FileNotFoundError):
        run_cli("bench", "crossover-yard/nope")


def test_a_rejected_request_is_reported_rather_than_flattering_the_makespan() -> None:
    # A rejection is work the run never attempted, and dropping it shortens the
    # makespan — so it must not read as `ok`.
    printed = run_cli("bench", "crossover-yard/rejection")
    assert "rejected" in printed
    assert "never attempted it" in printed


def test_layout_show_prints_the_derived_topology() -> None:
    # The review the committed layout file used to give in a diff (ADR-0015):
    # blocks with their lengths, every transit, and the concurrent pairs.
    lines = run_cli("layout", "show", "crossover-yard").splitlines()
    assert lines[0] == "crossover-yard  (6 blocks, 3 connections)"
    assert "blocks" in lines
    assert ["up_w", "3200"] in [line.split() for line in lines]
    assert ["yard_w", "1400", "terminal"] in [line.split() for line in lines]
    assert "crossover" in lines and "west_ladder" in lines
    assert ["up_straight", "up_e.A", "up_w.B"] in [line.split() for line in lines]
    assert ["concurrent", "dn_straight", "+", "up_straight"] in [
        line.split() for line in lines
    ]


def test_generate_writes_every_generated_file(tmp_path: Path) -> None:
    # Written into another checkout on purpose. Writing the committed files
    # here would repair a stale one before the test whose whole job is to
    # notice — tests/store/test_symbols.py — ever looked at it.
    written = run_cli("generate", "--out", str(tmp_path))
    assert GENERATORS, "the command would write nothing"
    for generated in GENERATORS:
        assert f"wrote {tmp_path / generated}\n" in written
        assert (tmp_path / generated).read_text() == (ROOT / generated).read_text()


def test_find_root_locates_the_railroads_from_anywhere_and_says_so_if_not() -> None:
    # The fixtures are repo data, not package data — the wheel ships src/tc49
    # alone — so the benchmark commands only work inside a checkout, and must
    # say that rather than raising on an invented path. They live under
    # `bench/`, and the store is rooted there rather than at the checkout.
    assert (find_root(ROOT / "src" / "tc49" / "cli.py") / "bench" / "layouts").is_dir()
    assert find_root(ASSETS / "scenarios" / "reversing-loops-v0") == ROOT
    assert find_assets(ROOT / "src" / "tc49" / "cli.py") == ASSETS
    with pytest.raises(FileNotFoundError, match="not usable from an installed wheel"):
        find_root(Path("/"))


def test_a_live_session_polls_for_commands_briskly() -> None:
    """The railroad's pacing is the simulator's own transit delays
    (ADR-0047); the period only bounds how long a gesture sits in the queue
    before it is drained, so it stays small."""
    args = command_line().parse_args(["live", "reversing-loops-v0/meet"])
    assert args.period == 0.1


def test_a_live_session_may_come_up_with_no_railroad_at_all() -> None:
    """The panel names the session (#148). `tc49 live` comes up idle on its
    port waiting to be told, and a railroad on the command line is the one it
    comes up on rather than the one it is fixed to."""
    assert command_line().parse_args(["live"]).railroad is None
    named = command_line().parse_args(["live", "reversing-loops-v0"])
    assert named.railroad == "reversing-loops-v0"


def test_the_period_flag_still_sets_the_period_and_says_the_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A faster session stays one flag away, and the help says what it is
    faster than."""
    args = command_line().parse_args(
        ["live", "reversing-loops-v0/meet", "--period", "0.5"]
    )
    assert args.period == 0.5
    with pytest.raises(SystemExit):
        command_line().parse_args(["live", "--help"])
    assert "default 0.1" in capsys.readouterr().out


def test_a_session_is_told_where_to_keep_the_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--state` is what makes a session outlive its process (#151), and the
    banner stops promising the opposite the moment it is given."""
    assert command_line().parse_args(["live"]).state is None
    kept = command_line().parse_args(["live", "--state", "run.json"])
    assert kept.state == Path("run.json")

    assert "an empty layout" in restart_note(None)
    assert restart_note(Path("run.json")) == (
        "a restart adopts the placement and facing kept beside run.json"
    )
    with pytest.raises(SystemExit):
        command_line().parse_args(["live", "--help"])
    assert "--state" in capsys.readouterr().out


def test_a_station_is_the_flag_that_selects_the_physical_binding() -> None:
    """A physical run needs the station's address anyway, so nothing else says
    which binding it is (#314); `--startup` is the trip currents that address
    is handed. Without them the session takes exactly what it took before."""
    name = railroads()[0]
    plain = command_line().parse_args(["live", name])
    assert plain.station is None and plain.startup is None
    driven = command_line().parse_args(
        ["live", name, "--station", "dccex-usb:2560", "--startup", "trip.txt"]
    )
    assert driven.station == ("dccex-usb", 2560)
    assert driven.startup == Path("trip.txt")


def free_port() -> int:
    """A port nothing is listening on, so a refusal can be watched giving back
    one it really held. The default 8766 would have the suite fight whatever
    else on the machine wants that port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


REFUSED_LIVE = [
    (["--scenario", "crossover-yard/meet", "--state", "run.json"], "name one"),
    (["--scenario", "crossover-yard/meet", "--station", "dccex-usb:2560"], "name one"),
    (["--station", "dccex-usb:2560"], "name the railroad it is under"),
    (["reversing-loops", "--startup", "trip.txt"], "name the --station it goes to"),
    (["nonesuch"], "no railroad 'nonesuch'"),
]
"""Every `tc49 live` the CLI refuses, and a word of the refusal. Four are
decided off the arguments alone, the last only by asking the store for the
railroad — which takes a session, and a session is already serving.

Each is run with `--store` naming the fixtures, so `nonesuch` is refused
against a store that does hold railroads rather than against whatever the
machine has in `~/tc49` (#320).

A station is one physical railroad: it may not be pinned by the first client
to connect, so it requires the positional railroad, and it replays no document
onto steel that is standing where the last session left it (#314). The trip
currents are the station's to carry, so `--startup` without one is refused
rather than taken and dropped (#334) — named over a railroad the fixtures
hold, so what is refused is the pairing and not a typo."""


@pytest.mark.parametrize("argv, wording", REFUSED_LIVE)
def test_a_refused_live_session_leaves_no_socket_bound(
    argv: list[str], wording: str
) -> None:
    """A session serves from construction, so a refusal decided after one is
    built holds the bridge port for the rest of the process (#179). From a
    shell that is invisible — the port goes when the process does — but in a
    pytest run it makes a later session's bind fail for reasons that have
    nothing to do with what is under test."""
    port = free_port()
    out = io.StringIO()

    argv = ["live", "--port", str(port), "--store", str(ASSETS), *argv]
    assert main(argv, out) == 2
    assert wording in out.getvalue()
    with socket.socket() as after:
        after.bind(("127.0.0.1", port))  # nothing is listening on it


def test_the_trip_currents_are_carried_past_the_refusals_by_a_station() -> None:
    """The fourth refusal is about the pairing and nothing else (#334): with a
    station named, `--startup` is carried on to the session, which then fails
    over the railroad like any other run. `--station` without `--startup` is
    untouched too — it is refused above only for want of a railroad."""
    out = io.StringIO()
    argv = [
        "live",
        "--port",
        str(free_port()),
        "--store",
        str(ASSETS),
        "nonesuch",
        "--station",
        "dccex-usb:2560",
        "--startup",
        "trip.txt",
    ]
    assert main(argv, out) == 2
    assert "no railroad 'nonesuch'" in out.getvalue()
    assert "--startup" not in out.getvalue()


def test_a_live_session_reads_the_installations_store_by_default() -> None:
    """`~/tc49/` and not the checkout (#320). The fixtures under `bench/` are
    the benchmark's inputs, so a session started with no flag comes up on the
    railroads somebody drew — of which a fresh installation has none."""
    assert command_line().parse_args(["live"]).store is None
    assert command_line().parse_args(["serve"]).store is None
    named = command_line().parse_args(["live", "--store", "/srv/railroad"])
    assert named.store == Path("/srv/railroad")


def test_the_environment_roots_a_session_and_the_flag_beats_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UI opens the store with no arguments, so `TC49_STORE` has to be an
    answer; a person typing `--store` is answering for this one command, which
    is the last word."""
    monkeypatch.setenv(STORE_ENV, str(tmp_path))
    out = io.StringIO()
    assert main(["live", "--port", str(free_port()), "reversing-loops"], out) == 2
    assert "no railroad 'reversing-loops'" in out.getvalue()

    assert store_root() == tmp_path
    assert store_root(ASSETS) == ASSETS


def test_no_fixture_is_reachable_from_a_store_of_ones_own(tmp_path: Path) -> None:
    """Nothing seeds a store, so a railroad the checkout carries is not in
    one: `tc49 live reversing-loops` against an empty root is refused in words
    rather than quietly running the benchmark's copy."""
    out = io.StringIO()
    argv = ["live", "--port", str(free_port()), "--store", str(tmp_path)]
    assert main([*argv, "reversing-loops"], out) == 2
    assert "no railroad 'reversing-loops'" in out.getvalue()


def test_an_empty_store_is_a_state_the_banner_says_rather_than_a_fault(
    tmp_path: Path,
) -> None:
    """A fresh installation has drawn nothing. The session and the server come
    up on it all the same, and what the banner owes is the root it looked in
    and that there was nothing there — otherwise an empty store and a mistyped
    `--store` read the same."""
    assert "no railroad yet" in holding(AssetStore(tmp_path))
    assert holding(AssetStore(ASSETS)) == ", ".join(railroads())


def test_the_benchmark_reads_the_fixtures_whatever_the_store_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BENCHMARKS.md records its numbers against the documents in this
    checkout, so no store of anyone's can move one — `bench` and `sweep` find
    the fixtures and never ask where the installation's store is (#320)."""
    monkeypatch.setenv(STORE_ENV, str(tmp_path / "not-even-there"))
    assert "crossover-yard/meet  (k = 2)" in run_cli("bench", "crossover-yard/meet")
    assert run_cli("layout", "show", "crossover-yard").startswith("crossover-yard")


def test_generate_writes_the_checkout_it_runs_in_unless_told_another(
    tmp_path: Path,
) -> None:
    """The generated sources are a checkout's and not a store's, so this is
    the one command that still goes looking for one. It is found rather than
    fixed at import, which is what lets `live` and `serve` run outside a
    checkout at all."""
    assert command_line().parse_args(["generate"]).out is None
    assert find_root(Path(__file__)) == ROOT


def test_the_banner_says_where_backup_stands(tmp_path: Path) -> None:
    """A store nobody has run `git init` in is an ordinary state, so the
    banner says what backup needs rather than the command refusing to come up
    (ADR-0053). What it names is the command a person would have run
    themselves — this never runs it for them."""
    backup = Backup(tmp_path, log=lambda _: None)
    off = backing(backup)
    assert "backup  off" in off
    assert "git init" in off

    backup.switch(True)
    assert "on, but" in backing(backup)
    assert "git init" in backing(backup)


def test_a_session_that_serves_no_store_leaves_backup_to_the_one_that_does(
    tmp_path: Path,
) -> None:
    """`--no-store` is a session beside a `tc49 serve` that outlives it
    (scripts/dev.sh). The saves are that server's, and so is the timer they
    arm: two processes committing one store would each be committing the
    other's half-finished editing session."""
    assert "left to the `tc49 serve` already running" in backing(None)
    assert "backup" in backing(Backup(tmp_path, log=lambda _: None))
