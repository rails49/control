"""The railroad's settings, so far the point gap, set by a person from the
Settings dialog on `tc49/layout/settings_wanted` (#1126).

`layout` takes the gesture whatever track power and the run are doing, says
the settings at once on `state/settings`, and hands them to be kept with the
railroad. Nothing is rebuilt: the gap is used from the next `align`.
"""

from tc49.layout.interface import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.settings import POINT_GAP_S, KeptSettings
from tests.layout.railroad import (
    SETTINGS,
    SETTINGS_WANTED,
    build,
    energised,
    heard,
    railroad,
    settings_row,
    stock,
)


def sets(bus: InProcessBus, payload: object) -> None:
    """A person setting the railroad's settings from the Settings dialog."""
    bus.publish(SETTINGS_WANTED, payload)  # type: ignore[arg-type]
    bus.drain()


def kept_by_app() -> tuple[InProcessBus, LayoutInterface, list[KeptSettings]]:
    """An app whose kept settings are recorded rather than written."""
    clock = Clock()
    bus = InProcessBus(clock)
    kept: list[KeptSettings] = []
    app = LayoutInterface(bus, railroad(), stock(), clock, keep=kept.append)
    bus.drain()
    return bus, app, kept


def test_a_gap_set_is_said_at_once_and_kept() -> None:
    bus, app, kept = kept_by_app()
    said = heard(bus, SETTINGS)
    sets(bus, {"point_gap": 1.5})
    assert said[-1] == (SETTINGS, {"at": 0.0, **settings_row(1.5)})
    assert app.point_gap == 1.5
    assert kept == [KeptSettings(1.5)]


def test_a_gap_is_taken_whatever_the_track_power() -> None:
    bus, app = build()
    sets(bus, {"point_gap": 2})
    assert app.point_gap == 2.0
    energised(bus)
    sets(bus, {"point_gap": 0})
    assert app.point_gap == 0.0
    assert bus.last_values[SETTINGS] == {"at": 0.0, **settings_row(0.0)}


def test_the_ends_of_the_range_are_taken() -> None:
    bus, app, kept = kept_by_app()
    sets(bus, {"point_gap": 5})
    sets(bus, {"point_gap": 0.0})
    assert kept == [KeptSettings(5.0), KeptSettings(0.0)]
    assert app.point_gap == 0.0


def test_a_gesture_that_cannot_be_read_is_dropped() -> None:
    """No `point_gap`, one out of range or no number at all: dropped as any
    malformed gesture is, nothing said and nothing kept (ADR-0034)."""
    bus, app, kept = kept_by_app()
    said = heard(bus, SETTINGS)
    bus.drain()
    before = list(said)
    unreadable: list[object] = [
        {},
        {"gap": 1},
        {"point_gap": -0.5},
        {"point_gap": 5.5},
        {"point_gap": "1"},
        {"point_gap": True},
        {"point_gap": None},
        {"point_gap": float("nan")},
        {"point_gap": float("inf")},
        [1],
    ]
    for payload in unreadable:
        sets(bus, payload)
    assert said == before
    assert kept == []
    assert app.point_gap == POINT_GAP_S


def test_an_app_built_with_a_kept_gap_starts_at_it() -> None:
    clock = Clock()
    bus = InProcessBus(clock)
    app = LayoutInterface(bus, railroad(), stock(), clock, point_gap=3.0)
    bus.drain()
    assert app.point_gap == 3.0
    payload: Payload = bus.last_values[SETTINGS]
    assert payload == {"at": 0.0, **settings_row(3.0)}


def test_a_gap_set_says_the_speeds_and_the_throttle_silence_with_it() -> None:
    """Every field is always on the row, the ones nobody changed at what
    they were (#1130)."""
    bus, _app, _kept = kept_by_app()
    sets(bus, {"point_gap": 1.5})
    assert bus.last_values[SETTINGS]["speeds"] == {"clear": 0.6, "caution": 0.3}
    assert bus.last_values[SETTINGS]["throttle_silence"] == 5.0


def test_a_gap_beside_a_field_the_contract_does_not_read_is_dropped() -> None:
    """An unknown field, or another field out of range, drops the gesture
    whole: the gap beside it is not half taken (#1131)."""
    bus, app, kept = kept_by_app()
    sets(bus, {"point_gap": 1.5, "colour": "red"})
    sets(bus, {"point_gap": 1.5, "throttle_silence": 100})
    sets(bus, {"point_gap": 1.5, "speeds": {"clear": 2}})
    assert kept == []
    assert app.point_gap == POINT_GAP_S


def test_a_gap_beside_good_speeds_and_silence_is_taken() -> None:
    """The gap is taken; keeping the speeds and the silence is #1132's."""
    bus, app, kept = kept_by_app()
    sets(bus, {"point_gap": 2, "speeds": {"clear": 0.8}, "throttle_silence": 10})
    assert kept == [KeptSettings(2.0)]
    assert app.point_gap == 2.0
