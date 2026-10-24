"""A throttle switching one of its train's functions by the name the
catalogue gives it (#849).

The name is the train's, as a throttle shows it (`Train.functions`), and
which decoder and which function number it reaches is `layout`'s: the first
car in the train's order that has an address and declares the name, and that
car's first number for it. The press is the holding throttle's alone, and is
accepted at any power and in either driving mode. Nothing else writes a
function row bar a train let go of having its momentary functions that are on
written off (#998), and `state/functions` says which of each train's functions are
on, read back off the rows themselves so a light a decoder still has on shows
on after a restart.
"""

from tc49.layout import LayoutInterface
from tc49.layout.interface import THROTTLE_SILENCE_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import MANUAL
from tests.layout.railroad import (
    FUNCTIONS,
    WANTED_FUNCTION,
    build,
    gives,
    heard,
    railroad,
    removed,
    settle,
    stand,
    stock,
    switches_function,
    takes,
    wired,
)


def rows(written: list[tuple[str, Payload]]) -> list[tuple[str, Payload]]:
    """Function rows as topic and the fields this app wrote, the stamp being
    the row's shape rather than this write's news."""
    return [
        (topic, {key: value for key, value in payload.items() if key != "at"})
        for topic, payload in written
    ]


def on(said: list[tuple[str, Payload]]) -> object:
    """What `state/functions` last carried."""
    return said[-1][1]["functions"]


def held(train: str = "lit") -> tuple[InProcessBus, list[tuple[str, Payload]]]:
    """A fresh app with the suite's throttle holding `train`, and every
    function row written from here on."""
    bus, _app = build()
    takes(bus, train)
    return bus, heard(bus, WANTED_FUNCTION + "/#")


def test_a_press_writes_the_row_of_the_first_addressed_car_declaring_the_name() -> None:
    """The coach ahead declares headlights and has no decoder, so the
    locomotive behind it is the one that answers: the first addressed car,
    not the first car."""
    bus, written = held()
    switches_function(bus, "lit", "headlights", True)

    assert rows(written) == [
        (f"{WANTED_FUNCTION}/5/0", {"addr": "5", "function": "0", "value": True})
    ]


def test_a_press_with_on_false_writes_value_false() -> None:
    bus, written = held()
    switches_function(bus, "lit", "headlights", False)

    assert rows(written) == [
        (f"{WANTED_FUNCTION}/5/0", {"addr": "5", "function": "0", "value": False})
    ]


def test_a_name_on_two_numbers_is_the_first_the_car_declares() -> None:
    bus, written = held()
    switches_function(bus, "lit", "horn", True)

    assert rows(written) == [
        (f"{WANTED_FUNCTION}/5/3", {"addr": "5", "function": "3", "value": True})
    ]


def test_a_name_only_a_later_car_declares_reaches_that_car() -> None:
    bus, written = held()
    switches_function(bus, "lit", "bell", True)

    assert rows(written) == [
        (f"{WANTED_FUNCTION}/6/1", {"addr": "6", "function": "1", "value": True})
    ]


def test_a_press_from_a_throttle_not_holding_the_train_writes_nothing() -> None:
    bus, written = held()
    switches_function(bus, "lit", "headlights", True, throttle="t-2")
    switches_function(bus, "lit", "headlights", True, throttle=None)

    assert written == []


def test_a_press_on_a_train_no_throttle_holds_writes_nothing() -> None:
    bus, _app = build()
    written = heard(bus, WANTED_FUNCTION + "/#")
    switches_function(bus, "lit", "headlights", True)

    assert written == []


def test_a_name_the_train_does_not_declare_writes_nothing() -> None:
    bus, written = held()
    switches_function(bus, "lit", "smoke", True)

    assert written == []


def test_a_train_with_no_function_writes_nothing() -> None:
    bus, written = held("single")
    switches_function(bus, "single", "headlights", True)

    assert written == []


def test_a_press_while_the_power_is_off_is_written() -> None:
    """The app comes up `off`, and a light is not a wheel: a person turns the
    headlights on before the supply, and the row waits for it (ADR-0054)."""
    bus, written = held()
    assert bus.last_values["tc49/layout/state/power"]["power"] == "off"
    switches_function(bus, "lit", "headlights", True)

    assert len(written) == 1


def test_a_press_in_manual_is_written() -> None:
    bus, _app = build(driving=MANUAL)
    takes(bus, "lit")
    written = heard(bus, WANTED_FUNCTION + "/#")
    switches_function(bus, "lit", "headlights", True)

    assert len(written) == 1


def test_a_release_writes_no_function_row() -> None:
    """The headlights stay as the person left them: a release takes the
    lever out of a hand, and a light is nobody's to put out."""
    bus, written = held()
    switches_function(bus, "lit", "headlights", True)
    gives(bus, "lit")

    assert len(written) == 1


HORN_OFF = (f"{WANTED_FUNCTION}/5/3", {"addr": "5", "function": "3", "value": False})
"""The off row a press of the horn writes."""


def test_a_release_writes_a_momentary_function_that_is_on_off() -> None:
    """Nobody holds the horn's button once the train is let go, so the off
    its throttle would send is dropped as not the holder's: `layout` writes
    it, or the real locomotive keeps sounding (#998)."""
    bus, written = held()
    switches_function(bus, "lit", "horn", True)
    gives(bus, "lit")

    assert rows(written)[1:] == [HORN_OFF]


def test_a_release_before_another_throttle_takes_writes_the_off_once() -> None:
    """A panel's release before its take (#971): the off is written at the
    release, and the take after it writes nothing."""
    bus, written = held()
    switches_function(bus, "lit", "horn", True)
    gives(bus, "lit")
    takes(bus, "lit", throttle="t-2")

    assert rows(written)[1:] == [HORN_OFF]


def test_a_silent_throttle_writes_a_momentary_function_that_is_on_off() -> None:
    bus, app, clock = wired()
    takes(bus, "lit")
    written = heard(bus, WANTED_FUNCTION + "/#")
    switches_function(bus, "lit", "horn", True)
    settle(bus, app, clock, after=THROTTLE_SILENCE_S)

    assert rows(written)[1:] == [HORN_OFF]


def test_a_release_with_the_momentary_function_off_writes_no_row() -> None:
    bus, written = held()
    switches_function(bus, "lit", "horn", True)
    switches_function(bus, "lit", "horn", False)
    gives(bus, "lit")

    assert len(written) == 2


def test_a_release_with_the_momentary_function_never_pressed_writes_no_row() -> None:
    bus, written = held()
    gives(bus, "lit")

    assert written == []


def test_a_release_states_the_momentary_function_off() -> None:
    bus, _written = held()
    said = heard(bus, FUNCTIONS)
    switches_function(bus, "lit", "horn", True)
    gives(bus, "lit")

    assert on(said) == {"lit": {"horn": False}}


def test_a_train_taken_off_writes_no_function_row() -> None:
    bus, written = held()
    stand(bus, "lit", "up_w")
    switches_function(bus, "lit", "headlights", True)
    removed(bus, "lit")

    assert len(written) == 1


# -- which functions are on ----------------------------------------------------


def test_the_app_comes_up_saying_no_function_is_on() -> None:
    bus, _app = build()

    assert bus.last_values[FUNCTIONS]["functions"] == {}


def test_a_press_on_is_stated_on() -> None:
    bus, _written = held()
    said = heard(bus, FUNCTIONS)
    switches_function(bus, "lit", "headlights", True)

    assert on(said) == {"lit": {"headlights": True}}


def test_a_press_off_is_stated_off() -> None:
    bus, _written = held()
    said = heard(bus, FUNCTIONS)
    switches_function(bus, "lit", "headlights", True)
    switches_function(bus, "lit", "bell", True)
    switches_function(bus, "lit", "headlights", False)

    assert on(said) == {"lit": {"headlights": False, "bell": True}}


def restarted(*retained: tuple[str, Payload]) -> InProcessBus:
    """A bus that outlived the app, holding the rows given, and a fresh app
    started on it."""
    clock = Clock()
    bus = InProcessBus(clock)
    for topic, payload in retained:
        bus.publish(topic, payload)
    bus.drain()
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    return bus


def test_a_light_a_decoder_still_has_on_shows_on_after_a_restart() -> None:
    bus = restarted(
        (f"{WANTED_FUNCTION}/5/0", {"addr": "5", "function": "0", "value": True})
    )

    assert bus.last_values[FUNCTIONS]["functions"] == {"lit": {"headlights": True}}


def test_a_retained_row_no_name_sits_on_is_left_out() -> None:
    """A car no train holds, a number the car names nothing on, a number a
    press of that name would not reach — the horn's second — and a row that
    cannot be read."""
    bus = restarted(
        (f"{WANTED_FUNCTION}/99/0", {"addr": "99", "function": "0", "value": True}),
        (f"{WANTED_FUNCTION}/5/7", {"addr": "5", "function": "7", "value": True}),
        (f"{WANTED_FUNCTION}/5/2", {"addr": "5", "function": "2", "value": True}),
        (f"{WANTED_FUNCTION}/6/1", {"addr": "6", "function": "1", "value": "on"}),
        (f"{WANTED_FUNCTION}/6/0", {"addr": "6", "function": "0", "value": True}),
    )

    assert bus.last_values[FUNCTIONS]["functions"] == {}
