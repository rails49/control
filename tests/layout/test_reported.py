"""A move waits for its reported points, and a wrong report stops the train
(ADR-0097, decisions 6 and 7, #1107).

A point whose address is reported lies where `device/point` says, so a train
departs over it only once it says the position the `align` asked for. From
then until the block the train left reads vacated, a report of the other
position stops the train, as an arrival does. A point not reported is taken
for where `wanted/point` put it, as before.

The bench railroad's `to_dn` throws `12` and `13`; here `12` is reported.
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus
from tc49.lib.clock import Clock
from tests.layout.railroad import (
    align,
    commanded,
    energised,
    faces,
    lies,
    move,
    reads,
    settle,
    speeds,
    stand,
    takes,
    turns,
    wired,
)


def ready() -> tuple[InProcessBus, LayoutInterface, Clock]:
    """A live railroad with `single` standing in `up_w` facing nose-first
    over `to_dn`, and the way over the crossover asked for with `12`
    reported."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    align(bus, "crossover", "to_dn", reported=("12",))
    return bus, app, clock


def test_a_move_over_a_reported_point_waits_for_its_report() -> None:
    bus, app, _clock = ready()
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}

    lies(bus, "12", "thrown")

    assert speeds(written) == [("3", 0.6)]
    assert app.position == {"single": "dn_e"}


def test_a_report_of_the_other_position_keeps_it_waiting() -> None:
    bus, app, _clock = ready()
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    lies(bus, "12", "closed")

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_point_already_reporting_the_position_lets_the_move_through() -> None:
    """The report came before the `align`: the point already lay where the
    way wants it, so nothing is waited for."""
    bus, _app, _clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    lies(bus, "12", "thrown")
    align(bus, "crossover", "to_dn", reported=("12",))
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == [("3", 0.6)]


def test_a_report_of_a_point_not_reported_is_not_waited_for() -> None:
    """`13` is on the way and not reported: `wanted/point` stands for where
    it lies, and what `device/point` says of it holds nothing."""
    bus, _app, _clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    lies(bus, "13", "closed")
    align(bus, "crossover", "to_dn")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written) == [("3", 0.6)]


def test_a_throw_by_hand_waits_for_nothing_and_authorises_nothing() -> None:
    """An `align` naming no transit writes its point and is done: no move is
    let through by it, and the report that follows lets through none."""
    bus, app, _clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    bus.publish(
        "tc49/layout/align",
        {
            "connection": None,
            "transit": None,
            "points": [{"addr": "12", "position": "thrown", "reported": True}],
        },
    )
    bus.drain()
    lies(bus, "12", "thrown")

    assert speeds(written) == []
    assert app.position == {"single": "up_w"}


def test_a_wrong_report_after_departure_stops_the_train() -> None:
    bus, _app, _clock = ready()
    lies(bus, "12", "thrown")
    written = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    lies(bus, "12", "closed")

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_a_wrong_report_after_the_arrival_still_stops_the_train() -> None:
    """At the arrival the train's tail may still be over the points: until
    the block it left reads vacated, a wrong report is written `0.0` again,
    over whatever a throttle has given it since."""
    bus, app, clock = ready()
    lies(bus, "12", "thrown")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    takes(bus, "single")
    faces(bus, single="dn_e.A-to-B")
    written = commanded(bus)
    turns(bus, "single", 0.3)
    lies(bus, "12", "closed")

    assert speeds(written)[-2:] == [("3", 0.3), ("3", 0.0)]


def test_a_repeated_wrong_report_does_not_stop_the_train_again() -> None:
    """A throttle may drive the train on (ADR-0081): nothing holds it
    against one, so the same report heard again writes nothing."""
    bus, app, clock = ready()
    lies(bus, "12", "thrown")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    takes(bus, "single")
    faces(bus, single="dn_e.A-to-B")
    lies(bus, "12", "closed")
    written = commanded(bus)
    turns(bus, "single", 0.3)
    lies(bus, "12", "closed")

    assert speeds(written)[-1] == ("3", 0.3)


def test_a_train_stopped_by_a_wrong_report_is_not_given_its_grant_again() -> None:
    """Stopped as at an arrival, the grant implies nothing more: the `on`
    after a cut does not drive the train on over the point."""
    bus, _app, _clock = ready()
    lies(bus, "12", "thrown")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    lies(bus, "12", "closed")
    bus.publish("tc49/layout/power_wanted", {"power": "off"})
    bus.drain()
    written = commanded(bus)
    bus.publish("tc49/layout/power_wanted", {"power": "on"})
    bus.drain()

    assert [speed for _addr, speed in speeds(written) if speed != 0.0] == []


def test_a_wrong_report_after_the_block_left_reads_clear_writes_nothing() -> None:
    bus, app, clock = ready()
    written = commanded(bus)
    lies(bus, "12", "thrown")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    reads(bus, "up_w.B", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    since = len(written)
    lies(bus, "12", "closed")

    assert speeds(written)[since:] == []


def test_the_next_move_over_the_transit_waits_for_its_own_reports() -> None:
    """Each `align` is one crossing (#305), and its reported points are its
    own: a point thrown back since is waited for again."""
    bus, app, clock = ready()
    written = commanded(bus)
    lies(bus, "12", "thrown")
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    reads(bus, "dn_e.B", "occupied")
    settle(bus, app, clock)
    stand(bus, "single", "up_w")
    lies(bus, "12", "closed")
    align(bus, "crossover", "to_dn", reported=("12",))
    since = len(written)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert speeds(written)[since:] == []
    assert app.position == {"single": "up_w"}
