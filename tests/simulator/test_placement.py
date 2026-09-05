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
