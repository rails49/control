"""A person's throttle, and the road it takes to a locomotive (#297).

`tc49/layout/throttle_wanted` carries a train, a speed in −1.0 … 1.0 and the
id of the throttle turning the lever, and it reaches a decoder by the same
road a `move` does: one signed speed per addressed car, composed out of the
way the train points and the way round each of its cars is coupled (#296). So
a person pushes the lever forward and the train moves nose-first, whichever
way round the locomotives are wired and however many of them there are.

The lever is signed for the **train**, positive nose-first, which is the whole
difference from a `move`: a move states a magnitude and the block it is going
into, and this states the direction outright. So facing is not in the number
here, only in the refusal beside it — this app will not drive a train the rest
of the system is not holding the geometry of, and which block that facing
names is not asked, a facing lagging the train it is about.

A throttle drives only the train it holds, and drives it at any time, granted
move or not (ADR-0079, ADR-0081): the move ending at its sensor writes `0.0`,
and the next lever frame drives the train on. A lever reversing a running train
stops it instead, until the throttle has sent `0` or this app has stopped the
train (ADR-0084, ADR-0088).
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import MANUAL
from tests.layout.railroad import (
    POWER_WANTED,
    THROTTLE_WANTED,
    align,
    build,
    commanded,
    drains,
    energised,
    faces,
    gives,
    move,
    reads,
    removed,
    settle,
    speeds,
    stand,
    takes,
    turns,
    wired,
)


def granted(bus: InProcessBus, train: str) -> None:
    """The dispatcher's grant: `train` from `up_w` across the crossover into
    `dn_e`, which is what a throttle's lever drives within."""
    align(bus, "crossover", "to_dn")
    move(bus, train, "crossover", "to_dn", "dn_e", 0.6)


def underway(
    train: str, facing: str, driving: str | None = None
) -> tuple[InProcessBus, LayoutInterface, Clock, list[tuple[str, Payload]]]:
    """A live railroad with `train` standing in `up_w` facing as stated, a
    throttle holding it and a move granted, and every traction write from
    there on."""
    bus, app, clock = wired() if driving is None else wired(driving=driving)
    energised(bus)
    stand(bus, train, "up_w")
    faces(bus, **{train: facing})
    takes(bus, train)
    granted(bus, train)
    return bus, app, clock, commanded(bus)


def held(train: str, facing: str) -> tuple[InProcessBus, list[tuple[str, Payload]]]:
    """The same, for a test with no business with the arrival."""
    bus, _app, _clock, written = underway(train, facing)
    return bus, written


def test_a_lever_pushed_forward_runs_the_locomotive_forward() -> None:
    """Nose-first is what positive means, and the locomotive is coupled
    `forward`, so the number goes out as it came in."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.6)

    assert speeds(written) == [("3", 0.6)]


def test_a_lever_pulled_back_runs_it_backwards() -> None:
    """The same train the other way: a person backs it up, and the sign of the
    lever is the sign of the movement."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", -0.6)

    assert speeds(written) == [("3", -0.6)]


def test_one_lever_drives_a_top_and_tail_set_opposite() -> None:
    """The whole reason orientation is a car's place in its train (ADR-0045):
    one number, two locomotives, opposite signs — and the person pushing it
    knows nothing of either address."""
    bus, written = held("topped", "up_w.A-to-B")
    turns(bus, "topped", 0.5)

    assert speeds(written) == [("8", 0.5), ("4", -0.5)]


def test_the_lever_says_which_way_and_the_facing_does_not() -> None:
    """Positive is nose-first whichever end of its block the train's nose
    points at: a person drives the train they can see, and where the block's
    ends are is not something they hold a lever about."""
    bus, written = held("topped", "up_w.B-to-A")
    turns(bus, "topped", 0.5)

    assert speeds(written) == [("8", 0.5), ("4", -0.5)]


def test_centring_the_lever_stops_every_car() -> None:
    """The control a person reaches for when something is wrong, and it reaches
    the same addresses the driving did."""
    bus, written = held("topped", "up_w.A-to-B")
    turns(bus, "topped", 0.5)
    turns(bus, "topped", 0.0)

    assert speeds(written)[2:] == [("8", 0.0), ("4", 0.0)]


def test_a_car_with_no_address_is_not_commanded() -> None:
    """Nothing reads `kind`: the address is what says a car can be told a
    speed, so the van with no decoder is passed over."""
    bus, written = held("van", "up_w.A-to-B")
    turns(bus, "van", 0.5)

    assert speeds(written) == [("9", 0.5)]


def test_a_throttle_drives_in_manual_as_in_automatic() -> None:
    """The driving mode decides who drives a train no throttle holds; a train
    a throttle holds is that throttle's either way (ADR-0079)."""
    bus, _app, _clock, written = underway("single", "up_w.A-to-B", MANUAL)
    turns(bus, "single", 0.6)

    assert speeds(written) == [("3", 0.6)]


def stood(
    driving: str | None = None,
) -> tuple[InProcessBus, list[tuple[str, Payload]]]:
    """A live railroad with `single` standing in `up_w`, a throttle holding it
    and no move granted, and every traction write from there on."""
    bus, _app, _clock = wired() if driving is None else wired(driving=driving)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    return bus, commanded(bus)


def test_a_lever_with_no_move_outstanding_writes_its_speed_in_automatic() -> None:
    """A throttle drives the train it holds at any time, granted move or not:
    a person at a platform backs a train up a few centimetres (ADR-0081,
    decision 1)."""
    bus, written = stood()
    turns(bus, "single", -0.3)

    assert speeds(written) == [("3", -0.3)]


def test_a_lever_with_no_move_outstanding_writes_its_speed_in_manual() -> None:
    bus, written = stood(MANUAL)
    turns(bus, "single", 0.3)

    assert speeds(written) == [("3", 0.3)]


def test_the_moves_end_zeroes_the_lever_and_the_lever_drives_on() -> None:
    """The move ending at its sensor writes `0.0` for the throttle's train as
    for one this app drives, and the next lever frame is applied again with no
    new grant (ADR-0081, decision 3)."""
    bus, app, clock, written = underway("single", "up_w.A-to-B")
    turns(bus, "single", 0.4)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4), ("3", 0.0), ("3", 0.4)]


def test_a_lever_while_draining_writes_its_speed() -> None:
    """A drain keeps the supply on, so the rails are live and a person's hand
    is heard: pulling back to stop is what a drain wants."""
    bus, written = held("single", "up_w.A-to-B")
    drains(bus)
    turns(bus, "single", 0.2)

    assert speeds(written) == [("3", 0.2)]


def test_a_lever_for_a_train_taken_off_the_layout_writes_nothing() -> None:
    """A train this app holds no position for stands nowhere, and a lever for
    it would drive a decoder in a hand."""
    bus, written = stood()
    removed(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.0)]


def test_a_lever_after_a_restart_drives_a_train_the_allocation_names() -> None:
    """`train_placed` is an event, so a restarted app takes where the train
    stands from the dispatcher's retained allocation, and the lever is not
    dead until the train is dispatched or dragged (#579, #960)."""
    bus, _app, _clock = wired(driving=MANUAL, allocated={"single": "up_w"})
    energised(bus)
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]


def test_a_flip_at_speed_writes_zero_until_the_lever_is_at_zero() -> None:
    """A reverser moves only with the lever at 0 (ADR-0084): a frame of the
    other sign stops the train instead, and so does every later one of that
    sign until the throttle sends `0`. From there the other way is free."""
    bus, written = held("single", "up_w.A-to-B")
    for speed in (0.4, -0.4, -0.4, 0.0, -0.4):
        turns(bus, "single", speed)

    assert speeds(written) == [
        ("3", 0.4),
        ("3", 0.0),
        ("3", 0.0),
        ("3", 0.0),
        ("3", -0.4),
    ]


def test_an_arrival_lets_the_lever_drive_the_other_way() -> None:
    """The arrival's `0.0` stops the train as the throttle's own `0` would,
    and the page shows the slider at 0 without sending it, so the other way
    is free from there (#962)."""
    bus, app, clock, written = underway("single", "up_w.A-to-B")
    turns(bus, "single", 0.4)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    turns(bus, "single", -0.4)

    assert speeds(written) == [("3", 0.4), ("3", 0.0), ("3", -0.4)]


def test_a_cut_lets_the_lever_drive_the_other_way() -> None:
    """A cut writes `0.0` over every row and stops every train (#962)."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.4)
    bus.publish(POWER_WANTED, {"power": "off"})
    bus.drain()
    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()
    energised(bus)
    turns(bus, "single", -0.4)

    assert speeds(written)[-1] == ("3", -0.4)


def test_a_release_in_manual_lets_the_next_take_drive_the_other_way() -> None:
    """A release in `manual` writes `0.0`, and the next take opens at
    Forward with the slider at 0: its first frame drives (#962)."""
    bus, _app, _clock, written = underway("single", "up_w.A-to-B", MANUAL)
    turns(bus, "single", -0.4)
    gives(bus, "single")
    takes(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", -0.4), ("3", 0.0), ("3", 0.4)]


def test_a_flip_against_the_grants_speed_writes_zero() -> None:
    """The last speed written for the train is the grant's as much as the
    lever's: a train taken running nose-first and pulled back stops first."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    takes(bus, "single")
    turns(bus, "single", -0.4)

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_a_flip_on_a_top_and_tail_set_stops_both_locomotives() -> None:
    """The sign compared is the train's, before it is composed onto the cars,
    so the two locomotives running opposite are one direction here."""
    bus, written = held("topped", "up_w.A-to-B")
    turns(bus, "topped", 0.5)
    turns(bus, "topped", -0.5)

    assert speeds(written) == [("8", 0.5), ("4", -0.5), ("8", 0.0), ("4", 0.0)]


def test_the_next_grant_brings_the_lever_back() -> None:
    """A train that has arrived and been granted the next move is the
    throttle's to drive again."""
    bus, app, clock, written = underway("single", "up_w.A-to-B")
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    stand(bus, "single", "up_w")
    granted(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.0), ("3", 0.4)]


def test_a_lever_naming_no_throttle_writes_nothing() -> None:
    """The id is what says whose the lever is, so a frame without one is
    nobody's and is dropped (ADR-0079)."""
    bus, written = held("single", "up_w.A-to-B")
    bus.publish(THROTTLE_WANTED, {"train": "single", "speed": 0.6})
    bus.drain()

    assert speeds(written) == []


def test_a_lever_on_a_throttle_that_does_not_hold_the_train_writes_nothing() -> None:
    """At most one throttle holds a train, and only that one drives it."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.6, throttle="t-2")

    assert speeds(written) == []


def test_a_throttle_for_a_train_no_throttle_holds_writes_nothing() -> None:
    """The grant is what moves a train in `automatic`, and a lever nobody is
    holding does not get to overtake it."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    turns(bus, "single", 0.9)

    assert speeds(written) == [("3", 0.6)]


def test_a_throttle_for_a_train_given_back_writes_nothing() -> None:
    """The gesture is refused from the moment the throttle lets go: released
    running in `automatic`, the train keeps the speed the person left, and
    that is all that is on the row (ADR-0081, decision 6)."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.4)
    gives(bus, "single")
    turns(bus, "single", 0.9)

    assert speeds(written) == [("3", 0.4)]


def test_nothing_is_written_while_the_rails_are_dead() -> None:
    """Dead rails refuse a person's hand as they refuse a grant (ADR-0041).
    Nothing is written rather than a zero: the row holds whatever it last
    held, and a gesture that could not be acted on has said nothing."""
    bus, written = held("single", "up_w.A-to-B")
    bus.publish("tc49/layout/state/device/track", {"power": "off"})
    bus.drain()
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_throttle_for_a_train_with_no_facing_writes_nothing() -> None:
    """No facing, no move, and no lever either: this app will not drive a
    train whose geometry it cannot say."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    takes(bus, "single")
    granted(bus, "single")
    written = commanded(bus)
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_facing_this_build_cannot_spell_is_no_facing() -> None:
    """The `<block>.<A-to-B|B-to-A>` form is the vocabulary, and the bare end
    letter it once was is retired (#241)."""
    bus, written = held("single", "up_w.B")
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_facing_that_has_not_caught_up_with_the_train_still_drives_it() -> None:
    """Which block the facing names is not asked of a lever. A facing lags the
    train it is about — another app publishes it, on another topic — and a
    lever that went dead for as long as the lag lasted would be a person
    pulling back to stop and not being heard."""
    bus, written = held("single", "up_e.A-to-B")
    turns(bus, "single", 0.6)

    assert speeds(written) == [("3", 0.6)]


def test_an_unreadable_gesture_writes_nothing() -> None:
    """A frame that cannot be read is dropped, silently and to the trace: this
    app answers nothing, so a refusal would have nowhere to go (ADR-0034)."""
    bus, written = held("single", "up_w.A-to-B")
    for payload in (
        {},
        {"train": "single", "throttle": "t-1"},
        {"speed": 0.5, "throttle": "t-1"},
        {"train": 1, "speed": 0.5, "throttle": "t-1"},
        {"train": "single", "speed": 0.5, "throttle": ""},
    ):
        bus.publish(THROTTLE_WANTED, payload)
        bus.drain()

    assert speeds(written) == []


def test_a_person_drives_their_train_across_a_transit_the_grant_set() -> None:
    """The whole point of the two halves meeting: the dispatcher granted the
    move, the points threw and the transit is armed, and the train crosses on
    a person's lever with nothing this app wrote of its own."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]
