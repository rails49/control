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

Driven at the layout interface: a `move` command in, sensor events out.
"""

from tc49.bench.runner import placement
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import TOPICS
from tc49.lib.layout import Layout
from tc49.simulator import Simulator
from tests.harness import load

MOVE = "tc49/layout/move"


def simulator(bus: InProcessBus, layout: Layout, stood: dict[str, str]) -> Simulator:
    """The binding under test, with zero delays: a move's two sensor events
    fire on the next tick rather than a simulated minute out."""
    return Simulator(bus, layout, Clock(), stood, transit_s=0.0, clear_s=0.0)


def sensors(bus: InProcessBus) -> list[tuple[str, Payload]]:
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen.append((topic, payload)))
    return seen


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


def test_a_hand_that_lifts_a_train_moves_the_steel_under_it() -> None:
    """`train_placed` is the one thing besides a `move` that moves a train
    (#152): a person lifted a locomotive and the dispatcher accepted it. On
    the real railroad nobody has to say so — the steel simply is where it was
    left — and the simulator stands in for the steel, so it is told. Without
    it the next move would vacate the block the train used to be in and the
    sensors would describe a railroad nobody is on."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = simulator(bus, layout, placement(scenario.trains))
    bus.publish("tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    bus.drain()

    seen = sensors(bus)
    move(bus, "freight_1", "crossover.up_to_dn", "dn_e")
    tick(sim)
    assert ("tc49/layout/block_vacated", {"block": "up_w"}) in seen


def test_a_hand_that_lifts_a_train_off_the_layout_takes_the_steel_with_it() -> None:
    """The other half of the same gesture (#170): the train is gone, so the
    steel this binding stands in for is gone. Nothing is reported on any
    detector — this binding reports occupancy when a train crosses, and this
    train crosses nothing now."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = simulator(bus, layout, placement(scenario.trains))
    seen = sensors(bus)

    bus.publish("tc49/dispatch/train_removed", {"train": "freight_1"})
    bus.drain()
    assert seen == []

    # And it really is off: a move for it now stands no train up, where the
    # same move before the removal would have vacated `yard_w`.
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(sim)
    assert ("tc49/layout/block_vacated", {"block": "yard_w"}) not in seen


def test_the_placement_reaches_no_topic() -> None:
    """The whole of what keeps simulation out of the contract (ADR-0030): the
    inventory names no simulator topic, and where the steel stands is the
    app's own."""
    assert not [topic for topic in TOPICS if "simul" in topic]


def timed(bus: InProcessBus, layout: Layout, stood: dict[str, str]) -> Simulator:
    """The binding with a delay on each reading, so a test can stop a move
    between its head and its tail: each `step` fires exactly one of them."""
    return Simulator(bus, layout, Clock(), stood, transit_s=10.0, clear_s=10.0)


def step(sim: Simulator, readings: int) -> None:
    """Turns of the live loop, each sleeping one delay and so firing the one
    reading due at its end."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return ticks > readings

    sim.run_live(10.0, sleep=lambda _: None, stop=stop)


def remove(bus: InProcessBus, train: str) -> None:
    bus.publish("tc49/dispatch/train_removed", {"train": train})
    bus.drain()


def occupancy(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """The two detector readings alone."""
    seen: list[tuple[str, Payload]] = []
    for topic in ("tc49/layout/block_occupied", "tc49/layout/block_vacated"):
        bus.subscribe(topic, lambda topic, payload: seen.append((topic, payload)))
    return seen


def test_a_lifted_train_clears_the_block_it_moved_into() -> None:
    """The simulator stands in for the hand (ADR-0069 decision 7): its own
    detector last read the train occupied in `dn_w`, so lifting it off reads
    that block clear."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)

    seen = occupancy(bus)
    remove(bus, "freight_1")
    assert seen == [("tc49/layout/block_vacated", {"block": "dn_w"})]


def test_a_train_lifted_across_a_transit_clears_both_blocks() -> None:
    """Head in `dn_e`, tail still over `dn_w`: both read occupied for it, so
    both read clear when it comes off, and the tail reading it had scheduled
    never fires — there is no tail left to clear the near detector."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")
    step(sim, 1)

    seen = occupancy(bus)
    remove(bus, "freight_1")
    step(sim, 2)
    assert sorted(seen, key=str) == [
        ("tc49/layout/block_vacated", {"block": "dn_e"}),
        ("tc49/layout/block_vacated", {"block": "dn_w"}),
    ]


def test_a_train_lifted_before_its_head_reading_clears_its_origin_alone() -> None:
    """It moved into `dn_w` and has set off again, but the head has not
    reached `dn_e`: only `dn_w` was read occupied for it, so only `dn_w`
    reads clear, and neither of the move's readings fires afterwards."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    step(sim, 2)
    move(bus, "freight_1", "crossover.dn_straight", "dn_e")

    seen = occupancy(bus)
    remove(bus, "freight_1")
    step(sim, 2)
    assert seen == [("tc49/layout/block_vacated", {"block": "dn_w"})]


def test_a_train_lifted_where_it_was_placed_reads_nothing() -> None:
    """A train placed and never moved was never read occupied by this
    binding's detectors, so lifting it reads nothing clear either."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    timed(bus, layout, placement(scenario.trains))
    bus.publish("tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    bus.drain()

    seen = occupancy(bus)
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

    seen = occupancy(bus)
    remove(bus, "freight_1")
    assert seen == []


def test_a_train_placed_between_blocks_reaches_no_detector() -> None:
    """Placed after the `move` and before its head reading: the head never
    reaches the far detector and the tail has nothing left to clear, so
    neither reading fires and the train stays where it was put (#677)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    sim = timed(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    place(bus, "freight_1", "up_w")

    seen = occupancy(bus)
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

    seen = occupancy(bus)
    move(bus, "freight_1", "crossover.up_to_dn", "dn_e")
    step(sim, 2)
    assert seen == [
        ("tc49/layout/block_occupied", {"block": "dn_e"}),
        ("tc49/layout/block_vacated", {"block": "up_w"}),
    ]
