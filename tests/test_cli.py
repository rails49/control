"""`tc49 bench`: the comparison table, the k flag, the trace dump (#30)."""

import io
import json
from pathlib import Path

import pytest

from tc49.cli import main
from tc49.metrics import metrics
from tc49.runner import find_root
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
    assert "utilization" in printed and "crosses/tick" in printed
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
        "tick",
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


def test_find_root_locates_the_railroads_from_anywhere_and_says_so_if_not() -> None:
    # `layouts/` and `scenarios/` are repo data, not package data — the wheel
    # ships src/tc49 alone — so the benchmark commands only work inside a
    # checkout, and must say that rather than raising on an invented path.
    assert (find_root(ROOT / "src" / "tc49" / "cli.py") / "layouts").is_dir()
    assert find_root(ROOT / "scenarios" / "gotthard") == ROOT
    with pytest.raises(FileNotFoundError, match="not usable from an installed wheel"):
        find_root(Path("/"))
