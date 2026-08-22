"""The live run loop, at the assembly-over-the-bus seam (#69).

The same assembly the bench CLI wires, driven through `run_live` with an
injected time source — no test here sleeps. Batch mode's own behaviour is
pinned elsewhere (tests/bench/test_benchmarks.py): these tests are about
what live mode adds, which is wall-clock pacing and the refusal to stop.
"""

from tests.harness import build, events, load


def run_live_for(ticks: int, period_s: float = 0.5) -> tuple[str, list[float]]:
    """A live session over crossover-yard/meet, stopped after `ticks` ticks;
    the trace and every sleep the loop asked for."""
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = build(layout, _roster, scenario)
    slept: list[float] = []
    assembly.simulator.run_live(
        period_s,
        sleep=slept.append,
        stop=lambda: len(slept) >= ticks,
    )
    return assembly.trace, slept


def test_ticks_arrive_on_the_timer_and_stay_deterministic_integers() -> None:
    trace, slept = run_live_for(5, period_s=0.25)
    assert slept == [0.25] * 5  # one sleep of the period before every tick
    assert [line["boundary"] for line in events(trace, "boundary")] == [0, 1, 2, 3, 4]


def test_a_live_session_survives_quiescence() -> None:
    """Batch mode stops once the schedule is exhausted and a tick's cascade
    produces no command; live mode keeps ticking until told to stop."""
    layout, _roster, scenario = load("crossover-yard/meet")
    batch = build(layout, _roster, scenario)
    batch.simulator.run()
    quiescent_at = events(batch.trace, "boundary")[-1]["boundary"]

    trace, _ = run_live_for(quiescent_at + 20)
    completed = {line["id"] for line in events(trace, "request_completed")}
    assert completed == {
        line["id"] for line in events(batch.trace, "request_completed")
    }
    assert events(trace, "boundary")[-1]["boundary"] == quiescent_at + 19


def test_the_railroad_runs_in_live_mode_as_it_does_in_batch() -> None:
    """Same assembly, same scenario, same events — pacing is the whole
    difference, so the trace agrees with batch mode line for line up to
    the tick where batch mode stops."""
    layout, _roster, scenario = load("crossover-yard/meet")
    batch = build(layout, _roster, scenario)
    batch.simulator.run()

    trace, _ = run_live_for(len(events(batch.trace, "boundary")))
    assert trace == batch.trace
