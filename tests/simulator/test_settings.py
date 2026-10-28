"""What the simulator says on `state/settings` (#1133), and how it takes
`settings_wanted` (#1140).

The driver prices a grant at the speeds `tc49/layout/state/settings` says and
at nothing before it has heard them, so the binding of the layout interface
that is running says the row: `layout` on steel, and this one on a simulated
railroad, stated from its constructor as `state/power` is.
"""

import pytest

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.settings import THROTTLE_SILENCE_S, KeptInstallation, KeptSettings
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


SETTINGS_WANTED = "tc49/layout/settings_wanted"


class Built:
    """A simulator on the bench railroad, and every document it was handed
    to keep (#1140)."""

    def __init__(self, throttle_silence_s: float = THROTTLE_SILENCE_S) -> None:
        layout, _roster, _scenario = load("crossover-yard/meet")
        clock = Clock()
        self.bus = InProcessBus(clock)
        self.kept: list[KeptSettings | KeptInstallation] = []
        Simulator(
            self.bus,
            layout,
            clock,
            throttle_silence_s=throttle_silence_s,
            keep=self.kept.append,
        )
        self.bus.drain()

    def wanted(self, payload: Payload) -> None:
        self.bus.publish(SETTINGS_WANTED, payload)
        self.bus.drain()

    @property
    def said(self) -> Payload:
        row = dict(self.bus.last_values[SETTINGS])
        row.pop("at")
        return row


def test_a_speed_a_person_sets_is_said_at_once_and_kept_with_the_railroad() -> None:
    """`clear` alone: said with `caution` and the gap as they were, and the
    railroad's settings handed to keep, as `layout` takes it (#1140)."""
    built = Built()
    built.wanted({"speeds": {"clear": 0.5}})
    assert built.said == {
        "point_gap": 0.5,
        "speeds": {"clear": 0.5, "caution": 0.3},
        "throttle_silence": THROTTLE_SILENCE_S,
    }
    assert built.kept == [KeptSettings(0.5, {"clear": 0.5, "caution": 0.3})]


def test_a_throttle_silence_a_person_sets_is_said_and_kept_with_the_installation() -> (
    None
):
    """Kept as the installation's and not the railroad's: this binding holds
    no throttle, so it keeps and says the silence and runs on nothing."""
    built = Built()
    built.wanted({"throttle_silence": 10})
    assert built.said["throttle_silence"] == 10.0
    assert built.kept == [KeptInstallation(10.0)]


def test_a_simulator_says_the_throttle_silence_it_is_built_with() -> None:
    assert Built(throttle_silence_s=10.0).said["throttle_silence"] == 10.0


@pytest.mark.parametrize(
    "payload",
    [
        {"speeds": {"clear": 0}},
        {"speeds": {"clear": 0.5}, "colour": "red"},
        {"point_gap": 1.0, "throttle_silence": 1},
        {},
        "clear",
    ],
)
def test_a_gesture_the_contract_does_not_read_changes_nothing(
    payload: object,
) -> None:
    """Dropped whole, as `layout` drops it (ADR-0034): nothing said and
    nothing kept."""
    built = Built()
    before = built.said
    built.bus.publish(SETTINGS_WANTED, payload)  # type: ignore[arg-type]
    built.bus.drain()
    assert built.said == before
    assert built.kept == []
