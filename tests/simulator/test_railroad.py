"""Which railroad the simulator stands in for (#371).

The row is the **role's** and both bindings of the layout interface meet it
(ADR-0059 decision 2, as amended by ADR-0060): a run under the simulator is a
run of a drawn railroad, and a view reads which one off the same topic it
would on steel.
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.simulator import Simulator
from tests.harness import load

RAILROAD = "tc49/layout/state/railroad"


def heard(bus: InProcessBus) -> list[Payload]:
    seen: list[Payload] = []
    bus.subscribe(RAILROAD, lambda topic, payload: seen.append(payload))
    return seen


def test_the_railroad_is_named_from_the_constructor() -> None:
    """Retained and stated before anything is asked, so a subscriber that
    arrives afterwards is served it too."""
    layout, _roster, _scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    Simulator(bus, layout, clock)

    assert bus.last_values[RAILROAD] == {"at": 0.0, "name": "crossover-yard"}

    seen = heard(bus)
    bus.drain()
    assert seen[0] == {"at": 0.0, "name": "crossover-yard"}
