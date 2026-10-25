"""The traction write: which locomotive, how fast, which way (#296).

The last thing between the device vocabulary and a wheel turning. A `move`
carries a magnitude, and the sign is composed here out of two facts neither
of which is on the command: whether the move leaves the end the train faces —
`tc49/schedule/state/facing`, the scheduler's, there being nowhere else facing
lives (ADR-0045) — and which way round each car of the train is coupled.

The bench railroad's `to_dn` runs `up_w.B` to `dn_e.A`, so a train standing in
`up_w` departs through `up_w.B`: facing `up_w.A-to-B` is nose-first over it
and `up_w.B-to-A` is the same move **propelled**, which is an ordinary
movement and not an error.
"""

from dataclasses import replace

from tc49.bench.runner import DEFAULT_K, NONCE, facing, placement
from tc49.dispatcher import Dispatcher, Incremental
from tc49.driver import Driver
from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import AUTOMATIC
from tc49.lib.roster import Coupled, Train
from tc49.scheduler import Scheduler
from tests.harness import load
from tests.invariants import checked
from tests.layout.railroad import (
    DEVICE_SENSOR,
    FACING,
    POWER_WANTED,
    WANTED_POINT,
    WANTED_TRACTION,
    Unstamped,
    align,
    build,
    commanded,
    energised,
    faces,
    heard,
    loco,
    move,
    railroad,
    reads,
    removed,
    settle,
    speeds,
    stand,
    stock,
    switches,
    wired,
)

MOVE_GRANTED = "tc49/dispatch/move_granted"
REQUEST_COMPLETED = "tc49/dispatch/request_completed"


def ready(train: str, facing: str) -> tuple[InProcessBus, LayoutInterface]:
    """A live railroad with `train` standing in `up_w` facing as stated, and
    the way over the crossover set."""
    bus, app = build()
    energised(bus)
    stand(bus, train, "up_w")
    faces(bus, **{train: facing})
    align(bus, "crossover", "to_dn")
    return bus, app


def test_a_nose_first_move_runs_the_locomotive_forward() -> None:
    """The train faces the end it departs through and the locomotive is
    coupled `forward`, so the speed goes out positive, at the magnitude the
    command asked for."""
    bus, app = ready("single", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == [("3", 0.6)]
    assert app.position == {"single": "dn_e"}


def test_a_propelled_move_runs_the_same_locomotive_backwards() -> None:
    """The same train over the same transit, pushed out of the end its nose
    points away from: the same magnitude, negative."""
    bus, _app = ready("single", "up_w.B-to-A")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == [("3", -0.6)]


def test_a_top_and_tail_set_runs_its_two_locomotives_opposite() -> None:
    """The whole reason orientation is a car's place in its train (ADR-0045):
    a `forward` locomotive at the head and a `reverse` one at the tail are
    told opposite signs by one move."""
    bus, _app = ready("topped", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "topped", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", 1.0), ("4", -1.0)]


def test_a_propelled_top_and_tail_set_swaps_both_signs() -> None:
    bus, _app = ready("topped", "up_w.B-to-A")
    written = commanded(bus)
    move(bus, "topped", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", -1.0), ("4", 1.0)]


def test_a_car_with_no_address_is_not_commanded() -> None:
    """Nothing reads `kind`: the address is what says a car can be told a
    speed, so the van with no decoder is passed over and the locomotive in
    front of it is not."""
    bus, _app = ready("van", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "van", "crossover", "to_dn", "dn_e", 0.5)

    assert speeds(written) == [("3", 0.5)]


def test_a_train_with_no_addressed_car_crosses_and_publishes_nothing() -> None:
    """Not a failure: the train still gets its `align`, its near-end check and
    its crossing record, and there is simply nothing to publish. It needs no
    facing either — there are no wheels here to turn the wrong way."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")

    assert speeds(written) == []
    assert app.position == {"freight_1": "dn_e"}


def test_a_train_the_roster_does_not_name_crosses_and_publishes_nothing() -> None:
    """A train off this railroad's roster is a train with no address, which is
    the same answer arrived at one step earlier."""
    bus, app = build()
    energised(bus)
    stand(bus, "stranger", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "stranger", "crossover", "to_dn", "dn_e")

    assert speeds(written) == []
    assert app.position == {"stranger": "dn_e"}


def test_the_arrival_writes_zero_to_exactly_the_addresses_commanded() -> None:
    """The train is in the block it was sent to, so every car this move
    commanded is told to stand — and no other. The arrival is the entered
    block's first detector, the same reading `block_occupied` goes out on: it
    does not wait for the vacate, the tail clearing being a fact about the
    block behind."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "topped", "crossover", "to_dn", "dn_e", 1.0)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 1.0), ("4", -1.0), ("3", 0.0), ("4", 0.0)]


def test_the_arrival_stops_each_car_once_and_the_vacate_follows_it() -> None:
    """The second detector says the tail is in and releases the block behind;
    the zeros went out on the first and are not written again."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 1.0), ("3", 0.0)]


def test_a_move_for_a_train_with_no_published_facing_waits_for_one() -> None:
    """Guessing is a locomotive driven the wrong way down the track, so the
    move is held, the train standing where it is, until a facing naming the
    block it departs arrives (ADR-0095)."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}

    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_facing_arriving_after_the_move_runs_the_train_the_way_it_says() -> None:
    """The driver's `move` and the scheduler's facing come from two writers,
    and the bus promises no order between them: the facing arriving second
    still runs the train, with the sign it gives."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    faces(bus, single="up_w.B-to-A")

    assert speeds(written) == [("3", -1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_facing_naming_another_block_is_no_facing_for_this_move() -> None:
    """A facing is a run across one block. One that names a block the train is
    not departing says nothing about this move, and is not read as
    propelled: the move waits for one naming `up_w`."""
    bus, app = ready("single", "up_e.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}

    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_facing_this_build_cannot_spell_is_no_facing() -> None:
    """The `<block>.<A-to-B|B-to-A>` form is the vocabulary, and the bare end
    letter it once was is retired (#241): a value outside it is not guessed
    at, and the move waits for one this build can read."""
    bus, app = ready("single", "up_w.B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}

    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_move_held_for_its_facing_is_dropped_for_a_train_placed_elsewhere() -> None:
    """The held move meets every rule again when the facing arrives, and the
    near-end check is one: the train no longer stands at the end it would
    depart through."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    stand(bus, "single", "up_e")
    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == []
    assert app.position == {"single": "up_e"}


def test_a_move_held_for_its_facing_is_dropped_for_a_train_lifted_and_set_back() -> (
    None
):
    """A train lifted and set back where it stood is at the near end again,
    but the dispatcher cancelled its request and freed its route on the
    removal: the move held for the facing went with the train (#1056)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    removed(bus, "single")
    stand(bus, "single", "up_w")
    written = commanded(bus)
    faces(bus, single="up_w.A-to-B")

    assert [speed for _addr, speed in speeds(written) if speed != 0.0] == []


def test_a_move_held_for_its_facing_is_dropped_for_a_train_placed_away_and_back() -> (
    None
):
    """The same with no removal between: a placement elsewhere drops the held
    move, and the placement back where it stood does not restore it (#1056)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.3)
    stand(bus, "single", "up_e")
    stand(bus, "single", "up_w")
    written = commanded(bus)
    faces(bus, single="up_w.A-to-B")

    assert [speed for _addr, speed in speeds(written) if speed != 0.0] == []


def test_a_second_move_for_the_transit_replaces_the_one_held() -> None:
    """One move held per transit: the facing runs the last one, once."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.4)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.7)
    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == [("3", 0.7)]
    assert app.position == {"single": "dn_e"}


def test_a_move_stating_no_speed_commands_nothing_and_moves_nothing() -> None:
    """The magnitude is the command's and this app has no number to fall back
    on, so a `move` that states none is dropped, and no facing arriving
    later runs it."""
    bus, app = ready("single", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", None)
    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_the_sign_is_this_apps_and_never_the_commands() -> None:
    """`speed` on a `move` is a magnitude (BUS.md): a frame that signs one
    anyway does not get to reverse a locomotive by it."""
    bus, _app = ready("single", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", -0.4)

    assert speeds(written) == [("3", 0.4)]


def test_an_unreadable_facing_leaves_the_facing_already_held_alone() -> None:
    """A state topic's value that cannot be read is no value: forgetting every
    train's facing on one bad frame would stop the railroad on a payload."""
    bus, app = ready("single", "up_w.A-to-B")
    bus.publish(FACING, {"facing": "up_w.A-to-B"})
    bus.publish(FACING, {"trains": {"single": "up_w.B-to-A"}})
    bus.drain()
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_train_missing_from_a_value_that_reads_has_no_facing() -> None:
    """The map is adopted whole, a state topic's last value being what facing
    *is*: a train the scheduler no longer names has none here, and its next
    move is held rather than run on a value that has moved on."""
    bus, app = ready("single", "up_w.A-to-B")
    faces(bus, topped="up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_the_facing_left_on_the_topic_is_there_at_startup() -> None:
    """A retained state topic, so the last value is handed over on subscribing
    and the scheduler need not be running for a train to move (ADR-0032)."""
    clock = Clock()
    bus = InProcessBus(clock)
    bus.publish(FACING, {"facing": {"single": "up_w.A-to-B"}})
    bus.drain()

    app = LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    switches(bus, AUTOMATIC)
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_an_older_facing_delivered_late_does_not_turn_a_train_round() -> None:
    """Stamp-guarded like every other state topic this app takes: two values
    of one topic delivered backwards would otherwise leave the older standing,
    which here is a locomotive run the wrong way (#240)."""
    clock = Clock()
    bus = Unstamped(clock)
    app = LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
    switches(bus, AUTOMATIC)
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    bus.publish(FACING, {"at": 2.0, "facing": {"single": "up_w.A-to-B"}})
    bus.publish(FACING, {"at": 1.0, "facing": {"single": "up_w.B-to-A"}})
    bus.drain()
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", 1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_move_held_for_its_align_is_signed_on_the_facing_it_acts_on() -> None:
    """A held command meets every rule at the moment it is acted on and not at
    the moment it arrived, and the sign is no exception: the train was turned
    round while it waited."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    assert speeds(written) == []

    faces(bus, single="up_w.B-to-A")
    align(bus, "crossover", "to_dn")

    assert speeds(written) == [("3", -1.0)]
    assert app.position == {"single": "dn_e"}


def test_a_redelivered_move_commands_no_second_start() -> None:
    """The near-end check makes the redelivery a no-op on state alone, and a
    no-op writes no speed: the train has arrived and is not started again."""
    bus, _app = ready("single", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == [("3", 1.0)]


def test_nothing_is_commanded_while_the_rails_are_dead() -> None:
    """The power rule bites before the sign is composed: a dead railroad
    turns no wheel and is told nothing."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []


def test_an_unexplained_reading_stops_nobody() -> None:
    """A level no move explains publishes its own block's occupancy and
    nothing else: there is no crossing to arrive, so no car is told to stand
    (ADR-0048)."""
    bus, app, clock = wired()
    energised(bus)
    written = commanded(bus)
    bus.publish(f"{DEVICE_SENSOR}/dn_e.A", {"addr": "dn_e.A", "occupancy": "occupied"})
    bus.drain()
    settle(bus, app, clock)

    assert speeds(written) == []


# -- the railroad comes up at rest -------------------------------------------


def test_a_speed_the_last_session_left_is_zeroed_at_startup() -> None:
    """A traction row is retained, so a bus that outlived the app hands the
    last session's speed straight back, and a translator subscribed to it
    sends that speed at the first connect: the locomotive rolls the moment
    somebody powers the rails, with no grant, the run still held, and nothing
    on the bus that says why (#333).

    So this app opens by wanting zero on every row it finds, the way it
    already opens by wanting the track off (ADR-0054)."""
    clock = Clock()
    bus = InProcessBus(clock)
    bus.publish(f"{WANTED_TRACTION}/10", {"addr": "10", "speed": 0.5})
    bus.drain()

    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert bus.last_values[f"{WANTED_TRACTION}/10"] == {
        "at": 0.0,
        "addr": "10",
        "speed": 0.0,
    }


def test_the_zero_is_written_for_a_locomotive_this_session_never_hears_of() -> None:
    """Every row on the bus and not the ones this app has commanded: the row
    was written by the previous session's dispatcher, and this one's map of
    who is where is empty. A translator standing down cannot reach these
    either — it zeroes the addresses it commanded, and a fresh one has
    commanded none."""
    clock = Clock()
    bus = InProcessBus(clock)
    bus.publish(f"{WANTED_TRACTION}/10", {"addr": "10", "speed": 0.5})
    bus.publish(f"{WANTED_TRACTION}/11", {"addr": "11", "speed": -1.0})
    bus.drain()

    written = commanded(bus)
    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert speeds(written)[-2:] == [("10", 0.0), ("11", 0.0)]


def test_a_point_the_last_session_left_thrown_replays_untouched() -> None:
    """The asymmetry, stated: traction has a resting value and a point has
    none — there is no neutral position to write into the row — so the
    retained belief about where the last session left the blades stands, and
    restoring the route picture is the only answer short of throwing every
    point at startup (#333, ADR-0054)."""
    clock = Clock()
    bus = InProcessBus(clock)
    bus.publish(f"{WANTED_POINT}/12", {"addr": "12", "position": "thrown"})
    bus.drain()

    LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()

    assert bus.last_values[f"{WANTED_POINT}/12"] == {
        "at": 0.0,
        "addr": "12",
        "position": "thrown",
    }


class FacingLast(InProcessBus):
    """A bus that hands `state/facing` on only once everything else queued
    has been delivered: the driver's `move` reaches `layout` before the
    scheduler's facing for the same arrival, an order the bus allows between
    two writers (BUS.md, "Order from one publisher")."""

    def __init__(self, clock: Clock) -> None:
        super().__init__(clock)
        self._late: list[Payload] = []

    def publish(self, topic: str, payload: Payload) -> None:
        if topic != FACING:
            super().publish(topic, payload)
            return
        self._late.append(payload)

    def drain(self) -> None:
        super().drain()
        while self._late:
            late, self._late = self._late, []
            for payload in late:
                super().publish(FACING, payload)
            super().drain()


def test_a_train_reading_clear_behind_before_occupied_ahead_runs_every_move() -> None:
    """The real apps on one bus, and an addressed `freight_1` shorter than
    the gap to each next block's entry detector: every origin reads clear
    before the next block reads occupied (ADR-0077). Each move of the route
    still runs, because the allocation recording an arrival goes out before
    the grant it leads to, so the scheduler has moved the facing `layout`
    signs the next `move` on (#1038, #1025, ADR-0052)."""
    runs_every_move(InProcessBus)


def test_a_move_reaching_layout_before_its_facing_still_runs() -> None:
    """The same, with each `move` delivered before the facing the scheduler
    published for the same arrival: `layout` holds the move until the facing
    names the block departed, and every move still starts (ADR-0095)."""
    runs_every_move(FacingLast)


def runs_every_move(binding: type[InProcessBus]) -> None:
    """The route of `crossover-yard/meet` run by the real apps on a `binding`, each
    origin reading clear before the next block reads occupied, and a nonzero
    speed written on address `3` for every move granted."""
    layout, roster, scenario = load("crossover-yard/meet")
    addressed = replace(
        roster, trains={**roster.trains, "freight_1": Train((Coupled(loco("3")),))}
    )
    clock = Clock()
    bus = binding(clock)
    stood = placement(scenario.trains)
    app = LayoutInterface(bus, layout, addressed, clock, position=stood)
    Scheduler(bus, layout, facing(layout, scenario.trains), nonce=NONCE)
    dispatcher = Dispatcher(
        bus, layout, addressed, stood, Incremental(layout, DEFAULT_K)
    )
    Driver(bus)
    checked(bus, layout, addressed)
    switches(bus, AUTOMATIC)
    bus.publish(POWER_WANTED, {"power": "on"})
    energised(bus)
    granted = heard(bus, MOVE_GRANTED)
    completed = heard(bus, REQUEST_COMPLETED)
    written = commanded(bus)

    bus.publish(
        "tc49/schedule/request_wanted", {"train": "freight_1", "dest": ["yard_e.A"]}
    )
    bus.drain()
    answered = 0
    while len(granted) > answered:
        grant = granted[answered][1]
        answered += 1
        origin = dispatcher.state.block_of["freight_1"]
        for end in (f"{origin}.A", f"{origin}.B"):
            reads(bus, end, "clear")
        settle(bus, app, clock)
        for end in (f"{grant['into']}.A", f"{grant['into']}.B"):
            reads(bus, end, "occupied")
            settle(bus, app, clock)

    assert [p["into"] for _t, p in granted] == ["dn_w", "dn_e", "yard_e"]
    assert completed
    assert dispatcher.state.block_of["freight_1"] == "yard_e"
    # One start per move: a move `layout` dropped wrote none.
    started = [s for a, s in speeds(written) if a == "3" and s != 0.0]
    assert len(started) == len(granted), speeds(written)
