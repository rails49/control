"""metrics(trace) against hand-written traces — no run required (#30).

Writing the traces by hand is the point: every metric is a pure function of
the events SYSTEM.md defines, so each one can be pinned to an exact input
here, and `test_the_trace_is_load_bearing` then proves the dependency runs
the other way too — suppress any metric-feeding event in a real trace and a
metric changes.
"""

import json
from typing import Any

import pytest

from tc49.bench.metrics import Stall, metrics, parse
from tc49.dispatcher import Incremental
from tests.harness import events, load, run


def trace(*lines: dict[str, Any]) -> str:
    return "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines)


def submitted(rid: str, at: float) -> dict[str, Any]:
    return {"time": at, "event": "request_submitted", "id": rid}


def admitted(rid: str, at: float) -> dict[str, Any]:
    return {"time": at, "event": "request_admitted", "id": rid}


def completed(rid: str, at: float) -> dict[str, Any]:
    return {"time": at, "event": "request_completed", "id": rid}


def granted(at: float, *resources: str) -> dict[str, Any]:
    return {"time": at, "event": "lock_granted", "resources": list(resources)}


def released(at: float, *resources: str) -> dict[str, Any]:
    return {
        "time": at,
        "event": "lock_released",
        "resources": list(resources),
    }


def refused(
    rid: str, at: float, reason: str, *pairs: tuple[str, str]
) -> dict[str, Any]:
    return {
        "time": at,
        "event": "grant_refused",
        "id": rid,
        "reason": reason,
        "obstacles": [{"resource": r, "holder": h} for r, h in pairs],
    }


def test_makespan_is_first_admission_to_last_completion() -> None:
    m = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            submitted("b-1", 2),
            admitted("b-1", 2),
            completed("a-1", 5),
            completed("b-1", 9),
        )
    )
    assert m.makespan == 9
    assert m.completed == ("a-1", "b-1")
    assert m.status == "ok"


def test_latency_is_completion_minus_the_stamp_the_request_arrived() -> None:
    m = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            submitted("b-1", 4),
            admitted("b-1", 4),
            completed("a-1", 10),  # latency 10
            completed("b-1", 8),  # latency 4
        )
    )
    assert m.max_latency == 10
    assert m.mean_latency == 7


def test_latency_without_the_submission_stamp_is_a_loud_error() -> None:
    with pytest.raises(ValueError, match="missing 'request_submitted' for 'a-1'"):
        metrics(trace(admitted("a-1", 0), completed("a-1", 3)))


def test_utilization_counts_spans_over_the_whole_run() -> None:
    # The run spans 0..4 seconds. `held` is locked for two of them and
    # `standing` — a startup standing lock, never released — for all four.
    m = metrics(
        trace(
            granted(0.0, "standing"),
            granted(1.0, "held"),
            released(3.0, "held"),
            submitted("a-1", 0.0),
            admitted("a-1", 0.0),
            completed("a-1", 4.0),
        )
    )
    assert m.seconds == 4.0
    assert m.utilization == {"held": 0.5, "standing": 1.0}
    assert m.mean_utilization == 0.75


def test_throughput_is_move_commands_per_simulated_minute() -> None:
    m = metrics(
        trace(
            {"time": 0.0, "event": "move", "train": "a", "into": "x"},
            {"time": 0.0, "event": "move", "train": "b", "into": "y"},
            {"time": 30.0, "event": "move", "train": "a", "into": "z"},
        )
    )
    assert m.moves == 3
    assert m.moves_per_minute == 6.0  # three moves over half a minute


def test_a_stall_is_diagnosed_from_the_last_refusal_and_kills_the_makespan() -> None:
    m = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            submitted("b-1", 0),
            admitted("b-1", 0),
            refused("b-1", 1, "held", ("dn_e", "a")),
            completed("a-1", 3),
            # The LAST refusal is the diagnosis, and its obstacle list length
            # is how many candidate routes were blocked.
            refused("b-1", 4, "unsafe", ("dn_e", "a"), ("up_e", "a")),
        )
    )
    assert m.status == "stalled"
    assert m.stalls == (Stall("b-1", "unsafe", "dn_e", "a", 2),)
    assert m.makespan is None  # stalled runs are excluded from makespan aggregates
    assert m.completed == ("a-1",)  # what did finish is still reported


def test_a_request_never_attempted_stalls_as_queued() -> None:
    m = metrics(trace(submitted("a-2", 0), admitted("a-2", 0)))
    assert m.stalls == (Stall("a-2", "queued", "", "", 0),)


def test_a_rejected_request_is_not_a_stall() -> None:
    m = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            {
                "time": 1.0,
                "event": "request_rejected",
                "id": "a-1",
                "reason": "unreachable",
            },
        )
    )
    assert m.stalls == ()
    assert m.makespan is None  # nothing completed, so there is no span


def test_a_rejected_request_is_visible_in_the_status() -> None:
    # A rejection is work the run never attempted, and dropping it makes the
    # makespan SHORTER — so a run that quietly rejected half its workload
    # would outscore one that did all of it. The status has to say so.
    dropped = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            submitted("b-1", 0),
            admitted("b-1", 0),
            {
                "time": 1.0,
                "event": "request_rejected",
                "id": "b-1",
                "reason": "no_entry",
            },
            completed("a-1", 3),
        )
    )
    assert dropped.rejected == ("b-1",)
    assert dropped.status == "rejected"
    assert dropped.stalls == ()  # a rejection is not a stall
    assert dropped.makespan == 3  # and it flatters the makespan, hence the status


def test_mean_latency_is_a_float_even_when_the_mean_is_exact() -> None:
    # statistics.mean hands back an int when the mean divides exactly, which
    # would make the field's type depend on the data and the sweep's JSONL
    # column mixed int/float across rows.
    m = metrics(
        trace(
            submitted("a-1", 0),
            admitted("a-1", 0),
            submitted("b-1", 0),
            admitted("b-1", 0),
            completed("a-1", 1),
            completed("b-1", 3),
        )
    )
    assert m.mean_latency == 2.0
    assert isinstance(m.mean_latency, float)


# The events every metric derives from (bench/METRICS.md). The `time` stamp
# is on every line — the tap's own, not an event — so no timing event appears
# here.
METRIC_FEEDING_EVENTS = [
    "request_submitted",
    "request_admitted",
    "request_completed",
    "grant_refused",
    "lock_granted",
    "lock_released",
    "move",
]


@pytest.mark.parametrize("event", METRIC_FEEDING_EVENTS)
def test_the_trace_is_load_bearing(event: str) -> None:
    """Suppressing any metric-feeding event breaks a metric. This is the
    guarantee that keeps the event inventory honest: an event nothing reads
    would rot quietly, and none of these can.

    The scenario has to be one that both moves trains and stalls a request,
    or the stall diagnosis has nothing to lose.
    """
    layout, _roster, scenario = load("single-track-meet/arrival-obstruction")
    full = run(layout, _roster, scenario, Incremental)
    suppressed = "".join(
        line + "\n" for line in full.splitlines() if json.loads(line)["event"] != event
    )
    assert len(parse(suppressed)) < len(parse(full)), f"{event} was never emitted"

    try:
        degraded = metrics(suppressed)
    except ValueError:
        return  # a metric that cannot be derived at all is the loudest break
    assert degraded != metrics(full), f"suppressing '{event}' changed no metric"


def test_metrics_over_a_real_run_agree_with_the_trace() -> None:
    layout, _roster, scenario = load("crossover-yard/meet")
    m = metrics(run(layout, _roster, scenario, Incremental))
    trace_text = run(layout, _roster, scenario, Incremental)
    assert m.status == "ok"
    assert set(m.completed) == {
        line["id"] for line in events(trace_text, "request_completed")
    }
    assert m.makespan == max(
        line["time"] for line in events(trace_text, "request_completed")
    )
    # Every train's standing lock is in the trace from startup, so every
    # starting block shows utilization even before anything moves.
    assert all(block in m.utilization for block in ("yard_w", "up_e"))
