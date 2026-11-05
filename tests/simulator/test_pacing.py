"""The simulator's pacing and termination (#39).

The layout interface owns time (ADR-0009, ADR-0047) and this binding is the
simulator: an accepted `move` schedules its sensor readings on fixed
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

from tc49.bench.runner import placement, powered
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
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

SETTLED = "tc49/layout/state/settled/sensor/"


def build() -> tuple[InProcessBus, Clock, Simulator, StringIO]:
    """The binding under test on a bus of its own, its steel stood where the
    scenario document stands it, with the trace tap in front of it so the
    run's whole record — the power it states from its constructor and the
    ON that powers it included — is on the stream."""
    layout, _roster, scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    out = StringIO()
    TraceTap(bus, out, clock)
    simulator = powered(
        bus,
        Simulator(
            bus,
            layout,
            clock,
            placement(scenario.trains),
            transit_s=TRANSIT_S,
            clear_s=CLEAR_S,
        ),
    )
    return bus, clock, simulator, out


def readings(bus: InProcessBus, clock: Clock) -> list[tuple[float, str, str]]:
    """Every settled reading with the run clock's reading at the moment it was
    published: which sensor read what, and when. The topic's address is the
    payload's, as on `layout`'s row (#1168)."""
    seen: list[tuple[float, str, str]] = []

    def heard(topic: str, payload: Payload) -> None:
        assert set(payload) == {"at", "addr", "occupancy"}
        assert topic == f"{SETTLED}{payload['addr']}"
        assert payload["at"] == clock.now
        seen.append((clock.now, str(payload["addr"]), str(payload["occupancy"])))

    bus.subscribe(f"{SETTLED}#", heard)
    return seen


def move(bus: InProcessBus, train: str, transit: str, into: str) -> None:
    """One command as the driver publishes it, delivered on its own drain."""
    connection, _, name = transit.partition(".")
    bus.publish(
        "tc49/layout/move",
        {"train": train, "connection": connection, "transit": name, "into": into},
    )
    bus.drain()


def both_trains_move(bus: InProcessBus) -> None:
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


def test_one_move_reads_its_sensors_at_the_four_times() -> None:
    """Out of `yard_w` through `yard_w.B`, into `dn_w` through `dn_w.A`: what
    the sensors at those two ends read on steel. The head reaches `dn_w.A` after
    the transit delay and the tail clears `yard_w.B` a clearing delay later, the
    only order the physical railroad can produce (ADR-0047), and each on its own
    span rather than both on one (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()

    assert seen == [
        (0.0, "yard_w.B", "occupied"),
        (TRANSIT_S, "dn_w.A", "occupied"),
        (TRANSIT_S + CLEAR_S, "yard_w.B", "clear"),
        (TRANSIT_S + 2 * CLEAR_S, "dn_w.A", "clear"),
        (TRANSIT_S + 2 * CLEAR_S, "dn_w.B", "occupied"),
    ]


def run_to(simulator: Simulator, clock: Clock, at: float) -> None:
    """The live loop until the run clock reads `at`, with what is due then
    fired: the wait is cut to the period, and no second of anything is spent."""
    simulator.run_live(
        at - clock.now, sleep=lambda _: None, stop=lambda: clock.now >= at
    )


def test_a_second_move_starts_once_the_head_is_in() -> None:
    """At `t + transit_s` the train stands in `dn_w`, so its next move starts:
    out through the first move's far sensor, which reads occupied at once. The
    first move's last row still clears `dn_w.A` and does not read `dn_w.B`
    occupied again, the train having gone (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    run_to(simulator, clock, TRANSIT_S)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    simulator.run()

    second = [each for each in seen if each[0] >= TRANSIT_S]
    assert second == [
        (TRANSIT_S, "dn_w.A", "occupied"),
        (TRANSIT_S, "dn_w.B", "occupied"),
        (TRANSIT_S + CLEAR_S, "yard_w.B", "clear"),
        (2 * TRANSIT_S, "dn_e.A", "occupied"),
        (TRANSIT_S + 2 * CLEAR_S, "dn_w.A", "clear"),
        (2 * TRANSIT_S + CLEAR_S, "dn_w.B", "clear"),
        (2 * TRANSIT_S + 2 * CLEAR_S, "dn_e.A", "clear"),
        (2 * TRANSIT_S + 2 * CLEAR_S, "dn_e.B", "occupied"),
    ]


def test_a_move_while_the_train_is_rolling_is_dropped() -> None:
    """Halfway over the transit the head is not in: the second `move` reads
    nothing and leaves the first to run as it would have (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    run_to(simulator, clock, TRANSIT_S / 2)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    simulator.run()

    assert [addr for _at, addr, _level in seen] == [
        "yard_w.B",
        "dn_w.A",
        "yard_w.B",
        "dn_w.A",
        "dn_w.B",
    ]


def test_a_train_stopped_at_far_moved_out_through_far_reads_nothing_at_the_start() -> (
    None
):
    """`dn_w.B` already reads occupied, and an equal reading is not published
    again. It reads clear once the tail is past (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()
    started = clock.now
    before = len(seen)

    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    simulator.run()

    assert seen[before:] == [
        (started + TRANSIT_S, "dn_e.A", "occupied"),
        (started + TRANSIT_S + CLEAR_S, "dn_w.B", "clear"),
        (started + TRANSIT_S + 2 * CLEAR_S, "dn_e.A", "clear"),
        (started + TRANSIT_S + 2 * CLEAR_S, "dn_e.B", "occupied"),
    ]


def test_a_train_stopped_at_far_moved_out_by_its_entry_reads_both_clear_together() -> (
    None
):
    """Back out through `dn_w.A`, the end it came in by: that sensor reads
    occupied at the start, and both of the block's sensors read clear once the
    tail is past, the train having stood over `dn_w.B` until then (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()
    started = clock.now
    before = len(seen)

    move(bus, "freight_1", "west_ladder.to_dn", "yard_w")
    simulator.run()

    assert seen[before:] == [
        (started, "dn_w.A", "occupied"),
        (started + TRANSIT_S, "yard_w.B", "occupied"),
        (started + TRANSIT_S + CLEAR_S, "dn_w.B", "clear"),
        (started + TRANSIT_S + CLEAR_S, "dn_w.A", "clear"),
        (started + TRANSIT_S + 2 * CLEAR_S, "yard_w.B", "clear"),
        (started + TRANSIT_S + 2 * CLEAR_S, "yard_w.A", "occupied"),
    ]


def test_a_train_turned_back_as_its_head_comes_in_keeps_its_entry_occupied() -> None:
    """Out through `dn_w.A` the moment its head is over it: the first move's
    last row would read clear a sensor the train is leaving by, so it does not
    fire, and `dn_w.A` reads clear with the second move's tail (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    run_to(simulator, clock, TRANSIT_S)
    move(bus, "freight_1", "west_ladder.to_dn", "yard_w")
    simulator.run()

    assert [each for each in seen if each[1] == "dn_w.A"] == [
        (TRANSIT_S, "dn_w.A", "occupied"),
        (2 * TRANSIT_S + CLEAR_S, "dn_w.A", "clear"),
    ]


def test_a_live_run_sleeps_the_spans_a_batch_run_jumps() -> None:
    """One queue and one loop body, with the wait injected: batch advances
    the clock to the next scheduled event and live sleeps its way there, so
    the sensors land on the same stamps and the trace is the same trace. That
    is what lets ADR-0009 stand — nothing on the bus can tell the modes
    apart, and a benchmark number is a statement about the railroad rather
    than about the machine it ran on."""
    trace, slept = live_run(4)

    assert slept == [0.0, TRANSIT_S, CLEAR_S, CLEAR_S]
    assert trace == batch_run()


def test_a_batch_run_stops_at_quiescence_and_not_one_event_before() -> None:
    """Nothing outside the simulator speaks here, so the queue is the whole
    of what is coming: the run ends when it empties — nothing scheduled,
    nothing pending, no train rolling (BENCHMARKS.md, termination) — and not
    at the first quiet moment. Two trains rolling means the run passes a
    point where one has arrived and the other has not, and it does not stop
    there: every reading fires, and the clock ends at the last of them, each
    train's far sensor (#1170)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

    both_trains_move(bus)
    simulator.run()

    assert sorted(addr for _at, addr, _level in seen) == sorted(
        ["yard_w.B", "dn_w.A", "yard_w.B", "dn_w.A", "dn_w.B"]
        + ["up_e.B", "yard_e.A", "up_e.B", "yard_e.A", "yard_e.B"]
    )
    assert seen[-1][0] == TRANSIT_S + 2 * CLEAR_S
    assert clock.now == TRANSIT_S + 2 * CLEAR_S


def test_a_run_that_ended_left_no_train_rolling() -> None:
    """The third of the three conditions, which an empty queue alone does not
    show: a train whose tail has cleared is standing again, so a further
    command for it is acted on rather than refused as mid-move (ADR-0047)."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    simulator.run()

    seen.clear()
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    simulator.run()

    assert ("dn_e.A", "occupied") in [(addr, level) for _at, addr, level in seen]


def test_a_live_run_keeps_waiting_after_the_last_train_has_arrived() -> None:
    """Where batch stops, live waits: quiescence is the simulator's pacing and
    not the contract, and a binding driving track never terminates at all
    (SYSTEM.md, layout interface). Ten turns past the last sensor it is still
    polling on its period, and the trace is the batch run's — waiting is not
    an event, and nothing is invented to fill the quiet."""
    trace, slept = live_run(14)

    assert slept == [0.0, TRANSIT_S, CLEAR_S, CLEAR_S] + [PERIOD_S] * 10
    assert trace == batch_run()


def test_a_move_this_railroad_has_no_transit_for_schedules_nothing() -> None:
    """A command that cannot be acted on is dropped where it is read
    (tests/simulator/test_reading.py); what it costs the run is asserted
    here, and it is nothing at all. No event is queued, so the clock never
    moves and the batch run is over before it started — quiescence is the
    queue's emptiness and not a timeout, so a run with nothing to do stops
    rather than waiting out a budget."""
    bus, clock, simulator, _out = build()
    seen = readings(bus, clock)

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
