"""What the simulator says about track power (#159).

Simulated track is always live. The binding states `on` from its constructor
so a joining client is served a value rather than reading one out of an
absence (ADR-0032), and never says anything else: a power cut is a physical
act, and simulating one would be the field or the branch ADR-0030 keeps out
of every app.
"""

from tc49.lib.bus import Bus, Payload
from tc49.simulator import Simulator
from tests.harness import build, events, load

POWER = "tc49/layout/state/power"


def heard(bus: Bus) -> list[Payload]:
    seen: list[Payload] = []
    bus.subscribe(POWER, lambda topic, payload: seen.append(payload))
    return seen


def test_the_value_is_stated_before_anything_is_asked() -> None:
    """Retained and published from the constructor, so a subscriber that
    arrives afterwards is served it too — which is the case that matters,
    every consumer of the layout being built before the layout is."""
    bus = Bus()
    Simulator(bus)
    assert bus.last_values[POWER] == {"power": "on"}

    seen = heard(bus)
    bus.drain()
    assert seen[0] == {"power": "on"}


def test_a_whole_run_says_it_once_and_never_changes_it() -> None:
    """Nothing in the simulator moves the value: it is on the trace at
    boundary 0 and appears nowhere after."""
    layout, _roster, scenario = load("crossover-yard/meet")
    assembly = build(layout, _roster, scenario)
    assembly.simulator.run()

    said = events(assembly.trace, "power")
    assert said == [{"boundary": 0, "event": "power", "power": "on"}]
