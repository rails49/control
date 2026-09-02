"""What a signal is told to show (#287, #203).

The dispatcher publishes an aspect per signalled block end, and this app is
what turns each into a value on the signal standing there. The lookup is here
because `tc49/dispatch/state/aspects` is read by the panel and by a person
driving by eye, and neither of them wants an address.
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    ASPECTS,
    WANTED_SIGNAL,
    Unstamped,
    build,
    heard,
    railroad,
    stock,
)


def signals(bus: Bus) -> list[tuple[str, Payload]]:
    return heard(bus, WANTED_SIGNAL + "/#")


def show(bus: Bus, shown: dict[str, str]) -> None:
    bus.publish(ASPECTS, {"aspects": shown})
    bus.drain()


def test_each_signalled_end_is_written_to_the_signal_standing_there() -> None:
    bus, _app = build()
    written = signals(bus)
    show(bus, {"up_w.B": "clear"})

    assert written == [
        (
            WANTED_SIGNAL + "/dccex/40",
            {"at": 0.0, "addr": "dccex/40", "aspect": "clear"},
        )
    ]


def test_an_end_no_signal_stands_at_writes_nothing() -> None:
    """An end nothing ever leaves carries no signal, one that could only show
    `stop` being furniture (CONTEXT.md, **Signal**). There is nothing to tell,
    and inventing an address for it is the one thing this app must not do."""
    bus, _app = build()
    written = signals(bus)
    show(bus, {"up_w.A": "stop", "up_e.B": "caution"})

    assert written == []


def test_the_opening_value_seeds_every_signal_with_stop() -> None:
    """No rule of its own is needed: a held run puts every signal to stop and
    the dispatcher's value names every signalled end, so the retained value
    this app is handed on subscribing is the seed (ADR-0032)."""
    clock = Clock()
    bus = Bus(clock)
    bus.publish(ASPECTS, {"aspects": {"up_w.B": "stop", "up_e.A": "stop"}})
    bus.drain()

    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert bus.last_values[WANTED_SIGNAL + "/dccex/40"] == {
        "at": 0.0,
        "addr": "dccex/40",
        "aspect": "stop",
    }
    assert bus.last_values[WANTED_SIGNAL + "/dccex/41"] == {
        "at": 0.0,
        "addr": "dccex/41",
        "aspect": "stop",
    }


def test_two_ends_on_one_address_show_one_aspect_together() -> None:
    """A wiring fact and not a fault (ADR-0031): the two are written in the
    order the picture states them and the last stands, which is what one
    accessory output driving two heads does."""
    bus, _app = build()
    written = signals(bus)
    show(bus, {"up_e.A": "clear", "dn_e.A": "caution"})

    assert [payload["aspect"] for _topic, payload in written] == ["clear", "caution"]
    assert bus.last_values[WANTED_SIGNAL + "/dccex/41"]["aspect"] == "caution"


def test_every_end_is_written_again_on_every_picture() -> None:
    """The whole picture each time, as the dispatcher publishes it: a
    translator acts on every desired value it hears, never only on change
    (ADR-0043)."""
    bus, _app = build()
    written = signals(bus)
    show(bus, {"up_w.B": "stop"})
    show(bus, {"up_w.B": "stop"})

    assert len(written) == 2


def test_a_picture_older_than_the_one_held_is_ignored() -> None:
    """Delivered backwards, the older value would leave a signal showing an
    aspect the railroad has moved on from — and `state/aspects` keeps its last
    message, so it would stand for good (#240)."""
    clock = Clock()
    bus = Unstamped(clock)
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    bus.publish(ASPECTS, {"at": 20.0, "aspects": {"up_w.B": "clear"}})
    bus.drain()
    written = signals(bus)
    bus.drain()  # the value already standing, which a late subscriber is owed
    assert len(written) == 1

    bus.publish(ASPECTS, {"at": 10.0, "aspects": {"up_w.B": "stop"}})
    bus.drain()

    assert len(written) == 1
    assert bus.last_values[WANTED_SIGNAL + "/dccex/40"]["aspect"] == "clear"
