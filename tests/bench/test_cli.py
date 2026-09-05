"""`tc49 bench`: the comparison table, the k flag, the trace dump (#30),
`tc49 layout show` (#45), `tc49 generate` (#52, #126), what `tc49 serve` reads
(#320), and how it ends (#410)."""

import io
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tc49.bench.cli import (
    GENERATORS,
    backing,
    command_line,
    ending_as_ctrl_c_does,
    holding,
    main,
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


def free_port() -> int:
    """A port nothing is listening on, so a server started here does not fight
    whatever else on the machine wants the default one."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_serve_reads_the_installations_store_by_default() -> None:
    """`~/tc49/` and not the checkout (#320). The fixtures under `bench/` are
    the benchmark's inputs, so a server started with no flag serves the
    railroads somebody drew — of which a fresh installation has none."""
    assert command_line().parse_args(["serve"]).store is None
    named = command_line().parse_args(["serve", "--store", "/srv/railroad"])
    assert named.store == Path("/srv/railroad")


def test_the_environment_roots_the_store_and_the_flag_beats_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The UI opens the store with no arguments, so `TC49_STORE` has to be an
    answer; a person typing `--store` is answering for this one command, which
    is the last word."""
    monkeypatch.setenv(STORE_ENV, str(tmp_path))
    assert store_root() == tmp_path
    assert store_root(ASSETS) == ASSETS


def test_an_empty_store_is_a_state_the_banner_says_rather_than_a_fault(
    tmp_path: Path,
) -> None:
    """A fresh installation has drawn nothing. The server comes up on it all
    the same, and what the banner owes is the root it looked in and that there
    was nothing there — otherwise an empty store and a mistyped `--store` read
    the same."""
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
    fixed at import, which is what lets `serve` run outside a checkout at
    all."""
    assert command_line().parse_args(["generate"]).out is None
    assert find_root(Path(__file__)) == ROOT


def test_the_banner_says_where_backup_stands(tmp_path: Path) -> None:
    """A store that is no repository is an ordinary state, so the banner says
    what backup needs rather than the command refusing to come up (ADR-0053).
    What it names is what to make and where to enter it (#355) — this never
    runs `git init` for anybody."""
    backup = Backup(tmp_path, log=lambda _: None)
    off = backing(backup)
    assert "backup  off" in off
    assert "create an empty private repository" in off

    backup.switch(True)
    assert "on, but" in backing(backup)
    assert "create an empty private repository" in backing(backup)


# --- how `tc49 serve` ends (#410) ---------------------------------------------


def run_git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def backed_up_store(tmp_path: Path) -> Path:
    """A store the way the layout server's is: a repository with backup on, a
    remote to push to — here on disk, so nothing reaches the network — and a
    drawing that has not been committed yet, which is what the exit has left
    to do."""
    remote = tmp_path / "somebody-railroad.git"
    run_git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    root = tmp_path / "tc49"
    (root / "layouts").mkdir(parents=True)
    run_git(tmp_path, "init", "-q", "-b", "main", str(root))
    run_git(root, "config", "user.email", "suite@example.invalid")
    run_git(root, "config", "user.name", "The Suite")
    run_git(root, "config", "commit.gpgsign", "false")
    run_git(root, "config", "push.autoSetupRemote", "true")
    run_git(root, "remote", "add", "origin", str(remote))
    (root / "layouts" / "reversing-loops.drawing.yaml").write_text(
        "drawing: reversing-loops\n"
    )
    Backup(root, log=lambda _: None).switch(True)
    return root


def test_a_deploy_stopping_the_server_lands_the_last_backup(
    backed_up_store: Path,
) -> None:
    """The store is PID 1 in its container, which gets no default action for
    SIGTERM: `docker stop` — which every deploy does, recreating the service —
    waited ten seconds, killed it, and the commit on quit was never made
    (#410). Here it ends within two seconds and the drawing is in the remote,
    which is the whole of what the quit was for."""
    served = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tc49.bench.cli",
            "serve",
            "--store",
            str(backed_up_store),
            "--port",
            str(free_port()),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert served.stdout is not None
        assert served.stdout.readline().startswith("serving ")  # it is up
        served.send_signal(signal.SIGTERM)
        said = served.communicate(timeout=2)[0]
    finally:
        served.kill()

    assert served.returncode == 0
    assert "reversing-loops" in said  # the commit the quit made, named
    remote = backed_up_store.parent / "somebody-railroad.git"
    assert "reversing-loops" in run_git(remote, "log", "--oneline")


def test_ctrl_c_and_a_deploy_leave_by_the_same_door() -> None:
    """SIGTERM raises the interrupt the Ctrl-C path already handles, rather
    than a second way out to keep in step with the first. Outside the block
    the process's own handling is back, so a `serve` run inside another
    process does not take that process's SIGTERM away from it."""
    was = signal.getsignal(signal.SIGTERM)
    with ending_as_ctrl_c_does(), pytest.raises(KeyboardInterrupt):
        os.kill(os.getpid(), signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) is was
