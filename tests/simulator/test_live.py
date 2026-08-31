"""The live run loop, at the assembly-over-the-bus seam (#69).

The same assembly the bench CLI wires, driven through `run_live` with an
injected time source — no test here sleeps. Batch mode's own behaviour is
pinned elsewhere (tests/bench/test_benchmarks.py): these tests are about
what live mode adds, which is wall-clock pacing and the refusal to stop.
"""

from tests.harness import build, events, load


def run_live_for(turns: int, period_s: float) -> tuple[str, list[float]]:
    """A live session over crossover-yard/meet, stopped after `turns` turns;
    the trace and every sleep the loop asked for."""
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = build(layout, _roster, scenario)
    slept: list[float] = []
    assembly.simulator.run_live(
        period_s,
        sleep=slept.append,
        stop=lambda: len(slept) >= turns,
    )
    return assembly.trace, slept


def test_an_idle_wait_is_paced_by_the_period() -> None:
    """Nothing is due for thirty simulated seconds — the first transit delay
    — so the loop wakes on its period to poll for commands, and sleeps no
    longer than that."""
    _trace, slept = run_live_for(5, period_s=0.25)
    assert slept == [0.25] * 5


def test_a_sleep_is_cut_to_the_next_scheduled_event() -> None:
    """A sensor fires at the time batch mode would stamp it: the wait before
    it is trimmed to land on the event exactly, never over it."""
    _trace, slept = run_live_for(3, period_s=20.0)
    # 20 s, then the 10 s remainder to the first sensors at 30 s, then the
    # next full period toward the pair at 60 s.
    assert slept == [20.0, 10.0, 20.0]


def test_a_live_session_survives_quiescence() -> None:
    """Batch mode stops once nothing is scheduled; live mode keeps waiting
    until told to stop."""
    layout, _roster, scenario = load("crossover-yard/meet")
    batch = build(layout, _roster, scenario)
    batch.simulator.run()

    trace, slept = run_live_for(60, period_s=1000.0)
    completed = {line["id"] for line in events(trace, "request_completed")}
    assert completed == {
        line["id"] for line in events(batch.trace, "request_completed")
    }
    assert len(slept) == 60  # still waiting long after the last sensor


def test_the_railroad_runs_in_live_mode_as_it_does_in_batch() -> None:
    """Same assembly, same scenario, same events at the same stamps — pacing
    is the whole difference, so the traces agree byte for byte."""
    layout, _roster, scenario = load("crossover-yard/meet")
    batch = build(layout, _roster, scenario)
    batch.simulator.run()

    trace, _ = run_live_for(60, period_s=1000.0)
    assert trace == batch.trace
