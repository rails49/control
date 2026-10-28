"""The settings a person sets from the Settings dialog on
`tc49/layout/settings_wanted`: the railroad's point gap and speeds (#1126,
#1132), and the installation's throttle silence (#1132).

`layout` takes the gesture whatever track power and the run are doing, says
the settings at once on `state/settings`, and hands each to be kept in its
document: the gap and the speeds with the railroad, the silence with the
installation. Nothing is rebuilt: the gap is used from the next `align`, the
silence from the next check of who has gone silent, and the speeds are the
driver's.
"""

from tc49.layout.interface import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import MANUAL
from tc49.lib.settings import POINT_GAP_S, KeptInstallation, KeptSettings
from tests.layout.railroad import (
    SETTINGS,
    SETTINGS_WANTED,
    TAKEN,
    build,
    energised,
    faces,
    heard,
    railroad,
    settings_row,
    settle,
    stand,
    stock,
    takes,
    wired,
)

type Kept = KeptSettings | KeptInstallation


def sets(bus: InProcessBus, payload: object) -> None:
    """A person setting the railroad's settings from the Settings dialog."""
    bus.publish(SETTINGS_WANTED, payload)  # type: ignore[arg-type]
    bus.drain()


def kept_by_app() -> tuple[InProcessBus, LayoutInterface, list[Kept]]:
    """An app whose kept settings are recorded rather than written."""
    clock = Clock()
    bus = InProcessBus(clock)
    kept: list[Kept] = []
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


def test_a_gap_beside_good_speeds_and_silence_is_taken_with_them() -> None:
    bus, app, kept = kept_by_app()
    sets(bus, {"point_gap": 2, "speeds": {"clear": 0.8}, "throttle_silence": 10})
    assert kept == [
        KeptSettings(2.0, {"clear": 0.8, "caution": 0.3}),
        KeptInstallation(10.0),
    ]
    assert app.point_gap == 2.0
    assert bus.last_values[SETTINGS] == {
        "at": 0.0,
        "point_gap": 2.0,
        "speeds": {"clear": 0.8, "caution": 0.3},
        "throttle_silence": 10.0,
    }


def test_an_app_that_keeps_no_settings_says_the_default_speeds_and_silence() -> None:
    """A railroad without a settings document and an installation without
    one: `clear` 0.6, `caution` 0.3 and five seconds (#1132)."""
    _bus, _app, _kept = kept_by_app()
    row = _bus.last_values[SETTINGS]
    assert row["speeds"] == {"clear": 0.6, "caution": 0.3}
    assert row["throttle_silence"] == 5.0


def test_an_app_built_with_kept_speeds_says_them() -> None:
    clock = Clock()
    bus = InProcessBus(clock)
    LayoutInterface(
        bus, railroad(), stock(), clock, speeds={"clear": 0.9, "caution": 0.4}
    )
    bus.drain()
    assert bus.last_values[SETTINGS]["speeds"] == {"clear": 0.9, "caution": 0.4}


def test_a_speed_set_is_kept_with_the_railroad_beside_what_was_not_set() -> None:
    """`caution` alone: `clear` and the gap stay as they were, and the row
    says it at once (#1132)."""
    bus, app, kept = kept_by_app()
    sets(bus, {"point_gap": 1.5})
    said = heard(bus, SETTINGS)
    sets(bus, {"speeds": {"caution": 0.2}})
    assert kept[-1] == KeptSettings(1.5, {"clear": 0.6, "caution": 0.2})
    assert said[-1] == (
        SETTINGS,
        {
            "at": 0.0,
            "point_gap": 1.5,
            "speeds": {"clear": 0.6, "caution": 0.2},
            "throttle_silence": 5.0,
        },
    )
    assert app.point_gap == 1.5


def test_a_throttle_silence_set_is_kept_with_the_installation() -> None:
    """And not with the railroad, whose document it is no part of (#1132)."""
    bus, _app, kept = kept_by_app()
    said = heard(bus, SETTINGS)
    sets(bus, {"throttle_silence": 10})
    assert kept == [KeptInstallation(10.0)]
    assert said[-1] == (SETTINGS, {"at": 0.0, **settings_row(throttle_silence=10)})


def test_a_throttle_silence_set_is_the_one_trains_are_let_go_of_on() -> None:
    """Set to ten seconds: a throttle unheard for six still holds its train,
    and one unheard for ten lets go (#1132)."""
    bus, app, clock = wired(driving=MANUAL)
    sets(bus, {"throttle_silence": 10})
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    taken = heard(bus, TAKEN)

    settle(bus, app, clock, after=6.0)
    assert dict(taken[-1][1]["taken"]) == {"single": "t-1"}

    settle(bus, app, clock, after=4.0)
    assert dict(taken[-1][1]["taken"]) == {}


def test_a_gesture_out_of_range_or_with_an_unknown_field_changes_nothing() -> None:
    """A silence of a second, a speed of zero, a field the contract does not
    read: each dropped, nothing said and nothing kept (#1132)."""
    bus, app, kept = kept_by_app()
    said = heard(bus, SETTINGS)
    bus.drain()
    before = list(said)
    for payload in (
        {"throttle_silence": 1},
        {"speeds": {"clear": 0}},
        {"speeds": {"caution": 0.2}, "colour": "red"},
    ):
        sets(bus, payload)
    assert said == before
    assert kept == []
    assert bus.last_values[SETTINGS] == {"at": 0.0, **settings_row()}
    assert app.point_gap == POINT_GAP_S
