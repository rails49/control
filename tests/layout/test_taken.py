"""Which throttle holds each train, and what taking and releasing one is worth
on the rails (ADR-0079).

At most one throttle holds a train: `take_wanted` names the throttle by the id
its page minted, a second take is dropped, and `throttle: null` releases the
train whoever holds it. `state/taken` says who holds which.

The two edges are not symmetric, and that is the design. **Taking** a train
writes nothing: it keeps whatever speed it had, and a person's first movement
of the lever changes it. **Releasing** it writes what the driving mode makes
of it: in `manual`, `0.0`; in `automatic` with a move outstanding, nothing,
the train keeping the speed the person left until its move ends (ADR-0081),
unless it stands, when it is given its grant's speed (ADR-0083); in
`automatic` with no move outstanding, `0.0`. A throttle not heard for 5 s is
released the same way.
"""

from tc49.layout import LayoutInterface
from tc49.layout.interface import THROTTLE_SILENCE_S
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.inventory import MANUAL
from tc49.lib.roster import Coupled, Roster, Train
from tests.layout.railroad import (
    DEVICE_TRACK,
    POWER_WANTED,
    TAKE_WANTED,
    TAKEN,
    align,
    alive,
    build,
    commanded,
    drains,
    elapse,
    energised,
    faces,
    gives,
    heard,
    loco,
    move,
    reads,
    settle,
    speeds,
    stand,
    switches,
    takes,
    turns,
    wired,
)


def held_by(said: list[tuple[str, Payload]]) -> list[dict[str, str]]:
    """Every value `state/taken` carried, as the maps they carry: the stamp is
    the row's shape rather than the news."""
    return [
        {
            str(train): str(throttle)
            for train, throttle in dict(payload["taken"]).items()
        }
        for _topic, payload in said
    ]


def granted(bus: InProcessBus, train: str) -> None:
    align(bus, "crossover", "to_dn")
    move(bus, train, "crossover", "to_dn", "dn_e", 0.6)


def test_a_take_publishes_the_map_with_the_train_and_its_throttle() -> None:
    bus, _app = build()
    said = heard(bus, TAKEN)
    takes(bus, "single")

    assert held_by(said) == [{}, {"single": "t-1"}]


def test_a_second_take_by_another_throttle_is_dropped() -> None:
    """The second person asks the first: the last take does not win, and the
    second throttle's lever drives nothing (ADR-0079, decision 5)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    said = heard(bus, TAKEN)
    written = commanded(bus)
    granted(bus, "single")
    takes(bus, "single", throttle="t-2")
    turns(bus, "single", 0.6, throttle="t-2")

    assert held_by(said) == [{"single": "t-1"}]
    assert speeds(written) == []


def test_a_take_by_the_throttle_already_holding_it_says_nothing() -> None:
    bus, _app = build()
    takes(bus, "single")
    said = heard(bus, TAKEN)
    takes(bus, "single")

    assert held_by(said) == [{"single": "t-1"}]


def test_a_take_that_cannot_be_read_is_dropped() -> None:
    """A missing `throttle` is not a release, and an empty id names no
    throttle: both leave the train where it was."""
    bus, _app = build()
    takes(bus, "single")
    said = heard(bus, TAKEN)
    for payload in ({}, {"train": "single"}, {"train": "single", "throttle": ""}):
        bus.publish(TAKE_WANTED, payload)
        bus.drain()

    assert held_by(said) == [{"single": "t-1"}]


def test_taking_a_running_train_writes_nothing() -> None:
    """It keeps the speed it had: writing zero here would stop a running train
    the instant somebody selected it, which is not what selecting it means."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    takes(bus, "single")

    assert speeds(written) == [("3", 0.6)]


def test_a_train_taken_mid_transit_is_still_stopped_on_arrival() -> None:
    """The move ending writes `0.0` whoever drives it."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    takes(bus, "single")
    turns(bus, "single", 0.3)

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.6), ("3", 0.3), ("3", 0.0)]


def test_a_release_publishes_the_map_without_the_train() -> None:
    bus, _app = build()
    takes(bus, "single")
    said = heard(bus, TAKEN)
    gives(bus, "single")

    assert held_by(said) == [{"single": "t-1"}, {}]


def test_releasing_a_train_no_throttle_holds_changes_nothing() -> None:
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    said = heard(bus, TAKEN)
    written = commanded(bus)
    gives(bus, "single")

    assert held_by(said) == [{}]
    assert speeds(written) == []


def test_a_train_released_standing_mid_move_gets_its_grants_speed() -> None:
    """Taken before its grant and never moved by the lever, the train stands
    with its route held. A release hands the move back to the driver, which
    gives it the speed the grant implies (ADR-0083)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    takes(bus, "topped")
    written = commanded(bus)
    granted(bus, "topped")
    assert speeds(written) == []

    gives(bus, "topped")

    assert speeds(written) == [("3", 0.6), ("4", -0.6)]


def released_running(
    silent: bool = False,
) -> tuple[InProcessBus, LayoutInterface, Clock, list[tuple[str, Payload]]]:
    """In `automatic`, `single` taken, granted, driven at 0.4 mid-move and
    released — by `take_wanted` with `null`, or by its throttle going silent —
    and every traction write from the take on."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    granted(bus, "single")
    turns(bus, "single", 0.4)
    if silent:
        settle(bus, app, clock, after=THROTTLE_SILENCE_S)
    else:
        gives(bus, "single")
    return bus, app, clock, written


def test_a_train_released_running_in_automatic_keeps_its_speed() -> None:
    """A train a person was running slowly does not lurch to the driver's
    speed: nothing is written, and the arrival stops it (ADR-0081, decision
    6)."""
    bus, app, clock, written = released_running()
    assert speeds(written) == [("3", 0.4)]

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.4), ("3", 0.0)]


def test_a_train_released_running_by_silence_keeps_its_speed() -> None:
    bus, app, clock, written = released_running(silent=True)
    assert speeds(written) == [("3", 0.4)]

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.4), ("3", 0.0)]


def test_a_cut_after_a_release_resumes_at_the_grants_speed() -> None:
    """The cut zeroed the wheels and the speed the person left is gone with
    it, so the `on` gives the train what its grant implies, as it gives any
    train this app drives (ADR-0078, decision 6)."""
    bus, _app, _clock, written = released_running()
    bus.publish(POWER_WANTED, {"power": "off"})
    bus.drain()
    bus.publish(POWER_WANTED, {"power": "on"})
    bus.drain()

    assert speeds(written) == [("3", 0.4), ("3", 0.0), ("3", 0.6)]


def test_a_switch_to_manual_after_a_release_still_stops_it_on_arrival() -> None:
    """The crossing became the driver's at the release, so a switch to
    `manual` lets the train finish its move and the arrival writes `0.0`."""
    bus, app, clock, written = released_running()
    switches(bus, MANUAL)
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.4), ("3", 0.0)]


def test_a_release_in_automatic_while_draining_keeps_its_speed() -> None:
    """A drain keeps the supply on, so the train runs on to its sensor at the
    person's speed and the drain ends after it."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    granted(bus, "single")
    turns(bus, "single", 0.4)
    drains(bus)
    gives(bus, "single")

    assert speeds(written) == [("3", 0.4)]


def test_a_train_released_in_automatic_is_stopped_on_arrival() -> None:
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    granted(bus, "single")
    gives(bus, "single")

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_a_release_in_automatic_with_no_move_outstanding_writes_zero() -> None:
    """A train released does not keep the speed a person left on it, and there
    is no grant here to imply another one."""
    bus, _app = build()
    energised(bus)
    stand(bus, "topped", "up_w")
    takes(bus, "topped")
    written = commanded(bus)
    gives(bus, "topped")

    assert speeds(written) == [("3", 0.0), ("4", 0.0)]


def test_a_release_in_manual_mid_transit_writes_zero() -> None:
    """Released, a train stops in `manual`: nobody drives it, so it stands
    until a throttle takes it (ADR-0079, decision 6). Nothing is written at its
    arrival either, the train having been told to stand already."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    granted(bus, "single")
    turns(bus, "single", 0.5)
    gives(bus, "single")

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == [("3", 0.5), ("3", 0.0)]


def test_a_release_over_dead_rails_writes_zero() -> None:
    """A grant cannot be acted on over dead track at all, so it implies
    nothing: a desired speed left standing on a row is a train that would start
    the moment the power came back (ADR-0041)."""
    bus, _app = build()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    granted(bus, "single")
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    written = commanded(bus)
    gives(bus, "single")

    assert speeds(written)[-1:] == [("3", 0.0)]


def test_a_release_of_a_train_with_no_addressed_car_writes_nothing() -> None:
    bus, _app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    takes(bus, "freight_1")
    written = commanded(bus)
    gives(bus, "freight_1")

    assert speeds(written) == []


def test_a_throttle_silent_for_five_seconds_is_released() -> None:
    """A phone gone to sleep does not leave its train running at its last
    speed: the train is released as `take_wanted` with `null` would release
    it, here in `manual`, so it stops."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    granted(bus, "single")
    turns(bus, "single", 0.5)
    said = heard(bus, TAKEN)
    written = commanded(bus)

    settle(bus, app, clock, after=4.9)
    assert held_by(said) == [{"single": "t-1"}]

    settle(bus, app, clock, after=0.1)

    assert held_by(said) == [{"single": "t-1"}, {}]
    assert speeds(written)[-1:] == [("3", 0.0)]


def test_the_silence_a_throttle_is_allowed_is_the_apps_to_be_told() -> None:
    """An installation whose phones sleep sooner, or later, sets how long
    `layout` waits (docs/DEPLOY.md): the train is held to the last tenth of a
    second of it and released on it."""
    bus, app, clock = wired(driving=MANUAL, throttle_silence_s=2.0)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    granted(bus, "single")
    turns(bus, "single", 0.5)
    said = heard(bus, TAKEN)

    settle(bus, app, clock, after=1.9)
    assert held_by(said) == [{"single": "t-1"}]

    settle(bus, app, clock, after=0.1)

    assert held_by(said) == [{"single": "t-1"}, {}]


def test_a_throttle_that_keeps_saying_it_is_there_keeps_its_train() -> None:
    bus, app, clock = wired()
    takes(bus, "single")
    said = heard(bus, TAKEN)
    for _second in range(10):
        elapse(clock, 1.0)
        alive(bus)
        app.settle()
        bus.drain()

    assert held_by(said) == [{"single": "t-1"}]


def test_another_throttle_saying_it_is_there_keeps_nothing() -> None:
    """The id names the throttle, so one throttle's word does not hold another
    throttle's trains."""
    bus, app, clock = wired()
    takes(bus, "single")
    said = heard(bus, TAKEN)
    for _second in range(5):
        elapse(clock, 1.0)
        alive(bus, "t-2")
    settle(bus, app, clock, after=0.0)

    assert held_by(said) == [{"single": "t-1"}, {}]


def test_silence_releases_every_train_of_that_throttle_and_no_other() -> None:
    bus, app, clock = wired()
    takes(bus, "single")
    takes(bus, "topped", throttle="t-2")
    said = heard(bus, TAKEN)
    elapse(clock, 3.0)
    alive(bus, "t-2")
    settle(bus, app, clock, after=2.0)

    assert held_by(said) == [
        {"single": "t-1", "topped": "t-2"},
        {"topped": "t-2"},
    ]


def test_a_take_of_a_train_made_since_the_build_drives_its_car() -> None:
    """A train made in the stock view after the last build is on the store's
    roster and nowhere else; the take reads the roster again, so the lever
    reaches the car's address (ADR-0092, decision 2)."""
    asked: list[None] = []

    def reread() -> Roster | None:
        asked.append(None)
        return Roster("bench", {"railcar": Train((Coupled(loco("7")),))})

    bus, _app, _clock = wired(driving=MANUAL, reread=reread)
    energised(bus)
    stand(bus, "railcar", "up_w")
    faces(bus, railcar="up_w.A-to-B")
    written = commanded(bus)
    takes(bus, "railcar")
    turns(bus, "railcar", 0.4)

    assert speeds(written) == [("7", 0.4)]
    assert len(asked) == 1


def test_a_take_of_a_train_it_has_reads_no_roster() -> None:
    """Only a train the interface lacks costs a store read: one it was built
    with keeps its entry until the next build (ADR-0071)."""
    asked: list[None] = []

    def reread() -> Roster | None:
        asked.append(None)
        return Roster("bench", {"single": Train((Coupled(loco("9")),))})

    bus, _app, _clock = wired(driving=MANUAL, reread=reread)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    takes(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]
    assert asked == []


def test_a_train_read_again_keeps_the_entry_of_one_it_has() -> None:
    """The answer adds the trains the interface lacks and nothing else: a
    train it has, changed in the store since, drives as it was built."""
    store = Roster(
        "bench",
        {
            "single": Train((Coupled(loco("9")),)),
            "railcar": Train((Coupled(loco("7")),)),
        },
    )
    bus, _app, _clock = wired(driving=MANUAL, reread=lambda: store)
    energised(bus)
    stand(bus, "railcar", "up_w")
    stand(bus, "single", "up_e")
    faces(bus, railcar="up_w.A-to-B", single="up_e.A-to-B")
    takes(bus, "railcar")
    written = commanded(bus)
    takes(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]


def test_a_store_that_does_not_answer_applies_the_take_as_before() -> None:
    """None is a store that did not answer: the roster stays as it was, the
    take is held all the same, and the lever has no wheels to turn."""
    bus, _app, _clock = wired(driving=MANUAL, reread=lambda: None)
    energised(bus)
    stand(bus, "railcar", "up_w")
    faces(bus, railcar="up_w.A-to-B")
    said = heard(bus, TAKEN)
    written = commanded(bus)
    takes(bus, "railcar")
    turns(bus, "railcar", 0.4)

    assert held_by(said)[-1] == {"railcar": "t-1"}
    assert speeds(written) == []
