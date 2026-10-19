"""Track power at the layout interface: commanded on arrival, observed from
below, and off until a person says otherwise (#287, ADR-0051).

The two halves meet on one word and nowhere else: what the app writes on
`wanted/track` is the word it was told to write, and what it says on
`state/power` is folded from what the hardware reports. Commanding power is
not observing it — bar the emergency stop, which no hardware can report and
this app therefore holds from the command it wrote until a person asks for
the power back (ADR-0063, #470).

One command is not written through as it came. A plain `off` is applied only
where nothing is moving, because a topic names the app that answers it and
never the process that sent the frame, so the drain-first check is made here
rather than trusted to the sender (ADR-0062, #407); that guard is
`lib.power`'s, held to both bindings in `tests/system/test_layout_bindings.py`.
And an `off` that is applied leaves the railroad **at rest**: the traction rows
go to zero ahead of the cut, so the supply coming back does not come back over
a standing speed (#435).
"""

from collections.abc import Callable

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    DEVICE_LINK,
    DEVICE_TRACK,
    DRIVING,
    POWER,
    POWER_WANTED,
    RAILROAD,
    TAKEN,
    WANTED_TRACK,
    WANTED_TRACTION,
    align,
    build,
    commanded,
    energised,
    faces,
    heard,
    move,
    railroad,
    runs,
    speeds,
    stand,
    stock,
    takes,
    turns,
)

WANTED = "tc49/layout/state/wanted/#"
"""Every desired row at once, which is where the order two of them go out in
is visible: a translator acts on each as it arrives."""


def live(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """A railroad somebody has turned on, and every `wanted/track` write from
    there on.

    The `on` leads the list because a state filter is handed the value it is
    owed on subscribing (ADR-0032), and turning it on first is what makes an
    `off` that was applied tell itself apart from the one the app came up
    having written."""
    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()
    energised(bus)
    written = heard(bus, WANTED_TRACK)
    bus.drain()
    return written


def powers(written: list[tuple[str, Payload]]) -> list[str]:
    """Those writes as the words they carry, which is what these assert: the
    stamp is the row's shape rather than this write's news."""
    return [str(payload["power"]) for _topic, payload in written]


def commands(bus: InProcessBus, power: str) -> Callable[[], None]:
    """Somebody publishing a power gesture — a person's panel, a raw client,
    a test or a later UI: the topic says which of them it was, which is
    nothing at all."""

    def press() -> None:
        bus.publish(POWER_WANTED, {"power": power})
        bus.drain()

    return press


def desired(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every desired row written from here on, in order, whichever row it is.

    The values a subscription is owed arrive first and are dropped: what a
    gesture writes is the news, and what stood on the topics before it is the
    railroad the gesture arrived at."""
    written = heard(bus, WANTED)
    bus.drain()
    written.clear()
    return written


def topics(written: list[tuple[str, Payload]]) -> list[str]:
    """Those writes as the topics they went out on: which row, in what order.
    Ordering is load-bearing between the two of them and the payloads are
    asserted elsewhere."""
    return [topic for topic, _payload in written]


def hand_driven(bus: InProcessBus) -> None:
    """A person holding `single` in a throttle with the lever off zero, the
    train under way on a grant (ADR-0079).

    The row nothing else zeroes until the train arrives, and an `off` comes
    before any arrival (#435)."""
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    turns(bus, "single", 0.5)
    bus.drain()


def test_the_railroad_comes_up_off_before_anything_else() -> None:
    """Nothing moves and no turnout throws until a person turns it on
    (ADR-0051). The four values are the first things the app says, and the
    order is the honest one: which railroad this is (#371), then the supply
    commanded off, then what the app believes about it, and then who drives:
    people, with no train in a throttle (ADR-0079)."""
    clock = Clock()
    bus = InProcessBus(clock)
    seen = heard(bus, "tc49/#")
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert seen == [
        (RAILROAD, {"at": 0.0, "name": "bench"}),
        (WANTED_TRACK, {"at": 0.0, "power": "off"}),
        (POWER, {"at": 0.0, "power": "off"}),
        (DRIVING, {"at": 0.0, "driving": "manual"}),
        (TAKEN, {"at": 0.0, "taken": {}}),
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


def test_the_supply_cannot_report_an_emergency_stop() -> None:
    """An emergency stop leaves the rails live, so the supply reads `on`
    under one and the observed row has no third value to say it with
    (ADR-0063). A frame that says it anyway says what no hardware can
    observe, and is refused like any other value outside the closed set —
    falling to `off`, the direction a supply that cannot be read fails in."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()

    bus.publish(DEVICE_TRACK, {"power": "stopped"})
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "off"})


# -- the emergency stop this app holds ---------------------------------------


def test_an_emergency_stop_reads_as_itself_from_the_command_that_asked_for_it() -> None:
    """The one value on this row that is not folded from hardware, because no
    hardware can hold it: a stop leaves the rails live, so the supply reads
    `on` under one and a second after the press the fold would call the
    railroad good again (ADR-0063). `layout` wrote `stopped`, so `layout`
    holds it — and the person who pressed it has the row saying the railroad
    is waiting for them (ADR-0041)."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "stopped")()

    assert said[-1] == (POWER, {"at": 0.0, "power": "stopped"})


def test_the_hardware_saying_the_rails_are_live_does_not_clear_it() -> None:
    """Which is the whole reason it is held. The supply is live under an
    emergency stop and goes on saying so, and a row that took the hardware's
    word here would clear the stop nobody has cleared."""
    bus, _app = build()
    energised(bus)
    commands(bus, "stopped")()
    said = heard(bus, POWER)
    bus.drain()

    bus.publish(DEVICE_TRACK, {"power": "on"})
    bus.drain()

    assert said == [(POWER, {"at": 0.0, "power": "stopped"})]


def test_the_power_command_a_person_reaches_for_to_resume_clears_it() -> None:
    """`power_wanted: on` — the railroad's own power control, and no second
    topic, no fourth value and no new button. It is what a person presses to
    drive again, and the stop is cleared by the same press that asks for the
    railroad back (ADR-0063)."""
    bus, _app = build()
    energised(bus)
    commands(bus, "stopped")()
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "on")()

    assert said[-1] == (POWER, {"at": 0.0, "power": "on"})


def test_the_fold_answers_again_once_the_stop_is_cleared() -> None:
    """The held value outranks the fold while it is held and not after: what
    the hardware said in the meantime is what the row reads on the clearing
    press, rather than an `on` this app has taken its own word for."""
    bus, _app = build()
    energised(bus)
    commands(bus, "stopped")()
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "on")()

    assert said[-1] == (POWER, {"at": 0.0, "power": "off"})


def test_an_off_does_not_clear_it_and_the_row_does_not_flicker_on() -> None:
    """`on` alone clears it. A cut is commanded and not observed, so clearing
    on the press would publish the fold's answer — `on`, the hardware still
    reporting the supply it has not yet lost — in the moment this app is
    asking for the supply to go. The stop stands over a dark railroad
    instead, both words holding the run either way (ADR-0041)."""
    bus, _app = build()
    energised(bus)
    commands(bus, "stopped")()
    runs(bus, "held", moving=False)
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "off")()
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()

    assert said == [(POWER, {"at": 0.0, "power": "stopped"})]


def test_a_stop_this_app_never_commanded_is_not_held() -> None:
    """A gesture that was refused or could not be read commanded nothing, and
    a row that moved on it would report an emergency stop the railroad was
    never asked for."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()

    bus.publish(POWER_WANTED, {"power": "sideways"})
    bus.publish(POWER_WANTED, {})
    bus.drain()

    # The value the subscription was owed, and nothing after it.
    assert said == [(POWER, {"at": 0.0, "power": "on"})]


def test_a_link_going_down_takes_the_power_off_on() -> None:
    """With no word from the supply at all: a participant that cannot reach
    its hardware leaves a railroad no train may move on, whatever the supply
    says — the participant saying it may be the unreachable one."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "up"})
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "on"})

    bus.publish(
        DEVICE_LINK + "/shed",
        {"id": "shed", "link": "down", "detail": "no route to host"},
    )
    bus.drain()
    assert said[-1] == (POWER, {"at": 0.0, "power": "off"})
    # The supply never said a word: the fold moved on the link alone.
    assert bus.last_values[DEVICE_TRACK] == {"at": 0.0, "power": "on"}


def test_a_link_that_has_gone_holds_the_railroad_off() -> None:
    """ "Ever seen" and not "currently connected": a link is a retained level,
    so a publisher that said `down` and then died leaves the value standing,
    and forgetting it would turn a broken railroad back on (ADR-0050)."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "down"})
    energised(bus)
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_one_publisher_down_is_the_whole_railroad_down() -> None:
    """A railroad may have several participants driving hardware at once, and
    every one of them has to be reachable. Each keeps its own row under the
    id it calls itself — no drawing and no list of ours names either — so the
    second's `up` does not erase the first's `down` (ADR-0059)."""
    bus, _app = build()
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "up"})
    bus.publish(DEVICE_LINK + "/yard", {"id": "yard", "link": "up"})
    energised(bus)
    assert bus.last_values[POWER] == {"at": 0.0, "power": "on"}

    bus.publish(DEVICE_LINK + "/yard", {"id": "yard", "link": "down"})
    bus.drain()
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}

    # The one that is still up says so again, and the railroad stays off:
    # the fold reads every id it has heard and not the latest word.
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "up"})
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
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "down"})
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
    bus.publish(DEVICE_LINK + "/shed", {"id": "shed", "link": "up"})
    bus.drain()

    assert said == [
        (POWER, {"at": 0.0, "power": "off"}),
        (POWER, {"at": 0.0, "power": "on"}),
    ]


# -- a cut leaves the railroad at rest ---------------------------------------


def test_an_applied_off_writes_zero_over_a_standing_traction_row() -> None:
    """ "The railroad comes up at rest" is a promise about a **power off** and
    the `on` after it as well as about a process start (#435, ADR-0054).
    Nothing else writes this row down: the arrival zero reaches only a train
    this app drives, so a plain `off` would otherwise leave a person's lever
    standing in the row and the next `on` would bring current back over it."""
    bus, _app = build()
    live(bus)
    written = commanded(bus)
    hand_driven(bus)
    runs(bus, "held", moving=False)

    commands(bus, "off")()

    assert speeds(written) == [("3", 0.5), ("3", 0.0)]


def test_the_zero_goes_out_before_the_supply_is_cut() -> None:
    """Ordering is load-bearing. The translator acts on desired rows as they
    arrive, so zeros first means the last thing the station is told before the
    supply goes is a stop."""
    bus, _app = build()
    live(bus)
    hand_driven(bus)
    runs(bus, "held", moving=False)
    written = desired(bus)

    commands(bus, "off")()

    assert topics(written) == [f"{WANTED_TRACTION}/3", WANTED_TRACK]


def test_an_emergency_stop_leaves_the_rows_where_they_stand() -> None:
    """Not on `stopped`. STOP asks the rails for less and the run is meant to
    resume from it, so zeroing the rows there would turn an emergency stop
    into a re-drive (ADR-0041)."""
    bus, _app = build()
    live(bus)
    written = commanded(bus)
    hand_driven(bus)
    runs(bus, "held", moving=False)

    commands(bus, "stopped")()

    assert speeds(written) == [("3", 0.5)]


def test_an_off_refused_for_a_moving_train_leaves_the_rows_alone() -> None:
    """A refused gesture changes nothing (ADR-0062): nothing was cut, so
    nothing is at rest, and a train running to its sensor is the last one to
    take a zero."""
    bus, _app = build()
    track = live(bus)
    written = commanded(bus)
    hand_driven(bus)
    runs(bus, "held", moving=True)

    commands(bus, "off")()

    assert speeds(written) == [("3", 0.5)]
    assert powers(track) == ["on"]


def test_an_off_refused_for_a_running_run_leaves_the_rows_alone() -> None:
    """The other refusal, and the same answer: the zeros ride with the cut
    and there was no cut."""
    bus, _app = build()
    track = live(bus)
    written = commanded(bus)
    hand_driven(bus)
    runs(bus, "running", moving=False)

    commands(bus, "off")()

    assert speeds(written) == [("3", 0.5)]
    assert powers(track) == ["on"]
