"""What the simulator says about track power, and what it does under it (#702).

The simulator answers the band's power presses as the layout interface does
(ADR-0070). It comes up `off`, stated from its constructor so a joining
client is served a value rather than reading one out of an absence
(ADR-0032), and publishes on `state/power` the word each answered
`power_wanted` commanded, since it has no hardware to report one. A plain
`off` is applied only while the run is held and nothing moves (ADR-0062),
the check being `lib.power`'s and the same one the layout makes.

While the power is not `on` no move starts and none advances: a `move` is
dropped, and a transit under way at a STOP waits and goes on at ON with the
time it had left.
"""

import pytest

from tc49.bench.runner import placement
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import leaf
from tc49.simulator import Simulator
from tests.harness import build, events, load

POWER = "tc49/layout/state/power"
POWER_WANTED = "tc49/layout/power_wanted"
RUN = "tc49/dispatch/state/run"
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


def test_a_new_simulator_comes_up_off() -> None:
    """Retained and published from the constructor, as the layout interface
    comes up: a simulated box needs ON after it starts, as a real one does
    (ADR-0070, decision 2)."""
    bus, _clock, _sim = simulator()
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_each_answered_press_is_the_word_on_state_power() -> None:
    """No hardware reports the supply here, so the word commanded is the
    word stated: `on`, `stopped` and `off` each appear as pressed."""
    bus, _clock, _sim = simulator()
    seen = heard(bus)
    bus.drain()
    for word in ("on", "stopped", "off"):
        press(bus, {"power": word})
    assert seen == ["off", "on", "stopped", "off"]


@pytest.mark.parametrize(
    "payload", [{"power": "sideways"}, {"power": 1}, {}, {"wanted": "on"}]
)
def test_an_unreadable_press_changes_nothing(payload: Payload) -> None:
    bus, _clock, _sim = simulator()
    press(bus, {"power": "on"})
    seen = heard(bus)
    bus.drain()
    press(bus, payload)
    assert seen == ["on"]


@pytest.mark.parametrize(
    "run",
    [{"run": "running", "moving": False}, {"run": "held", "moving": True}],
)
def test_off_is_refused_on_evidence_that_something_moves(run: Payload) -> None:
    """The check `lib.power` makes for both bindings (ADR-0062): a run still
    committing, or a train moving under a held one, keeps the supply on."""
    bus, _clock, _sim = simulator()
    press(bus, {"power": "on"})
    bus.publish(RUN, run)
    bus.drain()
    seen = heard(bus)
    bus.drain()
    press(bus, {"power": "off"})
    assert seen == ["on"]


@pytest.mark.parametrize("run", [None, {"run": "held", "moving": False}])
def test_off_is_applied_with_no_run_row_or_a_held_still_one(
    run: Payload | None,
) -> None:
    """No `state/run` is not evidence: with no dispatcher up nothing has been
    granted."""
    bus, _clock, _sim = simulator()
    press(bus, {"power": "on"})
    if run is not None:
        bus.publish(RUN, run)
        bus.drain()
    seen = heard(bus)
    bus.drain()
    press(bus, {"power": "off"})
    assert seen == ["on", "off"]


@pytest.mark.parametrize("word", ["off", "stopped"])
def test_a_move_without_power_starts_nothing(word: str) -> None:
    """A `move` is dropped, as the layout drops it: no sensor speaks, and the
    train is not rolling — a move sent once the power is back is acted on."""
    bus, clock, sim = simulator()
    if word == "stopped":
        press(bus, {"power": "on"})
        press(bus, {"power": "stopped"})
    seen = stamped(bus, clock)
    move(bus)
    sim.run()
    assert seen == []

    press(bus, {"power": "on"})
    move(bus)
    sim.run()
    assert [(what, block) for _at, what, block in seen] == [
        ("block_occupied", "dn_w"),
        ("block_vacated", "yard_w"),
    ]


def test_a_transit_under_way_at_a_stop_goes_on_at_on_with_the_time_it_had_left() -> (
    None
):
    """Started at 0 with ten seconds to run, stopped at 4 and powered again
    at 20: the head is six seconds out still, so it lands at 26 and the tail
    clears a clearing delay after (ADR-0070, decision 4). Driven live with
    the wait injected; each press lands in the wait that ends at its time."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    seen = stamped(bus, clock)
    move(bus)

    presses = {4.0: "stopped", 20.0: "on"}

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
    """A batch run never sends STOP, so this is only for safety: a queue that
    cannot fire is not a queue to wait on."""
    bus, clock, sim = simulator()
    press(bus, {"power": "on"})
    seen = stamped(bus, clock)
    move(bus)
    press(bus, {"power": "stopped"})
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
