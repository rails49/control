"""A train taken off the layout: its decoders told to stand, its move forgotten
(#671, ADR-0069 decision 6).

A person lifts a train whenever they need to, the run going or not, so what
comes off may be running. The decoders go on hearing the track whether or not
the train is on it, and a locomotive lifted in a hand with its last speed still
standing on its row runs the moment it is set down anywhere. So every
addressed car is told `0.0`, and a move of that train's in flight writes
nothing more for it: the readings it was waiting on now belong to whatever the
detectors see, which is no longer this train.
"""

from tc49.lib.bus import InProcessBus, Payload
from tests.layout.railroad import (
    DEVICE_TRACK,
    REMOVED,
    align,
    build,
    commanded,
    energised,
    faces,
    move,
    reads,
    settle,
    speeds,
    stand,
    takes,
    turns,
    wired,
)


def told(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every traction write from here on, and not the rows already standing:
    what a retained row replays on subscribing is the last write, not this
    one."""
    written = commanded(bus)
    bus.drain()
    written.clear()
    return written


def removed(bus: InProcessBus, train: str) -> None:
    """A hand lifted the train off and the dispatcher accepted it."""
    bus.publish(REMOVED, {"train": train})
    bus.drain()


def test_a_standing_train_with_a_speed_written_is_told_to_stand() -> None:
    """A person's lever left a speed on each row; taking the train off writes
    `0.0` over every one of them, in the train's own order."""
    bus, _app = build()
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    takes(bus, "topped")
    turns(bus, "topped", 0.4)
    written = told(bus)

    removed(bus, "topped")

    assert speeds(written) == [("3", 0.0), ("4", 0.0)]


def test_the_zero_goes_out_whatever_the_power() -> None:
    """Dead rails refuse a speed, not a stop: a row left standing over dead
    track is a train that starts when the power comes back."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    written = told(bus)

    removed(bus, "single")

    assert speeds(written) == [("3", 0.0)]


def test_a_train_with_a_move_in_flight_is_stopped_and_its_move_forgotten() -> None:
    """The zero goes out on the removal, and the readings the move was waiting
    on — the arrival and the tail — write no speed for it afterwards."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    written = told(bus)

    removed(bus, "single")
    assert speeds(written) == [("3", 0.0)]

    written.clear()
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == []
    assert app.position == {}


def test_a_manual_train_is_stopped_the_same_way() -> None:
    """A train in a throttle is a person's to drive, but a train off the
    layout is nobody's: the panel drops the throttle, and this writes the
    zero the lever would otherwise have left standing."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    turns(bus, "single", -0.3)
    written = told(bus)

    removed(bus, "single")

    assert speeds(written) == [("3", 0.0)]


def test_a_train_with_no_addressed_car_writes_nothing() -> None:
    """Nothing to tell, so nothing told, and nothing raises — with a move in
    flight as without one."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    written = told(bus)

    removed(bus, "freight_1")

    assert speeds(written) == []
    assert app.position == {}


def test_another_trains_move_is_left_alone() -> None:
    """Only the removed train's crossing is forgotten: another train's arrival
    still stops it."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn")
    move(bus, "single", "crossover", "to_dn", "dn_e", 1.0)
    written = told(bus)

    removed(bus, "freight_1")
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.0)]
