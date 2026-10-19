"""Track power at the layout interface: one switch, `on`, `draining` or
`off`, answered on arrival and observed from below, and off until a person
says otherwise (#287, ADR-0051, ADR-0078).

The two halves meet on one word: what the app writes on `wanted/track` is the
supply it was asked for, and what it says on `state/power` is folded from what
the hardware reports — bar a drain, which no hardware can report and this app
therefore holds from the press until it ends, and a cut, held as `off` until
the next `on` (ADR-0063).

`off` is the emergency stop, applied at once whatever is moving. `draining`
keeps the supply on until `tc49/dispatch/state/moving` reads false, and then
cuts it as `off` does; the rule is `lib.power`'s, held to both bindings in
`tests/system/test_layout_bindings.py`. A cut leaves the railroad **at
rest**: the traction rows go to zero ahead of it, so the supply coming back
does not come back over a standing speed (#435). And `on` gives each train a
cut left between blocks the speed its grant implies, so it finishes its move.
"""

from collections.abc import Callable

from tc49.bench.runner import DEFAULT_K, NONCE, facing, placement
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.scheduler import Scheduler
from tests.harness import load
from tests.layout.railroad import (
    DEVICE_LINK,
    DEVICE_TRACK,
    DRIVING,
    POWER,
    POWER_WANTED,
    RAILROAD,
    REMOVED,
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
    moves,
    railroad,
    reads,
    settle,
    speeds,
    stand,
    stock,
    takes,
    turns,
    wired,
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


# -- the drain this app holds ------------------------------------------------


def test_a_drain_reads_as_itself_from_the_press_that_asked_for_it() -> None:
    """The supply stays on through a drain and the hardware goes on saying
    so, so the fold would read `on` and the dispatcher would route into it
    (ADR-0063). `layout` answered the drain, so `layout` holds it."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "draining")()
    bus.publish(DEVICE_TRACK, {"power": "on"})
    bus.drain()

    assert said == [
        (POWER, {"at": 0.0, "power": "on"}),
        (POWER, {"at": 0.0, "power": "draining"}),
    ]


def test_a_drain_cuts_only_once_nothing_is_moving() -> None:
    """The supply goes the first moment `state/moving` reads false, and not
    while a train is still running to its sensor (ADR-0078, decision 4)."""
    bus, _app = build()
    moves(bus, True)
    track = live(bus)
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "draining")()
    moves(bus, True)
    assert powers(track) == ["on"]
    assert said[-1] == (POWER, {"at": 0.0, "power": "draining"})

    moves(bus, False)
    assert powers(track) == ["on", "off"]
    assert said[-1] == (POWER, {"at": 0.0, "power": "off"})


def test_a_drain_over_a_railroad_standing_still_cuts_at_once() -> None:
    bus, _app = build()
    moves(bus, False)
    track = live(bus)

    commands(bus, "draining")()

    assert powers(track) == ["on", "off"]
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_no_moving_row_is_a_train_moving() -> None:
    """No dispatcher has said anything, and an absence is not evidence that
    nothing moves: the drain waits, and a person has `off`."""
    bus, _app = build()
    track = live(bus)

    commands(bus, "draining")()

    assert powers(track) == ["on"]
    assert bus.last_values[POWER] == {"at": 0.0, "power": "draining"}


def test_a_drain_under_a_train_partway_along_its_route_cuts() -> None:
    """The drain the band's off press makes, under a train with a route of
    three moves: the move granted runs to its sensor, the train stands in the
    block it entered with its route and its locks, and nothing stands to be
    stranded, so the supply goes off (#844, ADR-0078 decision 4).

    The dispatcher, scheduler and driver are the real ones on this app's bus,
    because what is under test is the meeting of the two: when the
    dispatcher's `state/moving` says a train standing on its route is not
    moving, and that this app ends the drain on it."""
    layout, roster, scenario = load("crossover-yard/meet")
    clock = Clock()
    bus = InProcessBus(clock)
    stood = placement(scenario.trains)
    app = LayoutInterface(bus, layout, roster, clock, position=stood)
    Scheduler(bus, layout, facing(layout, scenario.trains), nonce=NONCE)
    dispatcher = Dispatcher(bus, layout, roster, stood, Incremental(layout, DEFAULT_K))
    Driver(bus)
    track = live(bus)
    bus.publish(
        "tc49/schedule/request_wanted", {"train": "freight_1", "dest": ["yard_e.A"]}
    )
    bus.drain()

    commands(bus, "draining")()
    assert powers(track) == ["on"]
    assert bus.last_values[POWER]["power"] == "draining"

    reads(bus, "dn_w.A", "occupied")
    reads(bus, "dn_w.B", "occupied")
    settle(bus, app, clock)

    assert powers(track) == ["on", "off"]
    assert bus.last_values[POWER]["power"] == "off"
    assert dispatcher.state.block_of["freight_1"] == "dn_w"
    assert "freight_1" in dispatcher.state.active


def test_on_during_a_drain_ends_it() -> None:
    """A person asking for `on` during a drain ends it (ADR-0078), and the
    railroad is the fold's again: the trains that were stopping carry on,
    and nothing moving reading false afterwards cuts nothing."""
    bus, _app = build()
    moves(bus, True)
    track = live(bus)
    commands(bus, "draining")()

    commands(bus, "on")()
    moves(bus, False)

    assert powers(track) == ["on", "on"]
    assert bus.last_values[POWER] == {"at": 0.0, "power": "on"}


def test_a_drain_from_off_is_dropped() -> None:
    """From `on` only: there is nothing running to drain, and a drain over a
    dark railroad would be one that read the supply back on."""
    bus, _app = build()
    moves(bus, False)
    track = live(bus)
    commands(bus, "off")()
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "draining")()

    assert powers(track) == ["on", "off"]
    assert said == [(POWER, {"at": 0.0, "power": "off"})]


def test_a_press_that_cannot_be_read_commands_nothing() -> None:
    """`stopped` among them: the emergency stop with the track live is the
    word ADR-0078 retires."""
    bus, _app = build()
    energised(bus)
    said = heard(bus, POWER)
    written = heard(bus, WANTED_TRACK)
    bus.drain()

    bus.publish(POWER_WANTED, {"power": "sideways"})
    bus.publish(POWER_WANTED, {"power": "stopped"})
    bus.publish(POWER_WANTED, {})
    bus.drain()

    # The values the subscriptions were owed, and nothing after them.
    assert said == [(POWER, {"at": 0.0, "power": "on"})]
    assert powers(written) == ["off"]


# -- the emergency stop -------------------------------------------------------


def test_off_cuts_while_a_train_is_moving() -> None:
    """The emergency stop: at once, with no guard (ADR-0078, decision 5)."""
    bus, _app = build()
    moves(bus, True)
    track = live(bus)

    commands(bus, "off")()

    assert powers(track) == ["on", "off"]
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}


def test_a_cut_reads_off_before_the_hardware_says_so() -> None:
    """The supply reports live until it has gone, and a row read as `on` in
    that moment is a railroad the dispatcher routes."""
    bus, _app = build()
    live(bus)
    said = heard(bus, POWER)
    bus.drain()

    commands(bus, "off")()
    energised(bus)

    assert said == [
        (POWER, {"at": 0.0, "power": "on"}),
        (POWER, {"at": 0.0, "power": "off"}),
    ]


def test_the_fold_answers_again_on_on() -> None:
    """The held `off` stands until `on` and not after: what the hardware
    said meanwhile is what the row reads on the press, rather than an `on`
    this app has taken its own word for."""
    bus, _app = build()
    live(bus)
    commands(bus, "off")()
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()

    commands(bus, "on")()
    assert bus.last_values[POWER] == {"at": 0.0, "power": "off"}

    energised(bus)
    assert bus.last_values[POWER] == {"at": 0.0, "power": "on"}


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

    commands(bus, "off")()

    assert speeds(written) == [("3", 0.5), ("3", 0.0)]


def test_the_zero_goes_out_before_the_supply_is_cut() -> None:
    """Ordering is load-bearing. The translator acts on desired rows as they
    arrive, so zeros first means the last thing the station is told before the
    supply goes is a stop."""
    bus, _app = build()
    live(bus)
    hand_driven(bus)
    written = desired(bus)

    commands(bus, "off")()

    assert topics(written) == [f"{WANTED_TRACTION}/3", WANTED_TRACK]


def test_a_drain_ending_writes_zero_over_a_standing_traction_row() -> None:
    """The end of a drain is a cut like any other, and leaves the railroad at
    rest the same way, zeros first."""
    bus, _app = build()
    moves(bus, True)
    live(bus)
    hand_driven(bus)
    commands(bus, "draining")()
    written = desired(bus)

    moves(bus, False)

    assert topics(written) == [f"{WANTED_TRACTION}/3", WANTED_TRACK]
    assert written[0][1]["speed"] == 0.0


def test_a_drain_leaves_the_rows_where_they_stand() -> None:
    """Not on `draining`. The supply stays on and each moving train runs to
    the end of its move, so zeroing a row there would strand it between two
    blocks."""
    bus, _app = build()
    moves(bus, True)
    live(bus)
    written = commanded(bus)
    hand_driven(bus)

    commands(bus, "draining")()

    assert speeds(written) == [("3", 0.5)]


# -- `on` resumes ---------------------------------------------------------------


def crossing(bus: InProcessBus) -> None:
    """`single` under way on a grant the driver drives, in `automatic`."""
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)


def test_on_after_off_restores_a_crossing_trains_speed() -> None:
    """A train a cut left between blocks finishes its move (ADR-0078,
    decision 6): the press gives it the speed its grant implies, on the
    press and not when the hardware reports the supply back."""
    bus, _app = build()
    live(bus)
    written = commanded(bus)
    crossing(bus)
    commands(bus, "off")()
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()

    commands(bus, "on")()

    assert speeds(written) == [("3", 0.6), ("3", 0.0), ("3", 0.6)]


def test_on_restores_nothing_for_a_train_that_has_arrived() -> None:
    bus, app, clock = wired()
    live(bus)
    written = commanded(bus)
    crossing(bus)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    commands(bus, "off")()

    commands(bus, "on")()

    assert speeds(written) == [("3", 0.6), ("3", 0.0), ("3", 0.0)]


def test_on_leaves_a_train_a_throttle_holds_to_the_person() -> None:
    """Its speed is the person's (#825), and the cut left it at zero."""
    bus, _app = build()
    live(bus)
    written = commanded(bus)
    hand_driven(bus)
    commands(bus, "off")()

    commands(bus, "on")()

    assert speeds(written) == [("3", 0.5), ("3", 0.0)]


def test_on_in_manual_writes_nothing() -> None:
    """In `manual` a train no throttle holds stands at its signal, and the
    ones that carry on are those a throttle holds (#825)."""
    bus, _app = build(driving="manual")
    live(bus)
    written = commanded(bus)
    crossing(bus)
    commands(bus, "off")()

    commands(bus, "on")()

    assert speeds(written) == []


# -- a move granted as the power goes is kept ----------------------------------


def granted(bus: InProcessBus) -> None:
    """`single`'s move and its `align` arriving after the press that took the
    power, the dispatcher not having read it yet when it granted the move."""
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)


def drained(bus: InProcessBus) -> None:
    """A railroad somebody turned on and then drained, the drain over and the
    supply reporting it has gone."""
    moves(bus, True)
    live(bus)
    commands(bus, "draining")()
    moves(bus, False)
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()


def test_a_move_granted_while_draining_runs_to_its_sensor() -> None:
    """The supply is on through a drain and the move was granted, so it is
    acted on as it is while `on`, and the drain ends at the next `moving:
    false` (ADR-0078, decision 4)."""
    bus, app = build()
    moves(bus, True)
    track = live(bus)
    written = commanded(bus)
    commands(bus, "draining")()

    granted(bus)

    assert app.position == {"single": "dn_e"}
    assert speeds(written) == [("3", 0.6)]
    assert powers(track) == ["on"]
    moves(bus, False)
    assert powers(track) == ["on", "off"]


def test_a_move_granted_after_a_drain_is_kept_until_on() -> None:
    """Dead rails act on no move, and `on` resumes every granted one
    (ADR-0078, decision 6) — once the supply reports it back, since that is
    when `state/power` reads `on`."""
    bus, app = build()
    drained(bus)
    written = commanded(bus)

    granted(bus)
    assert app.position == {"single": "up_w"}
    assert speeds(written) == []

    commands(bus, "on")()
    energised(bus)

    assert app.position == {"single": "dn_e"}
    assert speeds(written) == [("3", 0.6)]


def test_a_kept_move_waits_for_an_align_that_also_lands_dead() -> None:
    """The `align` arriving after the `move`, both over dead rails: the points
    are written and the crossing authorised all the same, the rows being
    stored for when the rails come back (ADR-0054), and at `on` the kept move
    finds its `align` landed."""
    bus, app = build()
    drained(bus)
    written = commanded(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    align(bus, "crossover", "to_dn")
    assert app.position == {"single": "up_w"}

    commands(bus, "on")()
    energised(bus)

    assert app.position == {"single": "dn_e"}
    assert speeds(written) == [("3", 0.6)]


def test_a_kept_move_for_a_train_taken_off_is_dropped_at_on() -> None:
    """The near-end check is applied again when the kept move is acted on,
    and a train no longer on the layout fails it."""
    bus, app = build()
    drained(bus)
    written = commanded(bus)
    granted(bus)
    bus.publish(REMOVED, {"train": "single"})
    bus.drain()

    commands(bus, "on")()
    energised(bus)

    assert "single" not in app.position
    assert speeds(written) == [("3", 0.0)], "the removal's zero, and nothing at on"


def test_a_move_granted_after_an_emergency_stop_is_kept_until_on() -> None:
    bus, app = build()
    live(bus)
    commands(bus, "off")()
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    written = commanded(bus)

    granted(bus)
    assert app.position == {"single": "up_w"}
    assert speeds(written) == []

    commands(bus, "on")()
    energised(bus)

    assert app.position == {"single": "dn_e"}
    assert speeds(written) == [("3", 0.6)]


def test_a_kept_move_in_manual_is_a_crossing_with_no_speed_at_on() -> None:
    """As any `manual` move is: the route and not the driving (ADR-0079)."""
    bus, app = build(driving="manual")
    drained(bus)
    written = commanded(bus)
    granted(bus)

    commands(bus, "on")()
    energised(bus)

    assert app.position == {"single": "dn_e"}
    assert speeds(written) == []
