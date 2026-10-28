"""What the simulator says on `state/settings` (#1133).

The driver prices a grant at the speeds `tc49/layout/state/settings` says and
at nothing before it has heard them, so the binding of the layout interface
that is running says the row: `layout` on steel, and this one on a simulated
railroad, stated from its constructor as `state/power` is.
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.settings import THROTTLE_SILENCE_S, KeptSettings
from tc49.simulator import Simulator
from tests.harness import load

SETTINGS = "tc49/layout/state/settings"


def said_on_build(settings: KeptSettings | None) -> Payload:
    """The row a simulator built with `settings` leaves retained."""
    layout, _roster, _scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    Simulator(bus, layout, clock, settings=settings)
    bus.drain()
    row = dict(bus.last_values[SETTINGS])
    row.pop("at")
    return row


def test_a_railroad_that_keeps_no_settings_says_the_defaults() -> None:
    """`clear` 0.6 and `caution` 0.3 (ADR-0079), the point gap and the
    throttle silence beside them, every field present as `layout` says it."""
    assert said_on_build(None) == {
        "point_gap": 0.5,
        "speeds": {"clear": 0.6, "caution": 0.3},
        "throttle_silence": THROTTLE_SILENCE_S,
    }


def test_a_railroad_that_keeps_its_speeds_says_them() -> None:
    """The speeds the railroad keeps are the ones the driver hears."""
    kept = KeptSettings(1.0, {"clear": 0.5, "caution": 0.25})
    assert said_on_build(kept) == {
        "point_gap": 1.0,
        "speeds": {"clear": 0.5, "caution": 0.25},
        "throttle_silence": THROTTLE_SILENCE_S,
    }
