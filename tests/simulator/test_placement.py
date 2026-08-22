"""The simulator's own placement file (#151).

On a real railroad the steel is the persistence: the trains are simply still
there in the morning. The simulator stands in for the steel, so it keeps that
fact in a file of its own — written when a train moves, read at startup, and
entirely inside the app. No bus topic, no inventory entry, nothing about
simulation in the contract
([ADR-0030](../../docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).

Driven at the layout interface: a `cross` command in, sensor events out.
"""

import json
from pathlib import Path

from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import TOPICS
from tc49.simulator import Simulator, placement_file
from tests.harness import load

CROSS = "tc49/drive/cross"


def sensors(bus: Bus) -> list[tuple[str, Payload]]:
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen.append((topic, payload)))
    return seen


def tick(simulator: Simulator) -> None:
    """One tick of the live loop, with no clock: the buffered crosses are
    executed and their sensors published."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return ticks > 1

    simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def cross(bus: Bus, train: str, into: str) -> None:
    bus.publish(CROSS, {"train": train, "into": into})
    bus.drain()


def test_nothing_is_written_without_a_path(tmp_path: Path) -> None:
    """A benchmark run keeps no file, exactly as its bus opens none."""
    _, _roster, scenario = load("crossover-yard/meet")
    bus = Bus()
    simulator = Simulator(bus, scenario)
    cross(bus, "freight_1", "dn_w")
    tick(simulator)

    assert list(tmp_path.iterdir()) == []


def test_a_moved_train_is_written_where_it_now_stands(tmp_path: Path) -> None:
    """Written on change: the file is the placement whole, so what it holds
    is where every train is and not a log of how it got there."""
    _, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    simulator = Simulator(bus, scenario, path)
    cross(bus, "freight_1", "dn_w")
    tick(simulator)

    assert json.loads(path.read_text()) == {"express_2": "up_e", "freight_1": "dn_w"}


def test_a_restarted_simulator_starts_from_the_file(tmp_path: Path) -> None:
    """The morning after: the trains are where they were left, so the block
    the next move vacates is the one the last session parked them in and not
    the one the scenario document names."""
    _, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    first = Bus()
    moved = Simulator(first, scenario, path)
    cross(first, "freight_1", "dn_w")
    tick(moved)

    second = Bus()
    restarted = Simulator(second, scenario, path)
    seen = sensors(second)
    cross(second, "freight_1", "dn_e")
    tick(restarted)

    assert ("tc49/layout/block_vacated", {"block": "dn_w"}) in seen


def test_a_hand_that_lifts_a_train_moves_the_steel_under_it(tmp_path: Path) -> None:
    """`train_placed` is the one thing besides a `cross` that moves a train
    (#152): a person lifted a locomotive and the dispatcher accepted it. On
    the real railroad nobody has to say so — the steel simply is where it was
    left — and the simulator stands in for the steel, so it is told. Without
    it the next move would vacate the block the train used to be in and the
    sensors would describe a railroad nobody is on."""
    _, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    simulator = Simulator(bus, scenario, path)
    bus.publish("tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    bus.drain()

    assert json.loads(path.read_text()) == {"express_2": "up_e", "freight_1": "up_w"}

    seen = sensors(bus)
    cross(bus, "freight_1", "dn_w")
    tick(simulator)
    assert ("tc49/layout/block_vacated", {"block": "up_w"}) in seen


def test_a_hand_that_lifts_a_train_off_the_layout_takes_the_steel_with_it(
    tmp_path: Path,
) -> None:
    """The other half of the same gesture (#170): the train is gone, so the
    steel this binding stands in for is gone, and the file it is kept in says
    so. Nothing is reported on any detector — this binding reports occupancy
    when a train crosses, and this train crosses nothing now."""
    _, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    Simulator(bus, scenario, path)
    seen = sensors(bus)

    bus.publish("tc49/dispatch/train_removed", {"train": "freight_1"})
    bus.drain()

    assert json.loads(path.read_text()) == {"express_2": "up_e"}
    assert seen == []


def test_the_placement_reaches_no_topic(tmp_path: Path) -> None:
    """The whole of what keeps simulation out of the contract (ADR-0030): the
    inventory names no simulator topic, and the file is the app's own."""
    assert not [topic for topic in TOPICS if "simul" in topic]
    # Its file is a sibling of the session's, never the session's own: the
    # bus holds the contract's retained values and this one holds the steel.
    state = tmp_path / "session.json"
    assert placement_file(state) != state
    assert placement_file(state).parent == state.parent
