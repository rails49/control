"""A `move` is acted on only at the transit's near end (#268, ADR-0047).

ADR-0040's expiry stamp — dropping a `move` redelivered after a reconnect by
the boundary it was granted on — was never implemented. This is its
replacement, and it is stronger: a stale `move` is a no-op on state alone,
whether it was redelivered after arrival, granted against a placement a hand
has since changed, or names a train that has left the layout. No clock, no
stamp, no agreement between apps. Those stale cases are held to both bindings
in `tests/system/test_layout_bindings.py`; what stays here is the fresh move.

Driven at the layout interface: a `move` command in, sensor events out.
"""

from tc49.bench.runner import placement
from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tc49.simulator import Simulator
from tests.harness import load
from tests.simulator.test_placement import move, settled, simulator, tick


def build() -> tuple[InProcessBus, Simulator]:
    layout, _roster, scenario = load("crossover-yard/meet")
    bus = InProcessBus(Clock())
    return bus, simulator(bus, layout, placement(scenario.trains))


def test_a_live_move_still_moves() -> None:
    """The check refuses stale commands, not fresh ones: a train standing at
    the near end crosses exactly as before."""
    bus, sim = build()
    seen = settled(bus)
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(sim)
    assert ("yard_w.B", "clear") in seen
    assert ("dn_w.A", "occupied") in seen


def test_a_stale_move_reads_no_sensor() -> None:
    """A `move` redelivered after arrival finds its train past the near end,
    so `yard_w.B`, which has read clear, is not read occupied again (#1170)."""
    bus, sim = build()
    read: list[object] = []
    bus.subscribe(
        "tc49/layout/state/settled/sensor/yard_w.B",
        lambda topic, payload: read.append(payload["occupancy"]),
    )
    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(sim)
    assert read == ["occupied", "clear"]

    move(bus, "freight_1", "west_ladder.to_dn", "dn_w")
    tick(sim)
    assert read == ["occupied", "clear"]
