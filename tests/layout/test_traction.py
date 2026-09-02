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

from tc49.layout import LayoutInterface
from tc49.lib.bus import Bus, Payload
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    DEVICE_SENSOR,
    FACING,
    WANTED_TRACTION,
    Unstamped,
    align,
    build,
    energised,
    faces,
    heard,
    move,
    railroad,
    reads,
    settle,
    stand,
    stock,
    wired,
)


def commanded(bus: Bus) -> list[tuple[str, Payload]]:
    """Every traction write from here on, in order."""
    return heard(bus, WANTED_TRACTION + "/#")


def speeds(written: list[tuple[str, Payload]]) -> list[tuple[str, float]]:
    """Those writes as address and speed, which is what these suites assert:
    the stamp and the repeated address are the row's shape rather than this
    write's news, and the address on the topic is the one in the payload."""
    return [
        (str(payload["addr"]), float(payload["speed"])) for _topic, payload in written
    ]


def ready(train: str, facing: str) -> tuple[Bus, LayoutInterface]:
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


def test_a_move_for_a_train_with_no_published_facing_is_dropped() -> None:
    """Guessing is a locomotive driven the wrong way down the track, and a
    drop is what a failed read is worth for an app that answers nothing
    (SYSTEM.md, rule 4)."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_facing_arriving_after_the_move_does_not_run_the_train() -> None:
    """The dropped command stays dropped: nothing here holds a `move` for want
    of a facing, and a redelivery is what a driver would send."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    faces(bus, single="up_w.A-to-B")

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_facing_naming_another_block_is_no_facing_for_this_move() -> None:
    """A facing is a run across one block. One that names a block the train is
    not departing says nothing about this move, and is refused rather than
    read as propelled."""
    bus, app = ready("single", "up_e.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_facing_this_build_cannot_spell_is_no_facing() -> None:
    """The `<block>.<A-to-B|B-to-A>` form is the vocabulary, and the bare end
    letter it once was is retired (#241): a value outside it is dropped rather
    than guessed at."""
    bus, app = ready("single", "up_w.B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_move_stating_no_speed_commands_nothing_and_moves_nothing() -> None:
    """The magnitude is the command's and this app has no number to fall back
    on, so a `move` that states none is dropped the way one with no facing
    is."""
    bus, app = ready("single", "up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", None)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_the_sign_is_this_apps_and_never_the_commands() -> None:
    """`speed` on a `move` is a magnitude (SYSTEM.md): a frame that signs one
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
    move is dropped rather than run on a value that has moved on."""
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
    bus = Bus(clock)
    bus.publish(FACING, {"facing": {"single": "up_w.A-to-B"}})
    bus.drain()

    app = LayoutInterface(bus, railroad(), stock(), clock)
    bus.drain()
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
