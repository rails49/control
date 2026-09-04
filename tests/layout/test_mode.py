"""Who drives each train, and what changing that is worth on the rails (#297).

A train is **automatic** or **manual**: taking it in a throttle makes it
manual and giving it back puts it back (#207). The word names who turns the
throttle and nothing else — a manual train is dispatched like any other, holds
its block and is granted moves like any other — so what the mode changes here
is exactly one thing: whether this app writes the wheels.

The two edges are not symmetric, and that is the design. **Taking** a train
writes nothing: it keeps whatever speed it had, and a person's first movement
of the lever is what changes it, since stopping a running train the instant
somebody selected it is not what selecting it means. **Giving** it back writes
the speed its current grant implies, which is `0.0` where there is none: a
train handed back does not keep the speed a person left on it.
"""

from tc49.lib.bus import Bus, Payload
from tests.layout.railroad import (
    DEVICE_TRACK,
    MODE,
    MODE_WANTED,
    align,
    build,
    commanded,
    energised,
    faces,
    gives,
    heard,
    move,
    reads,
    settle,
    speeds,
    stand,
    takes,
    wired,
)


def driving(bus: Bus) -> list[tuple[str, Payload]]:
    """Every value `state/mode` carries from here on, in order. The retained
    value the subscription is owed comes first, so the map standing when this
    was asked leads the list."""
    return heard(bus, MODE)


def modes(said: list[tuple[str, Payload]]) -> list[dict[str, str]]:
    """Those values as the maps they carry, which is what this suite asserts:
    the stamp is the row's shape rather than the news."""
    return [
        {str(train): str(mode) for train, mode in dict(payload["modes"]).items()}
        for _topic, payload in said
    ]


def test_taking_one_train_publishes_a_map_containing_it() -> None:
    """The whole map, which is what a state topic carries, and only the manual
    trains are in it: `automatic` is the resting value, so a train the map does
    not name is automatic."""
    bus, _app = build()
    said = driving(bus)
    stand(bus, "single", "up_w")
    takes(bus, "single")

    assert modes(said) == [{}, {"single": "manual"}]


def test_giving_it_back_publishes_a_map_without_it() -> None:
    """Dropping the train is how the map says automatic, and it is a change,
    so it goes out."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    takes(bus, "single")
    said = driving(bus)
    gives(bus, "single")

    assert modes(said) == [{"single": "manual"}, {}]


def test_a_null_train_hands_over_every_train_the_app_holds() -> None:
    """One gesture that hands the whole railroad to people. Every train with a
    position is named: a train standing nowhere is one nobody is driving."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    stand(bus, "topped", "up_e")
    said = driving(bus)
    takes(bus, None)

    assert modes(said) == [{}, {"single": "manual", "topped": "manual"}]


def test_a_null_train_takes_the_whole_railroad_back() -> None:
    bus, _app = build()
    stand(bus, "single", "up_w")
    stand(bus, "topped", "up_e")
    takes(bus, None)
    said = driving(bus)
    gives(bus, None)

    assert modes(said) == [{"single": "manual", "topped": "manual"}, {}]


def test_a_second_take_on_a_train_already_taken_says_nothing() -> None:
    """The gesture states where the mode should stand rather than asking for a
    change, so a second one is not a race — and a state topic republishing the
    value it already holds is news to nobody."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    takes(bus, "single")
    said = driving(bus)
    takes(bus, "single")

    assert modes(said) == [{"single": "manual"}]


def test_giving_back_a_train_nobody_took_says_nothing() -> None:
    bus, _app = build()
    stand(bus, "single", "up_w")
    said = driving(bus)
    gives(bus, "single")

    assert modes(said) == [{}]


def test_a_gesture_that_cannot_be_read_leaves_the_map_where_it_was() -> None:
    """Falling to `manual` would hand a train to a person who is not there and
    falling to `automatic` would take one out of the hands of a person who is,
    so an unreadable frame is dropped and the mode stays put."""
    bus, _app = build()
    stand(bus, "single", "up_w")
    takes(bus, "single")
    said = driving(bus)
    for payload in ({}, {"train": "single"}, {"train": "single", "mode": "Manual"}):
        bus.publish(MODE_WANTED, payload)
        bus.drain()

    assert modes(said) == [{"single": "manual"}]


def test_taking_a_running_train_writes_nothing() -> None:
    """It keeps the speed it had: the move's own write is the whole of what
    the row has been told, and the take-over adds nothing to it. Writing zero
    here would stop a running train the instant somebody selected it, which is
    not what selecting it means."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    takes(bus, "single")

    assert speeds(written) == [("3", 0.6)]


def test_giving_back_a_train_with_no_grant_in_flight_writes_zero() -> None:
    """A train handed back does not keep the speed a person left on it, and
    there is no grant here to imply another one."""
    bus, _app = build()
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    takes(bus, "topped")
    written = commanded(bus)
    gives(bus, "topped")

    assert speeds(written) == [("3", 0.0), ("4", 0.0)]


def test_giving_back_a_train_mid_transit_writes_what_its_grant_implies() -> None:
    """The move was carried out while the train was a person's, so nothing was
    written for it — and the speed it implied was kept, which is what the train
    is given the moment it comes back."""
    bus, _app = build()
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    takes(bus, "topped")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "topped", "crossover", "to_dn", "dn_e", 0.6)
    assert speeds(written) == []

    gives(bus, "topped")

    assert speeds(written) == [("3", 0.6), ("4", -0.6)]


def test_a_train_given_back_mid_transit_is_stopped_on_arrival() -> None:
    """The wheels are this app's again, so the arrival is its to write."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    gives(bus, "single")

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_a_train_taken_mid_transit_is_not_stopped_on_arrival() -> None:
    """This app started it and a person is driving it now, so the `0.0` it was
    going to write when the train got there does not go out: a person stops
    their own train, and the signal at the far end is what tells them to."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    takes(bus, "single")

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.6)]


def test_giving_back_a_train_that_has_arrived_writes_zero() -> None:
    """The grant implies nothing once the train is where it was sent, so what
    it implied goes with the arrival."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    written = commanded(bus)
    gives(bus, "single")

    assert speeds(written) == [("3", 0.0)]


def test_giving_back_a_train_over_dead_rails_writes_zero() -> None:
    """A grant cannot be acted on over dead track at all, so it implies
    nothing: a desired speed left standing on a row is a train that would start
    the moment the power came back (ADR-0041)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    written = commanded(bus)
    gives(bus, "single")

    assert speeds(written) == [("3", 0.0)]


def test_giving_back_a_train_with_no_addressed_car_writes_nothing() -> None:
    """There are no wheels here to turn, which is `_addressed` and not a rule
    of the mode's."""
    bus, _app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    takes(bus, "freight_1")
    written = commanded(bus)
    gives(bus, "freight_1")

    assert speeds(written) == []


def test_handing_the_railroad_back_stops_every_train_a_person_had() -> None:
    """The wide gesture is the narrow one made of every train at once, down to
    what each is given."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    stand(bus, "topped", "up_e")
    takes(bus, None)
    written = commanded(bus)
    gives(bus, None)

    assert speeds(written) == [("3", 0.0), ("3", 0.0), ("4", 0.0)]


def test_a_manual_trains_move_throws_its_points_and_writes_no_speed() -> None:
    """The route is not the driving: the points still throw, the near-end check
    still passes and the crossing is still recorded, and the one thing that
    does not happen is the traction write."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    thrown = heard(bus, "tc49/layout/state/wanted/point/#")
    written = commanded(bus)
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert [payload["addr"] for _topic, payload in thrown] == ["12", "13"]
    assert speeds(written) == []
    assert app.position == {"single": "dn_e"}


def test_a_manual_trains_move_needs_no_facing() -> None:
    """The refusal exists because a sign cannot be guessed, and there is no
    sign to compose here: nothing is being written, so there is no wrong way to
    drive the train and no move to drop."""
    bus, app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    takes(bus, "single")
    written = commanded(bus)
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == []
    assert app.position == {"single": "dn_e"}


def test_a_manual_train_arriving_is_told_nothing() -> None:
    """It was never told to run, so it is not told to stand: a car nothing was
    sent for is a car nothing may be sent for."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == []
