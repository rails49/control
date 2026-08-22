"""A session killed and brought back up against the same file (#151).

The whole of (a) end to end, over the assembly `tc49 live --state` runs: an
evening's running, the process gone with nothing closed or flushed, and a
fresh assembly on the same file coming up where the railroad stopped instead
of where the scenario document starts it.

What is restored is placement, the crossing hint and facing, and nothing
else. The lock table comes back one block per train, the queue comes back
empty and no request id resumes (ADR-0033) — the per-app tests pin those
(tests/dispatcher/test_adoption.py, tests/scheduler/test_scheduler.py); this
one is about the three of them agreeing after a real run.

And it comes up **held** (#154): the picture is where the last session was
cut off, not where the railroad now stands, so nothing moves until a person
has looked and released it.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.layout import block_of
from tc49.simulator import placement_file
from tests.harness import RUN_WANTED, events, load

WANTED = "tc49/ui/request_wanted"
PLACED = "tc49/ui/placement_wanted"


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 50) -> None:
    """Run the live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def release(assembly: Assembly) -> None:
    """The press a restored session waits for: it comes up held, and the
    operator releases it once they have looked at the railroad (#154)."""
    assembly.bus.publish(RUN_WANTED, {"run": "running"})
    assembly.bus.drain()


def picture(assembly: Assembly) -> dict[str, Any]:
    return events(assembly.trace, "allocation")[-1]


def facing(assembly: Assembly) -> dict[str, str]:
    return events(assembly.trace, "facing")[-1]["facing"]


def dragged(state: Path | None) -> Assembly:
    """A live session on `crossover-yard/meet` with `freight_1` on its way
    across the railroad: the timetable is off, so a drag is what moves it."""
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = assemble_live(layout, _roster, scenario, state=state)
    assembly.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assembly.bus.drain()
    return assembly


def cut_off_crossing(state: Path | None) -> Assembly:
    """That session cut off two blocks along: the train has left the block
    the scenario places it in, and the grant that took it out of the last one
    has not been sensed yet — so it is also crossing, which is the placement
    the file has the least to say about and the most to mark."""
    assembly = dragged(state)
    tick_until(assembly, lambda: len(events(assembly.trace, "block_occupied")) >= 2)
    return assembly


def run_to_a_standstill(state: Path | None) -> Assembly:
    """That session left to finish: the train is parked, and parked somewhere
    the scenario document does not put it."""
    assembly = dragged(state)
    tick_until(assembly, lambda: bool(events(assembly.trace, "request_completed")))
    return assembly


def test_a_restarted_session_comes_up_where_the_railroad_stopped(
    tmp_path: Path,
) -> None:
    """Both apps adopt, and they agree: the picture the second session opens
    on is the placement and the crossing hint the first one left, and the
    arrow points where it pointed."""
    state = tmp_path / "session.json"
    stopped = cut_off_crossing(state)
    was = picture(stopped)
    assert was["crossing"], "the run was meant to stop with a train crossing"
    assert was["trains"] != {"express_2": "up_e", "freight_1": "yard_w"}

    layout, _roster, scenario = load("crossover-yard/meet")
    restarted = assemble_live(layout, _roster, scenario, state=state)
    restarted.bus.drain()

    assert picture(restarted)["trains"] == was["trains"]
    assert picture(restarted)["crossing"] == was["crossing"]
    assert facing(restarted) == facing(stopped)


def test_the_restarted_run_carries_no_route_and_no_request(tmp_path: Path) -> None:
    """It comes up knowing where the trains are and moving nothing on its
    own: the request the first session was running is not in the second's
    picture, and the crossing entry is a hint with no route behind it."""
    state = tmp_path / "session.json"
    stopped = cut_off_crossing(state)
    assert picture(stopped)["requests"], "the run was meant to stop mid-request"

    layout, _roster, scenario = load("crossover-yard/meet")
    restarted = assemble_live(layout, _roster, scenario, state=state)
    restarted.bus.drain()

    assert picture(restarted)["requests"] == []
    assert events(restarted.trace, "route_chosen") == []
    assert picture(restarted)["locks"] == {
        block: train for train, block in picture(restarted)["trains"].items()
    }


def test_a_restarted_session_moves_nothing_until_it_is_released(
    tmp_path: Path,
) -> None:
    """It comes up **held** (#154). The picture says where the last session
    believed the railroad was and nobody has looked at it since, so the
    second session admits the work and grants none of it: the boundaries
    pass, no route is chosen, and the release is what starts it."""
    state = tmp_path / "session.json"
    run_to_a_standstill(state)

    layout, _roster, scenario = load("crossover-yard/meet")
    restarted = assemble_live(layout, _roster, scenario, state=state)
    restarted.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    restarted.bus.drain()
    tick_until(restarted, lambda: False, limit=3)

    assert events(restarted.trace, "run")[-1]["run"] == "held"
    assert events(restarted.trace, "request_admitted"), "held blocks commitment only"
    assert events(restarted.trace, "route_chosen") == []

    release(restarted)
    tick_until(restarted, lambda: bool(events(restarted.trace, "route_chosen")))

    assert events(restarted.trace, "route_chosen")


def test_the_simulator_comes_back_to_the_same_railroad(tmp_path: Path) -> None:
    """The steel's side of it, in its own file beside the session's: the
    trains are where the last session left them, so the next move vacates the
    block they actually stand in (ADR-0030)."""
    state = tmp_path / "session.json"
    stopped = run_to_a_standstill(state)
    parked = events(stopped.trace, "block_occupied")[-1]["block"]
    assert parked != "yard_w", "the run was meant to leave the scenario's block"

    layout, _roster, scenario = load("crossover-yard/meet")
    restarted = assemble_live(layout, _roster, scenario, state=state)
    release(restarted)
    restarted.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    restarted.bus.drain()
    tick_until(restarted, lambda: bool(events(restarted.trace, "block_vacated")))

    assert placement_file(state).exists()
    assert events(restarted.trace, "block_vacated")[0]["block"] == parked


def test_a_train_restored_mid_crossing_is_resolved_by_placing_it(
    tmp_path: Path,
) -> None:
    """What the crossing entry is *for* (#154).

    Facing follows the grant and the lock table follows the sensor, so a
    session cut off mid-crossing restores a train whose facing names one block
    and whose placement names the one behind it, with no route restored to
    carry it on. The way out is the person: they drive it out of the
    connection by hand if it really is stuck between, and place it at
    whichever end it now stands. That clears the crossing entry, and the
    railroad runs from there.
    """
    state = tmp_path / "session.json"
    cut_off_crossing(state)

    layout, _roster, scenario = load("crossover-yard/meet")
    restarted = assemble_live(layout, _roster, scenario, state=state)
    restarted.bus.drain()
    transit = picture(restarted)["crossing"]["freight_1"]
    connection, _, name = transit.partition(".")
    behind = picture(restarted)["trains"]["freight_1"]
    ahead = next(
        block_of(end)
        for end in layout.connections[connection].transits[name]
        if block_of(end) != behind
    )

    restarted.bus.publish(PLACED, {"train": "freight_1", "block": ahead})
    restarted.bus.drain()

    assert picture(restarted)["crossing"] == {}
    assert picture(restarted)["trains"]["freight_1"] == ahead
    assert events(restarted.trace, "train_placed")[-1]["block"] == ahead

    release(restarted)
    restarted.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    restarted.bus.drain()
    tick_until(restarted, lambda: bool(events(restarted.trace, "request_completed")))

    assert events(restarted.trace, "request_rejected") == []
    assert events(restarted.trace, "request_completed")


def test_a_session_with_no_file_leaves_nothing_behind(tmp_path: Path) -> None:
    """The default: no path, no file, not even the simulator's. That the
    trace is byte-identical with it is
    `test_batch_trace_is_pinned_byte_identical`, which runs with no path
    because there is no other way to run."""
    run_to_a_standstill(None)

    assert list(tmp_path.iterdir()) == []
