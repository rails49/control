"""What the simulator says about track power, and what it does under it (#702).

The simulator answers the band's power presses as the layout interface does
(ADR-0070). It comes up `off`, stated from its constructor so a joining
client is served a value rather than reading one out of an absence
(ADR-0032), and publishes on `state/power` the word each answered
`power_wanted` commanded, since it has no hardware to report one. `off` is
applied at once and `draining` holds until `state/moving` reads false
(ADR-0078), the rule being `lib.power`'s and the same one the layout keeps.

While the power is not `on` no move starts: a `move` is dropped. A transit
under way follows the supply (#832): through a drain it runs to its sensors,
and at an `off` it waits and goes on at ON with the time it had left.
"""

from collections.abc import Callable

from tc49.bench.runner import placement
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import leaf
from tc49.simulator import Simulator
from tests.harness import build, events, load

POWER = "tc49/layout/state/power"
POWER_WANTED = "tc49/layout/power_wanted"
SENSORS = ("tc49/layout/block_occupied", "tc49/layout/block_vacated")

TRANSIT_S = 10.0
CLEAR_S = 5.0


def simulator() -> tuple[InProcessBus, Clock, Simulator]:
    """The binding under test on a bus of its own, its steel stood where the
    scenario document stands it."""
    layout, _roster, scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    sim = Simulator(
        bus,
        layout,
        clock,
        placement(scenario.trains),
        transit_s=TRANSIT_S,
        clear_s=CLEAR_S,
    )
    bus.drain()
    return bus, clock, sim


def heard(bus: InProcessBus) -> list[str]:
    """Every word `state/power` says from now on."""
    seen: list[str] = []
    bus.subscribe(POWER, lambda topic, payload: seen.append(str(payload["power"])))
    return seen


def press(bus: InProcessBus, payload: Payload) -> None:
    bus.publish(POWER_WANTED, payload)
    bus.drain()


def stamped(bus: InProcessBus, clock: Clock) -> list[tuple[float, str, str]]:
    """Every sensor event with the run clock's reading as it was published."""
    seen: list[tuple[float, str, str]] = []
    for topic in SENSORS:
        bus.subscribe(
            topic,
            lambda topic, payload: seen.append(
                (clock.now, leaf(topic), str(payload["block"]))
            ),
        )
    return seen


def move(bus: InProcessBus) -> None:
    """freight_1 out of the west yard onto the down line."""
    bus.publish(
        "tc49/layout/move",
        {
            "train": "freight_1",
            "connection": "west_ladder",
            "transit": "to_dn",
            "into": "dn_w",
        },
    )
    bus.drain()


def test_each_answered_press_is_the_word_on_state_power() -> None:
    """No hardware reports the supply here, so the word commanded is the
    word stated: `on`, `off` and `draining` each appear as pressed, and the
    drain ends `off` once nothing moves."""
    bus, _clock, _sim = simulator()
    seen = heard(bus)
    bus.drain()
    for word in ("on", "off", "on", "draining"):
        press(bus, {"power": word})
    bus.publish("tc49/dispatch/state/moving", {"moving": False})
    bus.drain()
    assert seen == ["off", "on", "off", "on", "draining", "off"]


def test_a_transit_under_way_at_a_cut_goes_on_at_on_with_the_time_it_had_left() -> None:
    """Started at 0 with ten seconds to run, cut at 4 and powered again
    at 20: the head is six seconds out still, so it lands at 26 and the tail
    clears a clearing delay after (ADR-0070, decision 4). Driven live with
    the wait injected; each press lands in the wait that ends at its time."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    seen = stamped(bus, clock)
    move(bus)

    presses = {4.0: "off", 20.0: "on"}

    def sleep(seconds: float) -> None:
        word = presses.pop(clock.now + seconds, None)
        if word is not None:
            bus.publish(POWER_WANTED, {"power": word})

    sim.run_live(2.0, sleep=sleep, stop=lambda: clock.now >= 40.0)

    assert seen == [
        (26.0, "block_occupied", "dn_w"),
        (26.0 + CLEAR_S, "block_vacated", "yard_w"),
    ]


def test_a_batch_run_ends_where_every_queued_event_is_waiting() -> None:
    """A batch run never cuts the power, so this is only for safety: a queue that
    cannot fire is not a queue to wait on."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    seen = stamped(bus, clock)
    move(bus)
    press(bus, {"power": "off"})
    sim.run()
    assert seen == []
    assert clock.now == 0.0


def test_a_batch_run_says_off_then_on_and_nothing_after() -> None:
    """The bench presses ON after building the simulator and before the run
    (ADR-0070, decision 2), and nothing in the run moves the value again."""
    layout, roster, scenario = load("crossover-yard/meet")
    assembly = build(layout, roster, scenario)
    assembly.simulator.run()

    said = [line["power"] for line in events(assembly.trace, "power")]
    assert said == ["off", "on"]


def test_a_transit_under_way_at_a_drain_runs_to_its_sensors() -> None:
    """A drain keeps the supply on, so a train crossing at the press rolls on
    into the block it was granted, as it does on steel (ADR-0078 decision 4):
    started at 0 and drained at 4, its head lands at 10 and its tail clears
    at 15, the times it had with the power on throughout."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    seen = stamped(bus, clock)
    move(bus)

    presses = {4.0: "draining"}

    def sleep(seconds: float) -> None:
        word = presses.pop(clock.now + seconds, None)
        if word is not None:
            bus.publish(POWER_WANTED, {"power": word})

    sim.run_live(2.0, sleep=sleep, stop=lambda: clock.now >= 40.0)

    assert seen == [
        (TRANSIT_S, "block_occupied", "dn_w"),
        (TRANSIT_S + CLEAR_S, "block_vacated", "yard_w"),
    ]


def test_a_drain_starts_no_move() -> None:
    """Nothing new starts in a drain: a `move` arriving while power reads
    `draining` is dropped, as the layout drops it, and never runs after."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    press(bus, {"power": "draining"})
    seen = stamped(bus, clock)
    move(bus)
    press(bus, {"power": "on"})
    sim.run()
    assert seen == []


def test_a_drain_ends_off_and_on_resumes_what_off_left() -> None:
    """Drained at 4 with the moving row still true, so the head lands at 10
    with the supply on; `state/moving` reading false at 12 ends the drain in
    `off` with the tail three seconds short. `on` at 20 lets it clear at 23."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    said = heard(bus)
    seen = stamped(bus, clock)
    move(bus)

    def drained() -> None:
        bus.publish("tc49/dispatch/state/moving", {"moving": False})

    def pressed(word: str) -> Callable[[], None]:
        return lambda: bus.publish(POWER_WANTED, {"power": word})

    acts = {4.0: pressed("draining"), 12.0: drained, 20.0: pressed("on")}

    def sleep(seconds: float) -> None:
        act = acts.pop(clock.now + seconds, None)
        if act is not None:
            act()

    sim.run_live(1.0, sleep=sleep, stop=lambda: clock.now >= 40.0)

    assert said == ["on", "draining", "off", "on"]
    assert seen == [
        (TRANSIT_S, "block_occupied", "dn_w"),
        (23.0, "block_vacated", "yard_w"),
    ]
