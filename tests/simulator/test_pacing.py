"""The simulator's pacing and termination (#39).

The layout interface owns time (ADR-0009, ADR-0047) and this binding is the
milestone-1 one: an accepted `move` schedules its two sensor events on fixed
delays of its own, a batch run jumps the clock event to event and stops at
quiescence, and a live run sleeps the same spans and never stops. Everything
downstream is timed off those stamps — a benchmark's makespan, the order two
trains meet in — so a regression here surfaces as an off-by-one somewhere
far from its cause, which is why it is pinned at the seam that owns it.

Driven at the layout interface with a bus and a scenario rather than an
assembly: commands in, sensor events out, and the run clock read off the
moment each one is published. No test here sleeps — the live loop's wait is
injected, and what it asked for is what is asserted.
"""

from io import StringIO

from tc49.bench.runner import placement
from tc49.lib.bus import Bus
from tc49.lib.clock import Clock
from tc49.lib.inventory import leaf
from tc49.lib.trace import TraceTap
from tc49.simulator import Simulator
from tests.harness import load

TRANSIT_S = 30.0
CLEAR_S = 20.0
"""The two delays, deliberately unequal: with one number the head's span and
the tail's could be swapped and nothing here would see it."""

PERIOD_S = 1000.0
"""Longer than either delay, so a live wait is cut to the next scheduled
event and a turn is exactly "the next thing the railroad does"."""

SENSORS = ("tc49/layout/block_occupied", "tc49/layout/block_vacated")


def build() -> tuple[Bus, Clock, Simulator, StringIO]:
    """The binding under test on a bus of its own, its steel stood where the
    scenario document stands it, with the trace tap in front of it so the
    run's whole record — the power it states from its constructor included —
    is on the stream."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = Bus()
    clock = Clock()
    out = StringIO()
    TraceTap(bus, out, clock)
    simulator = Simulator(
        bus,
        layout,
        clock,
        placement(scenario.trains),
        transit_s=TRANSIT_S,
        clear_s=CLEAR_S,
    )
    return bus, clock, simulator, out


def stamped(bus: Bus, clock: Clock) -> list[tuple[float, str, str]]:
    """Every sensor event with the run clock's reading at the moment it was
    published: which detector spoke about which block, and when."""
    seen: list[tuple[float, str, str]] = []
    for topic in SENSORS:
        bus.subscribe(
            topic,
            lambda topic, payload: seen.append(
                (clock.now, leaf(topic), str(payload["block"]))
            ),
        )
    return seen


def move(bus: Bus, train: str, transit: str, into: str) -> None:
    """One command as the driver publishes it, delivered on its own drain."""
    connection, _, name = transit.partition(".")
    bus.publish(
        "tc49/layout/move",
        {"train": train, "connection": connection, "transit": name, "into": into},
    )
    bus.drain()


def both_trains_move(bus: Bus) -> None:
    """The two trains the scenario stands, each given a transit the other
    does not touch: freight_1 out of the west yard onto the down line,
    express_2 off the up main into the east yard. Both are accepted at once,
    so the run has two trains rolling and the queue's ordering among equal
    stamps is doing work."""
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    move(bus, "express_2", "east_ladder.from_up", "yard_e")


def batch_run() -> str:
    """That pair of moves run to quiescence in batch, and the trace of it."""
    bus, _clock, simulator, out = build()
    both_trains_move(bus)
    simulator.run()
    return out.getvalue()


def live_run(turns: int) -> tuple[str, list[float]]:
    """The same pair run live for `turns` turns, the trace and every wait the
    loop asked for. The wait is injected: the clock the loop advances is the
    run clock, and no second of anything is spent here."""
    bus, _clock, simulator, out = build()
    both_trains_move(bus)
    slept: list[float] = []
    taken = 0

    def stop() -> bool:
        nonlocal taken
        taken += 1
        return taken > turns

    simulator.run_live(PERIOD_S, sleep=slept.append, stop=stop)
    return out.getvalue(), slept


def test_an_accepted_move_schedules_its_two_sensors_on_the_two_delays() -> None:
    """The whole of what one move does: the head reaches the far detector
    after the transit delay and the tail clears the near one a clearing delay
    later — occupied then vacated, the only order the physical railroad can
    produce (ADR-0047), and each on its own span rather than both on one."""
    bus, clock, simulator, _out = build()
    seen = stamped(bus, clock)

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()

    assert seen == [
        (TRANSIT_S, "block_occupied", "dn_w"),
        (TRANSIT_S + CLEAR_S, "block_vacated", "yard_w"),
    ]


def test_a_live_run_sleeps_the_spans_a_batch_run_jumps() -> None:
    """One queue and one loop body, with the wait injected: batch advances
    the clock to the next scheduled event and live sleeps its way there, so
    the sensors land on the same stamps and the trace is the same trace. That
    is what lets ADR-0009 stand — nothing on the bus can tell the modes
    apart, and a benchmark number is a statement about the railroad rather
    than about the machine it ran on."""
    trace, slept = live_run(2)

    assert slept == [TRANSIT_S, CLEAR_S]
    assert trace == batch_run()


def test_a_batch_run_stops_at_quiescence_and_not_one_event_before() -> None:
    """Nothing outside the simulator speaks here, so the queue is the whole
    of what is coming: the run ends when it empties — nothing scheduled,
    nothing pending, no train rolling (BENCHMARKS.md, termination) — and not
    at the first quiet moment. Two trains rolling means the run passes a
    point where one has arrived and the other has not, and it does not stop
    there: all four events fire, and the clock ends at the last one."""
    bus, clock, simulator, _out = build()
    seen = stamped(bus, clock)

    both_trains_move(bus)
    simulator.run()

    assert seen == [
        (TRANSIT_S, "block_occupied", "dn_w"),
        (TRANSIT_S, "block_occupied", "yard_e"),
        (TRANSIT_S + CLEAR_S, "block_vacated", "yard_w"),
        (TRANSIT_S + CLEAR_S, "block_vacated", "up_e"),
    ]
    assert clock.now == TRANSIT_S + CLEAR_S


def test_a_run_that_ended_left_no_train_rolling() -> None:
    """The third of the three conditions, which an empty queue alone does not
    show: a train whose tail has cleared is standing again, so a further
    command for it is acted on rather than refused as mid-move (ADR-0047)."""
    bus, clock, simulator, _out = build()
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()

    seen = stamped(bus, clock)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    simulator.run()

    assert [(what, block) for _at, what, block in seen] == [
        ("block_occupied", "dn_e"),
        ("block_vacated", "dn_w"),
    ]


def test_a_live_run_keeps_waiting_after_the_last_train_has_arrived() -> None:
    """Where batch stops, live waits: quiescence is milestone-1 pacing and
    not the contract, and a binding driving track never terminates at all
    (SYSTEM.md, layout interface). Ten turns past the last sensor it is still
    polling on its period, and the trace is the batch run's — waiting is not
    an event, and nothing is invented to fill the quiet."""
    trace, slept = live_run(12)

    assert slept == [TRANSIT_S, CLEAR_S] + [PERIOD_S] * 10
    assert trace == batch_run()


def test_a_move_this_railroad_has_no_transit_for_schedules_nothing() -> None:
    """A command that cannot be acted on is dropped where it is read
    (tests/simulator/test_reading.py); what it costs the run is asserted
    here, and it is nothing at all. No event is queued, so the clock never
    moves and the batch run is over before it started — quiescence is the
    queue's emptiness and not a timeout, so a run with nothing to do stops
    rather than waiting out a budget."""
    bus, clock, simulator, _out = build()
    seen = stamped(bus, clock)

    move(bus, "freight_1", "north_ladder.to_dn", "dn_w")
    simulator.run()

    assert seen == []
    assert clock.now == 0.0


def test_one_scenario_run_twice_leaves_the_same_trace() -> None:
    """Reproducible by construction and not by seeding: the delays are fixed,
    the queue breaks ties by scheduling order, and the bus delivers in
    subscription order, so there is no RNG behind this to control. Two runs
    of one scenario are the same run byte for byte, which is what makes a
    committed benchmark number mean anything (BENCHMARKS.md)."""
    assert batch_run() == batch_run()
