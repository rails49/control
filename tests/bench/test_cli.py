"""`tc49 bench`: the comparison table, the k flag, the trace dump (#30),
`tc49 layout show` (#45), and `tc49 generate` (#52, #126)."""

import io
import json
from pathlib import Path

import pytest

from tc49.bench.cli import GENERATORS, command_line, main, restart_note
from tc49.bench.metrics import metrics
from tc49.bench.runner import find_root
from tests.harness import ROOT


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
    assert "utilization" in printed and "crosses/boundary" in printed
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
    at_two = run_cli("bench", "gotthard/flexibility")
    at_one = run_cli("bench", "-k", "1", "gotthard/flexibility")
    assert "(k = 1)" in at_one
    assert "fixed-1 stalled — 'claro_2' held by 'resident' (held, 1" in at_one
    assert "fixed-1 stalled — 'claro_2' held by 'resident' (held, 2" in at_two


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
        "boundary",
        "request_admitted",
        "route_chosen",
        "cross",
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
    # `layouts/` and `scenarios/` are repo data, not package data — the wheel
    # ships src/tc49 alone — so the benchmark commands only work inside a
    # checkout, and must say that rather than raising on an invented path.
    assert (find_root(ROOT / "src" / "tc49" / "cli.py") / "layouts").is_dir()
    assert find_root(ROOT / "scenarios" / "gotthard") == ROOT
    with pytest.raises(FileNotFoundError, match="not usable from an installed wheel"):
        find_root(Path("/"))


def test_a_live_session_paces_itself_slowly_enough_to_watch() -> None:
    """Ten seconds a boundary, not two: each one moves trains, grants and
    releases locks, realigns points and changes aspects, and at two the next
    landed before a person had read the last (#144)."""
    args = command_line().parse_args(["live", "gotthard/meet"])
    assert args.period == 10.0


def test_a_live_session_may_come_up_with_no_scenario_at_all() -> None:
    """The panel names the session (#148). `tc49 live` comes up idle on its
    port waiting to be told, and a scenario on the command line is the
    railroad it comes up running rather than the one it is fixed to."""
    assert command_line().parse_args(["live"]).scenario is None
    named = command_line().parse_args(["live", "gotthard/meet"])
    assert named.scenario == "gotthard/meet"


def test_the_period_flag_still_sets_the_period_and_says_the_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A faster session stays one flag away, and the help says what it is
    faster than."""
    args = command_line().parse_args(["live", "gotthard/meet", "--period", "0.5"])
    assert args.period == 0.5
    with pytest.raises(SystemExit):
        command_line().parse_args(["live", "--help"])
    assert "default 10.0" in capsys.readouterr().out


def test_a_session_is_told_where_to_keep_the_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--state` is what makes a session outlive its process (#151), and the
    banner stops promising the opposite the moment it is given."""
    assert command_line().parse_args(["live"]).state is None
    kept = command_line().parse_args(["live", "--state", "run.json"])
    assert kept.state == Path("run.json")

    assert "fresh from the scenario" in restart_note(None)
    assert restart_note(Path("run.json")) == (
        "a restart adopts the placement and facing kept in run.json"
    )
    with pytest.raises(SystemExit):
        command_line().parse_args(["live", "--help"])
    assert "--state" in capsys.readouterr().out
