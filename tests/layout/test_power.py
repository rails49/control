"""Track power at the layout interface: commanded on arrival, observed from
below, and off until a person says otherwise (#287, ADR-0051).

The two halves never meet: what the app writes on `wanted/track` is the word
it was told to write, and what it says on `state/power` is folded from what
the hardware reports. Commanding power is not observing it.

One command is not written through as it came. A plain `off` is applied only
where nothing is moving, because a topic names the app that answers it and
never the process that sent the frame, so the drain-first check is made here
rather than trusted to the sender (ADR-0062, #407).
"""

import logging
from collections.abc import Callable

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    DEVICE_LINK,
    DEVICE_TRACK,
    MODE,
    POWER,
    POWER_WANTED,
    RUN,
    WANTED_TRACK,
    build,
    energised,
    heard,
    railroad,
    runs,
    stock,
)


class Kept(logging.Handler):
    """Every line the app logged, which is where a refused gesture says why."""

    def __init__(self) -> None:
        super().__init__()
        self.said: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.said.append(record.getMessage())


def refusals(commanding: Callable[[], None]) -> list[str]:
    """What the app said to a person while `commanding` ran: a gesture it
    cannot act on is dropped in silence and to the trace with its reason, and
    the log is where that reason is (ADR-0034)."""
    kept = Kept()
    log = logging.getLogger("tc49.layout.interface")
    log.addHandler(kept)
    log.setLevel(logging.INFO)
    try:
        commanding()
    finally:
        log.removeHandler(kept)
    return kept.said


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


def test_the_railroad_comes_up_off_before_anything_else() -> None:
    """Nothing moves and no turnout throws until a person turns it on
    (ADR-0051). The three values are the first things the app says, and the
    order is the honest one: the supply is commanded off, then the app states
    what it believes about it, and then that nobody has taken a train — the
    map of who drives is empty and the topic says so (#297)."""
    clock = Clock()
    bus = InProcessBus(clock)
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


def test_off_applies_where_the_run_is_held_and_nothing_moves() -> None:
    """The drain is done: the dispatcher commits nothing further and nothing
    is between blocks, so removing the supply strands nobody."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "held", moving=False)
    said = refusals(commands(bus, "off"))

    assert powers(written) == ["on", "off"]
    assert said == []


def test_off_applies_where_no_run_has_ever_been_stated() -> None:
    """No `state/run` is not evidence that something moves: with no
    dispatcher up nothing has been granted, and a railroad that could not be
    turned off would be worse than the race the guard is for (ADR-0062)."""
    bus, _app = build()
    written = live(bus)

    said = refusals(commands(bus, "off"))

    assert powers(written) == ["on", "off"]
    assert said == []


def test_off_is_refused_while_a_train_is_moving_under_a_held_run() -> None:
    """`held` does not mean nothing is moving: a held run is a brake on
    committing, and a move already granted runs to its sensor. This is the
    case the panel's wait used to be satisfied by wrongly — one panel drains,
    a second holds, the first cuts, and a train strands."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "held", moving=True)
    said = refusals(commands(bus, "off"))

    assert powers(written) == ["on"]
    assert said == ["power off refused: a train is moving"]


def test_off_is_refused_while_the_run_is_running() -> None:
    """`held` and not merely "not moving": an `off` on a running run with
    nothing granted would race the dispatcher's next grant by milliseconds."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "running", moving=False)
    said = refusals(commands(bus, "off"))

    assert powers(written) == ["on"]
    assert said == ["power off refused: the run reads running"]


def test_off_is_refused_while_a_drain_is_still_running_out() -> None:
    """A drain launches nothing more and lets what is under way finish, so
    the supply is exactly what may not go yet. Both reasons are named: the
    person reading the trace wants to know which of the two would clear."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "draining", moving=True)
    said = refusals(commands(bus, "off"))

    assert powers(written) == ["on"]
    assert said == ["power off refused: the run reads draining and a train is moving"]


def test_a_refused_off_is_not_held_for_later() -> None:
    """An intention kept would be the panel's stale wait moved server-side,
    and this app answers nothing that could clear it. The drain completing is
    not the press coming back: somebody has to press again."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "draining", moving=True)
    commands(bus, "off")()
    runs(bus, "held", moving=False)

    assert powers(written) == ["on"]


def test_on_and_stopped_write_through_in_every_run_state() -> None:
    """An emergency stop asks the rails for less and returning to `on`
    releases nothing, so neither is guarded (ADR-0041, ADR-0051)."""
    bus, _app = build()
    written = live(bus)

    for run in ("running", "draining", "held"):
        for moving in (True, False):
            runs(bus, run, moving=moving)
            commands(bus, "stopped")()
            commands(bus, "on")()

    assert powers(written) == ["on"] + ["stopped", "on"] * 6


def test_a_run_row_that_cannot_be_read_leaves_the_evidence_where_it_was() -> None:
    """Forgetting what the dispatcher said on one bad frame would leave this
    app with no evidence, and no evidence applies an `off`."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "held", moving=True)
    bus.publish(RUN, {"run": "drained"})
    bus.publish(RUN, {"run": "held", "moving": "no"})
    bus.drain()
    commands(bus, "off")()

    assert powers(written) == ["on"]


def test_a_row_without_moving_is_a_dispatcher_saying_nothing_moves() -> None:
    """An older dispatcher says nothing about what is under way, and an
    absence is not evidence that a train is in motion (#406)."""
    bus, _app = build()
    written = live(bus)

    bus.publish(RUN, {"run": "held"})
    bus.drain()
    commands(bus, "off")()

    assert powers(written) == ["on", "off"]


def test_the_run_this_app_reads_is_the_last_one_stated() -> None:
    """The guard is made against current state on arrival, as every other
    browser-writable gesture is: a run that has moved on since a cut was
    refused is the run the next one is judged by."""
    bus, _app = build()
    written = live(bus)

    runs(bus, "running", moving=True)
    commands(bus, "off")()
    assert powers(written) == ["on"]

    runs(bus, "held", moving=False)
    commands(bus, "off")()
    assert powers(written) == ["on", "off"]
