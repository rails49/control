"""Track power at the layout interface: commanded on arrival, observed from
below, and off until a person says otherwise (#287, ADR-0051).

The two halves never meet: what the app writes on `wanted/track` is the word
it was told to write, and what it says on `state/power` is folded from what
the hardware reports. Commanding power is not observing it.
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import Bus
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    DEVICE_LINK,
    DEVICE_TRACK,
    MODE,
    POWER,
    POWER_WANTED,
    WANTED_TRACK,
    build,
    energised,
    heard,
    railroad,
    stock,
)


def test_the_railroad_comes_up_off_before_anything_else() -> None:
    """Nothing moves and no turnout throws until a person turns it on
    (ADR-0051). The three values are the first things the app says, and the
    order is the honest one: the supply is commanded off, then the app states
    what it believes about it, and then that nobody has taken a train — the
    map of who drives is empty and the topic says so (#297)."""
    clock = Clock()
    bus = Bus(clock)
    seen = heard(bus, "tc49/#")
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert seen == [
        (WANTED_TRACK, {"at": 0.0, "power": "off"}),
        (POWER, {"at": 0.0, "power": "off"}),
        (MODE, {"at": 0.0, "modes": {}}),
    ]


def test_the_value_is_retained_for_a_client_that_joins_later() -> None:
    """A joining client is served a value rather than left to read one out of
    an absence (ADR-0032), and every consumer of the layout is built before
    the layout is."""
    bus, _app = build()
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}
    assert bus.last_values[WANTED_TRACK] == {"at": 0.0, "power": "off"}


def test_a_command_writes_the_word_and_says_nothing_about_the_railroad() -> None:
    """`layout` cannot verify that the supply arrived and does not try: it
    assumes the device it commanded did what it was asked (#232). So ON
    reaches the hardware and `state/power` does not move."""
    bus, _app = build()
    said = heard(bus, POWER)
    written = heard(bus, WANTED_TRACK)
    bus.drain()

    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()

    assert written[-1] == (WANTED_TRACK, {"at": 0.0, "power": "on"})
    assert said == [(POWER, {"at": 0.0, "power": "off"})]


def test_the_railroad_reads_on_only_once_the_hardware_says_so() -> None:
    """The fold, and the whole of it: the supply's own word, once every link
    ever seen is up."""
    bus, _app = build()
    said = heard(bus, POWER)
    bus.drain()

    energised(bus)
    assert said[-1] == (POWER, {"at": 0.0, "power": "on"})


def test_an_emergency_stop_is_reported_as_itself() -> None:
    """`stopped` and `off` differ for the person recovering — one is cleared
    and the other switched back on — and the dispatcher branches on "not
    `on`" either way (ADR-0041)."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()

    bus.publish(DEVICE_TRACK, {"power": "stopped"})
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "stopped"})


def test_a_link_going_down_takes_the_power_off_on() -> None:
    """With no word from the supply at all: a translator that cannot reach
    its hardware leaves a railroad no train may move on, whatever the supply
    says — the translator saying it may be the unreachable one."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/dccex", {"system": "dccex", "link": "up"})
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "on"})

    bus.publish(
        DEVICE_LINK + "/dccex",
        {"system": "dccex", "link": "down", "detail": "no route to host"},
    )
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "off"})
    # The supply never said a word: the fold moved on the link alone.
    assert bus.last_values[DEVICE_TRACK] == {"at": 0.0, "power": "on"}


def test_a_link_that_has_gone_holds_the_railroad_off() -> None:
    """ "Ever seen" and not "currently connected": a link is a retained level,
    so a translator that published `down` and then died leaves the value
    standing, and forgetting it would turn a broken railroad back on
    (ADR-0050)."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/dccex", {"system": "dccex", "link": "down"})
    energised(bus)
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_one_system_down_is_the_whole_railroad_down() -> None:
    """A railroad may be driven by two hardware systems at once (ADR-0043),
    and every one of them has to be reachable."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/dccex", {"system": "dccex", "link": "up"})
    bus.publish(DEVICE_LINK + "/jmri", {"system": "jmri", "link": "up"})
    energised(bus)
    assert bus.last_values[POWER] == {"at": 0.0, "power": "on"}

    bus.publish(DEVICE_LINK + "/jmri", {"system": "jmri", "link": "down"})
    bus.drain()
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_it_never_writes_off_of_its_own_accord() -> None:
    """After the opening `off` the app writes the word it was told to write
    and nothing else — the supply going away below it moves `state/power` and
    never `wanted/track`, which is a person's to command."""
    bus, _app = build()
    energised(bus)
    written = heard(bus, WANTED_TRACK)
    bus.drain()

    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.publish(DEVICE_LINK + "/dccex", {"system": "dccex", "link": "down"})
    bus.drain()

    assert written == [(WANTED_TRACK, {"at": 0.0, "power": "off"})]
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_the_fold_says_nothing_twice() -> None:
    """A state topic republishing the value it already holds is noise on the
    trace and news to nobody, so only a move is published."""
    bus, _app = build()
    said = heard(bus, POWER)
    bus.drain()

    energised(bus)
    energised(bus)
    bus.publish(DEVICE_LINK + "/dccex", {"system": "dccex", "link": "up"})
    bus.drain()

    assert said == [
        (POWER, {"at": 0.0, "power": "off"}),
        (POWER, {"at": 0.0, "power": "on"}),
    ]
