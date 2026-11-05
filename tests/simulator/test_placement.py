"""Where the simulator's steel stands, and the two gestures that move it.

On a real railroad the steel is the persistence: the trains are simply still
there in the morning. This binding stands in for the steel, so where each
train stands is its own — held in memory, on no bus topic, in no inventory
entry, and nothing about simulation in the contract
([ADR-0030](../../docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).
Retained state lives in the broker and nowhere else, so where that memory
would live across a container's restart is open and not this app's to invent
([ADR-0059](../../docs/adr/0059-the-bus-is-a-broker-each-app-is-its-own-process-and-the-bridge-is-deleted.md)
decision 3, `tc49/simulator/__main__.py`).

Driven at the layout interface: a `move` command in, sensor events out, and
the settled reading of each sensor beside them (#1170).
"""

from dataclasses import replace

from tc49.bench.runner import placement, powered
from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.lib.inventory import TOPICS
from tc49.lib.layout import Layout
from tc49.simulator import Simulator
from tests.harness import load

MOVE = "tc49/layout/move"


def simulator(bus: InProcessBus, layout: Layout, stood: dict[str, str]) -> Simulator:
    """The binding under test, with zero delays: a move's readings
    fire on the next tick rather than a simulated minute out. Powered, as a
    person powers a box that has just come up (ADR-0070)."""
    return powered(
        bus, Simulator(bus, layout, Clock(), stood, transit_s=0.0, clear_s=0.0)
    )


def tick(sim: Simulator) -> None:
    """One turn of the live loop, with no clock: the sensor events an
    accepted move scheduled — due immediately at zero delay — fire and their
    cascade drains."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return ticks > 1

    sim.run_live(0.0, sleep=lambda _: None, stop=stop)


def move(bus: InProcessBus, train: str, transit: str, into: str) -> None:
    connection, _, name = transit.partition(".")
    bus.publish(
        MOVE, {"train": train, "connection": connection, "transit": name, "into": into}
    )
    bus.drain()


def test_the_placement_reaches_no_topic() -> None:
    """The whole of what keeps simulation out of the contract (ADR-0030): the
    inventory names no simulator topic, and where the steel stands is the
    app's own."""
    assert not [topic for topic in TOPICS if "simul" in topic]


def timed(bus: InProcessBus, layout: Layout, stood: dict[str, str]) -> Simulator:
    """The binding with a delay on each reading, so a test can stop a move
    between its head and its tail: each `step` fires exactly one of them."""
    return powered(
        bus, Simulator(bus, layout, Clock(), stood, transit_s=10.0, clear_s=10.0)
    )


def step(sim: Simulator, readings: int) -> None:
    """Turns of the live loop until it has slept `readings` delays, each
    firing what is due at its end. A turn that sleeps nothing, firing what a
    `move` read at its start, is not one of them."""
    slept = 0

    def sleep(seconds: float) -> None:
        nonlocal slept
        slept += seconds > 0.0

    sim.run_live(10.0, sleep=sleep, stop=lambda: slept >= readings)


def remove(bus: InProcessBus, train: str) -> None:
    bus.publish("tc49/dispatch/train_removed", {"train": train})
    bus.drain()


def settled(bus: InProcessBus) -> list[tuple[str, str]]:
    """Each settled reading from now on, the sensor and its level. A test
    subscribes before the move, since a late subscriber is handed the rows
    this binding has published already."""
    seen: list[tuple[str, str]] = []
    bus.subscribe(
        "tc49/layout/state/settled/sensor/#",
        lambda topic, payload: seen.append(
            (str(payload["addr"]), str(payload["occupancy"]))
        ),
    )
    return seen


def from_here(bus: InProcessBus) -> list[tuple[str, str]]:
    """`settled` for a test subscribing after the move, past the rows it is
    handed for that."""
    seen = settled(bus)
    bus.drain()
    seen.clear()
    return seen


def test_a_removal_reads_clear_every_sensor_read_occupied_for_the_train() -> None:
    """Halfway to its tail clearing: `yard_w.B` and `dn_w.A` read occupied for
    it, so each reads clear, and nothing of the move fires after (#1170)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    seen = settled(bus)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 1)
    assert seen == [("yard_w.B", "occupied"), ("dn_w.A", "occupied")]

    seen.clear()
    remove(bus, "freight_1")
    assert seen == [("yard_w.B", "clear"), ("dn_w.A", "clear")]

    seen.clear()
    step(sim, 3)
    assert seen == []


def test_a_placement_reads_clear_every_sensor_read_occupied_for_the_train() -> None:
    """The same for a hand putting it down elsewhere, and the block it is put
    in reads nothing: no sensor here read it there (#1170)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    seen = settled(bus)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 1)

    seen.clear()
    place(bus, "freight_1", "up_w")
    assert seen == [("yard_w.B", "clear"), ("dn_w.A", "clear")]

    seen.clear()
    step(sim, 3)
    assert seen == []


def test_a_placement_in_the_block_a_train_stands_in_clears_its_far_sensor() -> None:
    """Every sensor read occupied for it reads clear (#1170)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    seen = settled(bus)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 3)
    assert seen[-1] == ("dn_w.B", "occupied")

    seen.clear()
    place(bus, "freight_1", "dn_w")
    assert seen == [("dn_w.B", "clear")]


def test_a_train_placed_reads_nothing_and_moved_reads_its_exit_at_the_start() -> None:
    """A train only placed publishes no row, and its first move reads the
    sensor it leaves by occupied at once (#1170)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    seen = settled(bus)
    place(bus, "freight_1", "up_w")
    assert seen == []

    move(bus, "freight_1", "crossover.up_to_dn", "dn_e")
    sim.run_live(10.0, sleep=lambda _: None, stop=lambda: seen != [])
    assert seen == [("up_w.B", "occupied")]


def test_a_block_named_with_a_wildcard_gets_no_row() -> None:
    """A drawing may name a block anything but `.` and `/`, and a broker's
    client raises on a wildcard in a topic (#1168, BUS.md): that sensor has no
    row (#1170)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    wild = replace(
        layout,
        blocks={**layout.blocks, "dn+w": layout.blocks["dn_w"]},
        connections={
            "west_ladder": replace(
                layout.connections["west_ladder"],
                transits={"to_dn": ("dn+w.A", "yard_w.B")},
            )
        },
    )
    bus = InProcessBus(Clock())
    sim = timed(bus, wild, placement(scenario.trains))
    seen = settled(bus)
    move(bus, "freight_1", "west_ladder.to_dn", "dn+w")
    step(sim, 3)

    assert seen == [("yard_w.B", "occupied"), ("yard_w.B", "clear")]


def test_a_lifted_train_clears_the_block_it_moved_into() -> None:
    """The simulator stands in for the hand (ADR-0069 decision 7): its own
    detector last read the train occupied at `dn_w.A`, so lifting it off reads
    that sensor clear."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)

    seen = from_here(bus)
    remove(bus, "freight_1")
    assert ("dn_w.A", "clear") in seen


def test_a_train_lifted_across_a_transit_clears_both_blocks() -> None:
    """Head in `dn_e`, tail still over `dn_w`: a sensor of each read occupied
    for it, so each reads clear when it comes off, and the tail reading it had
    scheduled never fires — there is no tail left to clear the near detector."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    step(sim, 1)

    seen = from_here(bus)
    remove(bus, "freight_1")
    step(sim, 2)
    assert ("dn_e.A", "clear") in seen
    assert ("dn_w.B", "clear") in seen
    assert all(level == "clear" for _sensor, level in seen)


def test_a_train_lifted_before_its_head_reading_clears_its_origin_alone() -> None:
    """It moved into `dn_w` and has set off again, but the head has not
    reached `dn_e`: only sensors of `dn_w` and the block before it were read
    occupied for it, so `dn_e` reads nothing, and neither of the move's readings
    fires afterwards."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")

    seen = from_here(bus)
    remove(bus, "freight_1")
    step(sim, 2)
    assert ("dn_w.A", "clear") in seen
    assert all(level == "clear" for _sensor, level in seen)
    assert not [sensor for sensor, _level in seen if sensor.startswith("dn_e")]


def test_a_train_lifted_where_it_was_placed_reads_nothing() -> None:
    """A train placed and never moved was never read occupied by this
    binding's detectors, so lifting it reads nothing clear either."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    timed(bus, layout, placement(scenario.trains))
    bus.publish("tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    bus.drain()

    seen = from_here(bus)
    remove(bus, "freight_1")
    assert seen == []


def place(bus: InProcessBus, train: str, block: str) -> None:
    bus.publish("tc49/dispatch/train_placed", {"train": train, "block": block})
    bus.drain()


def test_a_train_placed_after_a_move_clears_nothing_when_lifted() -> None:
    """Its detector read it occupied in `dn_w`, then a hand put it in `up_w`:
    the detector under `dn_w` no longer reports it, so lifting it off reads
    nothing clear (#677)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)
    place(bus, "freight_1", "up_w")

    seen = from_here(bus)
    remove(bus, "freight_1")
    assert seen == []


def test_a_train_placed_away_reads_the_block_it_left_clear() -> None:
    """Its detector read it occupied in `dn_w`, and a hand lifted it off and
    put it in `up_w`. The steel has left `dn_w`, and left reading occupied it
    would stand disputed with no detector to end it (#1154). `up_w` is not read
    occupied: no detector here read it there."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)

    seen = from_here(bus)
    place(bus, "freight_1", "up_w")

    assert ("dn_w.A", "clear") in seen
    assert all(level == "clear" for _sensor, level in seen)


def test_a_train_placed_between_blocks_reaches_no_detector() -> None:
    """Placed after the `move` and before its head reading: the head never
    reaches the far detector and the tail has nothing left to clear, so
    neither reading fires and the train stays where it was put (#677)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    place(bus, "freight_1", "up_w")

    seen = from_here(bus)
    step(sim, 2)
    assert seen == []
    assert sim._position["freight_1"] == "up_w"  # pyright: ignore[reportPrivateUsage]


def test_a_train_placed_between_blocks_takes_its_next_move() -> None:
    """It is no longer mid-move once a hand has put it down, so a `move`
    from the block it was put in is accepted and its readings fire (#677)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    place(bus, "freight_1", "up_w")

    seen = from_here(bus)
    move(bus, "freight_1", "crossover.up_to_dn", "dn_e")
    step(sim, 2)
    assert seen == [
        ("up_w.B", "occupied"),
        ("dn_e.A", "occupied"),
        ("up_w.B", "clear"),
    ]
