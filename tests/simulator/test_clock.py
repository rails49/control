"""The simulator's fast clock: the row `layout` says, timed off the run clock
(ADR-0090, decision 1).

Once a second of run clock, in batch and live alike, so a live run and a
batch run say the same rows at the same stamps and a replay is the same run.
A batch run's seconds are the run clock's to jump; the clock is no event, so
a run still ends at quiescence and nothing waits on it.

Driven at the layout interface with a bus and a railroad, as the pacing is:
nothing here sleeps, the live loop's wait being injected.
"""

from tc49.bench.runner import placement, powered
from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.clock_row import CLOCK, CLOCK_WANTED, FastClockRow
from tc49.lib.fast_clock import FastClock, KeptClock
from tc49.lib.inventory import leaf
from tc49.simulator import Simulator
from tests.harness import load

TRANSIT_S = 3.0
CLEAR_S = 2.5
"""Short, and the second not a whole number, so a run's last sensor falls
between two beats."""

SEVEN = 7 * 3600
"""07:00, where the clock under test starts."""

type Said = list[tuple[float, str, object]]
"""What the bus carried: the run clock's reading, the leaf, and a clock
row's time or a sensor's block."""


def build(
    speed_up: float = 1.0, kept: list[KeptClock] | None = None
) -> tuple[InProcessBus, Simulator, Said]:
    """The binding on a bus of its own holding a fast clock started at 07:00
    on its run clock, and everything it says from the first beat on."""
    layout, _roster, scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    row = FastClockRow(
        bus,
        FastClock(SEVEN, speed_up, clock.now),
        KeptClock(SEVEN, speed_up),
        lambda: clock.now,
        (kept if kept is not None else []).append,
    )
    simulator = powered(
        bus,
        Simulator(
            bus,
            layout,
            clock,
            placement(scenario.trains),
            transit_s=TRANSIT_S,
            clear_s=CLEAR_S,
            fast=row,
        ),
    )
    said: Said = []
    bus.subscribe(
        CLOCK,
        lambda topic, payload: said.append((clock.now, leaf(topic), payload["time"])),
    )
    for topic in ("tc49/layout/block_occupied", "tc49/layout/block_vacated"):
        bus.subscribe(
            topic,
            lambda topic, payload: said.append(
                (clock.now, leaf(topic), payload["block"])
            ),
        )
    bus.publish(
        "tc49/layout/move",
        {
            "train": "freight_1",
            "connection": "west_ladder",
            "transit": "to_dn",
            "into": "dn_w",
        },
    )
    return bus, simulator, said


def live(turns: int) -> tuple[Said, list[float]]:
    """The same run live for `turns` turns, and every wait it asked for."""
    _bus, simulator, said = build()
    slept: list[float] = []
    taken = 0

    def stop() -> bool:
        nonlocal taken
        taken += 1
        return taken > turns

    simulator.run_live(1000.0, sleep=slept.append, stop=stop)
    return said, slept


def test_a_batch_run_says_the_clock_once_a_second_of_run_clock() -> None:
    """From the run's start to its last sensor and no further: the clock is
    no event, so the run ends at quiescence as it did without one."""
    _bus, simulator, said = build()
    simulator.run()
    assert said == [
        (0.0, "clock", SEVEN),
        (1.0, "clock", SEVEN + 1),
        (2.0, "clock", SEVEN + 2),
        (3.0, "clock", SEVEN + 3),
        (3.0, "block_occupied", "dn_w"),
        (4.0, "clock", SEVEN + 4),
        (5.0, "clock", SEVEN + 5),
        (5.5, "block_vacated", "yard_w"),
    ]


def test_the_clock_runs_at_its_speed_up_on_the_run_clock() -> None:
    _bus, simulator, said = build(speed_up=8.0)
    simulator.run()
    times = [what for _at, leaf_, what in said if leaf_ == "clock"]
    assert times == [SEVEN + 8 * second for second in range(6)]


def test_a_live_run_says_the_rows_a_batch_run_says_at_the_same_stamps() -> None:
    """Each wait cut to the next beat as it is to the next sensor, so the
    live record is the batch one and a replay stays the same run."""
    _bus, simulator, batch = build()
    simulator.run()
    said, slept = live(6)
    assert said == batch
    assert slept == [1.0, 1.0, 1.0, 1.0, 1.0, 0.5]


def test_a_clock_set_is_said_at_once_and_counted_on_the_run_clock() -> None:
    """Taken as `layout` takes it (ADR-0090, decision 2), and kept with the
    railroad."""
    kept: list[KeptClock] = []
    bus, simulator, said = build(kept=kept)
    bus.publish(CLOCK_WANTED, {"time": 9 * 3600, "speed_up": 2})
    simulator.run()
    times = [(at, what) for at, leaf_, what in said if leaf_ == "clock"]
    assert times[:3] == [(0.0, SEVEN), (0.0, 9 * 3600), (1.0, 9 * 3600 + 2)]
    assert kept == [KeptClock(9 * 3600, 2.0)]


def test_a_simulator_given_no_clock_says_none() -> None:
    """What the research harness builds: its traces are what they were."""
    layout, _roster, scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    simulator = powered(bus, Simulator(bus, layout, clock, placement(scenario.trains)))
    said: list[object] = []
    bus.subscribe(CLOCK, lambda _topic, payload: said.append(payload))
    turns = iter(range(3))
    simulator.run_live(1.0, sleep=lambda _s: None, stop=lambda: next(turns, -1) < 0)
    simulator.run()
    assert said == []


def test_a_live_run_given_a_real_clock_keeps_to_it_where_a_turn_runs_long() -> None:
    """Deployed, a turn costs more than the wait it asked for, and a run clock
    advanced by the waits alone would fall behind: the clock is said once a
    *real* second (ADR-0090, decision 1), so the loop catches the run clock up
    to the real one, and says the clock once however many beats were
    passed."""
    _bus, simulator, said = build()
    real = 0.0

    def sleep(seconds: float) -> None:
        nonlocal real
        real += 2 * seconds  # every turn takes twice what it waits

    turns = iter(range(2))
    simulator.run_live(
        1000.0,
        sleep=sleep,
        stop=lambda: next(turns, -1) < 0,
        monotonic=lambda: real,
    )
    assert [(at, what) for at, leaf_, what in said if leaf_ == "clock"] == [
        (0.0, SEVEN),
        (2.0, SEVEN + 2),
        (4.0, SEVEN + 4),
    ]
