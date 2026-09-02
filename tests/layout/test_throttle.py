"""A person's throttle, and the road it takes to a locomotive (#297).

`tc49/layout/throttle_wanted` carries a train and a speed in −1.0 … 1.0, and it
reaches a decoder by the same road a `move` does: one signed speed per
addressed car, composed out of the way the train points and the way round each
of its cars is coupled (#296). So a person pushes the lever forward and the
train moves nose-first, whichever way round the locomotives are wired and
however many of them there are.

The lever is signed for the **train**, positive nose-first, which is the whole
difference from a `move`: a move states a magnitude and the block it is going
into, and this states the direction outright. So facing is not in the number
here, only in the refusal beside it — this app will not drive a train the rest
of the system is not holding the geometry of, and which block that facing
names is not asked, a facing lagging the train it is about.
"""

from tc49.lib.bus import Bus, Payload
from tests.layout.railroad import (
    THROTTLE_WANTED,
    align,
    build,
    commanded,
    energised,
    faces,
    gives,
    move,
    speeds,
    stand,
    takes,
    turns,
)


def held(train: str, facing: str) -> tuple[Bus, list[tuple[str, Payload]]]:
    """A live railroad with `train` standing in `up_w` facing as stated and a
    person holding its throttle, and every traction write from there on."""
    bus, _app = build()
    energised(bus)
    stand(bus, train, "up_w")
    faces(bus, **{train: facing})
    takes(bus, train)
    return bus, commanded(bus)


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

    assert speeds(written) == [("3", 0.5), ("4", -0.5)]


def test_the_lever_says_which_way_and_the_facing_does_not() -> None:
    """Positive is nose-first whichever end of its block the train's nose
    points at: a person drives the train they can see, and where the block's
    ends are is not something they hold a lever about."""
    bus, written = held("topped", "up_w.B-to-A")
    turns(bus, "topped", 0.5)

    assert speeds(written) == [("3", 0.5), ("4", -0.5)]


def test_centring_the_lever_stops_every_car() -> None:
    """The control a person reaches for when something is wrong, and it reaches
    the same addresses the driving did."""
    bus, written = held("topped", "up_w.A-to-B")
    turns(bus, "topped", 0.5)
    turns(bus, "topped", 0.0)

    assert speeds(written)[2:] == [("3", 0.0), ("4", 0.0)]


def test_a_car_with_no_address_is_not_commanded() -> None:
    """Nothing reads `kind`: the address is what says a car can be told a
    speed, so the van with no decoder is passed over."""
    bus, written = held("van", "up_w.A-to-B")
    turns(bus, "van", 0.5)

    assert speeds(written) == [("3", 0.5)]


def test_a_throttle_for_an_automatic_train_writes_nothing() -> None:
    """The grant is what moves an automatic train, and a lever nobody is
    holding does not get to overtake it."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_throttle_for_a_train_given_back_writes_nothing() -> None:
    """The gesture is refused from the moment the train stops being a
    person's, and the `0.0` the hand-back wrote is all that is on the row."""
    bus, written = held("single", "up_w.A-to-B")
    turns(bus, "single", 0.6)
    gives(bus, "single")
    turns(bus, "single", 0.9)

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_nothing_is_written_while_the_rails_are_dead() -> None:
    """Dead rails refuse a person's hand as they refuse a grant (ADR-0041).
    Nothing is written rather than a zero: the row holds whatever it last
    held, and a gesture that could not be acted on has said nothing."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_throttle_for_a_train_the_app_does_not_hold_writes_nothing() -> None:
    """A train standing nowhere this app knows of is one it will not drive:
    the `move`'s refusal, arriving here for the `move`'s reason."""
    bus, _app = build()
    energised(bus)
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    turns(bus, "single", 0.6)

    assert speeds(written) == []


def test_a_throttle_for_a_train_with_no_facing_writes_nothing() -> None:
    """No facing, no move, and no lever either: this app will not drive a
    train whose geometry it cannot say."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    takes(bus, "single")
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
    for payload in ({}, {"train": "single"}, {"speed": 0.5}, {"train": 1}):
        bus.publish(THROTTLE_WANTED, payload)
        bus.drain()

    assert speeds(written) == []


def test_a_person_drives_their_train_across_a_transit_the_grant_set() -> None:
    """The whole point of the two halves meeting: the dispatcher granted the
    move, the points threw and the transit is armed, and the train crosses on
    a person's lever with nothing this app wrote of its own."""
    bus, written = held("single", "up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]
