"""The simulator's own placement file (#151).

On a real railroad the steel is the persistence: the trains are simply still
there in the morning. The simulator stands in for the steel, so it keeps that
fact in a file of its own — written when a train moves, read at startup, and
entirely inside the app. No bus topic, no inventory entry, nothing about
simulation in the contract
([ADR-0030](../../docs/adr/0030-the-physical-railroad-is-the-normative-binding.md)).

Driven at the layout interface: a `move` command in, sensor events out.
"""

import json
from pathlib import Path

from tc49.bench.runner import placement
from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import TOPICS
from tc49.simulator import Simulator, placement_file
from tests.harness import load

MOVE = "tc49/layout/move"


def sensors(bus: Bus) -> list[tuple[str, Payload]]:
    seen: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/layout/+", lambda topic, payload: seen.append((topic, payload)))
    return seen


def tick(simulator: Simulator) -> None:
    """One tick of the live loop, with no clock: the buffered moves are
    executed and their sensors published."""
    ticks = 0

    def stop() -> bool:
        nonlocal ticks
        ticks += 1
        return ticks > 1

    simulator.run_live(0.0, sleep=lambda _: None, stop=stop)


def move(bus: Bus, train: str, transit: str, into: str) -> None:
    connection, _, name = transit.partition(".")
    bus.publish(
        MOVE, {"train": train, "connection": connection, "transit": name, "into": into}
    )
    bus.drain()


def test_nothing_is_written_without_a_path(tmp_path: Path) -> None:
    """A benchmark run keeps no file, exactly as its bus opens none."""
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = Bus()
    simulator = Simulator(bus, layout, placement(scenario.trains))
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(simulator)

    assert list(tmp_path.iterdir()) == []


def test_a_moved_train_is_written_where_it_now_stands(tmp_path: Path) -> None:
    """Written on change: the file is the placement whole, so what it holds
    is where every train is and not a log of how it got there."""
    layout, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    simulator = Simulator(bus, layout, placement(scenario.trains), path)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(simulator)

    assert json.loads(path.read_text()) == {"express_2": "up_e", "freight_1": "dn_w"}


def test_a_restarted_simulator_starts_from_the_file(tmp_path: Path) -> None:
    """The morning after: the trains are where they were left, so the block
    the next move vacates is the one the last session parked them in and not
    the one the scenario document names."""
    layout, _roster, scenario = load("crossover-yard/meet")
    stood = placement(scenario.trains)
    path = tmp_path / "placement.json"
    first = Bus()
    moved = Simulator(first, layout, stood, path)
    move(first, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(moved)

    second = Bus()
    restarted = Simulator(second, layout, stood, path)
    seen = sensors(second)
    move(second, "freight_1", "crossover.dn_straight", "dn_e")
    tick(restarted)

    assert ("tc49/layout/block_vacated", {"block": "dn_w"}) in seen


def test_a_hand_that_lifts_a_train_moves_the_steel_under_it(tmp_path: Path) -> None:
    """`train_placed` is the one thing besides a `move` that moves a train
    (#152): a person lifted a locomotive and the dispatcher accepted it. On
    the real railroad nobody has to say so — the steel simply is where it was
    left — and the simulator stands in for the steel, so it is told. Without
    it the next move would vacate the block the train used to be in and the
    sensors would describe a railroad nobody is on."""
    layout, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    simulator = Simulator(bus, layout, placement(scenario.trains), path)
    bus.publish("tc49/dispatch/train_placed", {"train": "freight_1", "block": "up_w"})
    bus.drain()

    assert json.loads(path.read_text()) == {"express_2": "up_e", "freight_1": "up_w"}

    seen = sensors(bus)
    move(bus, "freight_1", "crossover.up_to_dn", "dn_e")
    tick(simulator)
    assert ("tc49/layout/block_vacated", {"block": "up_w"}) in seen


def test_a_hand_that_lifts_a_train_off_the_layout_takes_the_steel_with_it(
    tmp_path: Path,
) -> None:
    """The other half of the same gesture (#170): the train is gone, so the
    steel this binding stands in for is gone, and the file it is kept in says
    so. Nothing is reported on any detector — this binding reports occupancy
    when a train crosses, and this train crosses nothing now."""
    layout, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    bus = Bus()
    Simulator(bus, layout, placement(scenario.trains), path)
    seen = sensors(bus)

    bus.publish("tc49/dispatch/train_removed", {"train": "freight_1"})
    bus.drain()

    assert json.loads(path.read_text()) == {"express_2": "up_e"}
    assert seen == []


def test_the_file_names_the_steel_no_document_placed(tmp_path: Path) -> None:
    """The file is the steel's own memory, so it comes first: a train a hand
    put on the rails is one no document places, and a restart that dropped it
    would move a locomotive nobody touched (ADR-0039, ADR-0030)."""
    layout, _roster, scenario = load("crossover-yard/meet")
    path = tmp_path / "placement.json"
    path.write_text(json.dumps({"shunter": "up_w"}))
    bus = Bus()
    simulator = Simulator(bus, layout, placement(scenario.trains), path)

    seen = sensors(bus)
    move(bus, "shunter", "crossover.up_to_dn", "dn_e")
    tick(simulator)

    assert ("tc49/layout/block_vacated", {"block": "up_w"}) in seen


def test_the_placement_reaches_no_topic(tmp_path: Path) -> None:
    """The whole of what keeps simulation out of the contract (ADR-0030): the
    inventory names no simulator topic, and the file is the app's own."""
    assert not [topic for topic in TOPICS if "simul" in topic]
    # Its file is a sibling of the session's, never the session's own: the
    # bus holds the contract's retained values and this one holds the steel.
    state = tmp_path / "session.json"
    assert placement_file(state) != state
    assert placement_file(state).parent == state.parent
