"""The apps killed and brought back up against the rows the broker kept
(#151, #123).

The whole of (a) end to end: an evening's running, the processes gone with
nothing closed or flushed, and a fresh assembly handed exactly the retained
rows a broker would still be holding — which is what a restart really finds
(ADR-0059, decision 3). It comes up where the railroad stopped instead of
where the scenario document starts it.

What is adopted is placement, the crossing hint and facing, and nothing
else. The lock table comes back one block per train, the queue comes back
empty and no request id resumes (ADR-0033) — the per-app tests pin those
(tests/dispatcher/test_adoption.py, tests/scheduler/test_scheduler.py); this
one is about the three of them agreeing after a real run.

And it comes up **held** (#154): the picture is where the last run was cut
off, not where the railroad now stands, so nothing moves until a person has
looked and released it.

The simulator is not among them. Its steel is on no topic, so the broker
holds none of it and a restarted binding comes up with an empty layout while
the dispatcher comes up with the picture it left — which is what
`tc49/simulator/__main__.py` says it costs. Here the second assembly stands
its trains from the scenario document, as every harness run does; what is
under test is what the *adopting* apps make of the rows, and the simulator's
own memory is `tests/simulator/test_placement.py`'s.
"""

from collections.abc import Callable
from typing import Any

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.bus import Payload
from tc49.lib.layout import block_of
from tests.harness import RUN_WANTED, events, load

WANTED = "tc49/schedule/request_wanted"
PLACED = "tc49/dispatch/placement_wanted"


def tick_until(assembly: Assembly, done: Callable[[], bool], limit: int = 50) -> None:
    """Run the live loop, no waiting, until `done` or the tick limit."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return done() or ticks > limit

    assembly.simulation.run_live(3600.0, sleep=lambda _: None, stop=stop)


def release(assembly: Assembly) -> None:
    """The press a restored session waits for: it comes up held, and the
    operator releases it once they have looked at the railroad (#154)."""
    assembly.bus.publish(RUN_WANTED, {"run": "running"})
    assembly.bus.drain()


def picture(assembly: Assembly) -> dict[str, Any]:
    return events(assembly.trace, "allocation")[-1]


def facing(assembly: Assembly) -> dict[str, str]:
    return events(assembly.trace, "facing")[-1]["facing"]


def dragged() -> Assembly:
    """A live run on `crossover-yard/meet` with `freight_1` on its way across
    the railroad: the timetable is off, so a drag is what moves it."""
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = assemble_live(layout, _roster, scenario.trains)
    assembly.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    assembly.bus.drain()
    return assembly


def cut_off_crossing() -> Assembly:
    """That run cut off two blocks along: the train has left the block the
    scenario places it in, and the grant that took it out of the last one has
    not been sensed yet — so it is also crossing, which is the placement the
    retained picture has the least to say about and the most to mark."""
    assembly = dragged()
    tick_until(assembly, lambda: len(events(assembly.trace, "block_occupied")) >= 2)
    return assembly


def run_to_a_standstill() -> Assembly:
    """That run left to finish: the train is parked, and parked somewhere the
    scenario document does not put it."""
    assembly = dragged()
    tick_until(assembly, lambda: bool(events(assembly.trace, "request_completed")))
    return assembly


def kept(assembly: Assembly) -> dict[str, Payload]:
    """What the broker would still be holding: every retained row the run put
    there, which is what an app restarted under it is handed."""
    return assembly.bus.last_values


def restarted(held: dict[str, Payload]) -> Assembly:
    """The apps again, on the same railroad, against those rows."""
    layout, _roster, scenario = load("crossover-yard/meet")
    return assemble_live(layout, _roster, scenario.trains, retained=held)


def test_a_restarted_run_comes_up_where_the_railroad_stopped() -> None:
    """Both apps adopt, and they agree: the picture the second run opens on
    is the placement and the crossing hint the first one left, and the arrow
    points where it pointed."""
    stopped = cut_off_crossing()
    was = picture(stopped)
    assert was["crossing"], "the run was meant to stop with a train crossing"
    assert was["trains"] != {"express_2": "up_e", "freight_1": "yard_w"}

    again = restarted(kept(stopped))
    again.bus.drain()

    assert picture(again)["trains"] == was["trains"]
    assert picture(again)["crossing"] == was["crossing"]
    assert facing(again) == facing(stopped)


def test_the_restarted_run_carries_no_route_and_no_request() -> None:
    """It comes up knowing where the trains are and moving nothing on its
    own: the request the first run was working is not in the second's
    picture, and the crossing entry is a hint with no route behind it."""
    stopped = cut_off_crossing()
    assert picture(stopped)["requests"], "the run was meant to stop mid-request"

    again = restarted(kept(stopped))
    again.bus.drain()

    assert picture(again)["requests"] == []
    assert events(again.trace, "route_chosen") == []
    assert picture(again)["locks"] == {
        block: train for train, block in picture(again)["trains"].items()
    }


def test_a_restarted_run_moves_nothing_until_it_is_released() -> None:
    """It comes up **held** (#154). The picture says where the last run
    believed the railroad was and nobody has looked at it since, so the
    second run admits the work and grants none of it: the boundaries pass, no
    route is chosen, and the release is what starts it."""
    stopped = run_to_a_standstill()

    again = restarted(kept(stopped))
    again.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_w.B"]})
    again.bus.drain()
    tick_until(again, lambda: False, limit=3)

    assert events(again.trace, "run")[-1]["run"] == "held"
    assert events(again.trace, "request_admitted"), "held blocks commitment only"
    assert events(again.trace, "route_chosen") == []

    release(again)
    tick_until(again, lambda: bool(events(again.trace, "route_chosen")))

    assert events(again.trace, "route_chosen")


def test_a_train_restored_mid_crossing_is_resolved_by_placing_it() -> None:
    """What the crossing entry is *for* (#154).

    Facing follows the grant and the lock table follows the sensor, so a
    session cut off mid-crossing restores a train whose facing names one block
    and whose placement names the one behind it, with no route restored to
    carry it on. The way out is the person: they drive it out of the
    connection by hand if it really is stuck between, and place it at
    whichever end it now stands. That clears the crossing entry, and the
    railroad runs from there.
    """
    stopped = cut_off_crossing()

    layout, _roster, _scenario = load("crossover-yard/meet")
    again = restarted(kept(stopped))
    again.bus.drain()
    transit = picture(again)["crossing"]["freight_1"]
    connection, _, name = transit.partition(".")
    behind = picture(again)["trains"]["freight_1"]
    ahead = next(
        block_of(end)
        for end in layout.connections[connection].transits[name]
        if block_of(end) != behind
    )

    again.bus.publish(PLACED, {"train": "freight_1", "block": ahead})
    again.bus.drain()

    assert picture(again)["crossing"] == {}
    assert picture(again)["trains"]["freight_1"] == ahead
    assert events(again.trace, "train_placed")[-1]["block"] == ahead

    release(again)
    again.bus.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})
    again.bus.drain()
    tick_until(again, lambda: bool(events(again.trace, "request_completed")))

    assert events(again.trace, "request_rejected") == []
    assert events(again.trace, "request_completed")
