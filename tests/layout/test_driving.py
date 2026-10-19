"""The railroad's driving mode, and what changing it is worth on the rails
(ADR-0079).

The railroad is `manual` or `automatic`, and comes up `manual`. The dispatcher
routes the same in both, so a granted move throws its points, passes the
near-end check and is recorded either way. What the mode decides is who drives
a train no throttle holds: this app in `automatic`, on the grant's speed, and
nobody in `manual`, where the train stands at its signal until a throttle
takes it.
"""

from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.inventory import AUTOMATIC, MANUAL
from tests.layout.railroad import (
    DRIVING,
    DRIVING_WANTED,
    align,
    build,
    commanded,
    energised,
    faces,
    heard,
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


def modes(said: list[tuple[str, Payload]]) -> list[str]:
    """Every value `state/driving` carried, as the word it carries."""
    return [str(payload["driving"]) for _topic, payload in said]


def granted(bus: InProcessBus, train: str) -> None:
    align(bus, "crossover", "to_dn")
    move(bus, train, "crossover", "to_dn", "dn_e", 0.6)


def test_a_switch_is_stated_on_the_row() -> None:
    bus, _app = build(driving=MANUAL)
    said = heard(bus, DRIVING)
    switches(bus, AUTOMATIC)
    switches(bus, MANUAL)

    assert modes(said) == ["manual", "automatic", "manual"]


def test_a_switch_to_the_mode_already_held_says_nothing() -> None:
    bus, _app = build(driving=MANUAL)
    said = heard(bus, DRIVING)
    switches(bus, MANUAL)

    assert modes(said) == ["manual"]


def test_a_switch_is_accepted_at_any_power() -> None:
    """The railroad comes up dark, and the mode is a person's choice about who
    drives, not a command to the track."""
    bus, _app = build(driving=MANUAL)
    said = heard(bus, DRIVING)
    switches(bus, AUTOMATIC)

    assert modes(said) == ["manual", "automatic"]


def test_a_switch_that_cannot_be_read_is_dropped() -> None:
    bus, _app = build(driving=MANUAL)
    said = heard(bus, DRIVING)
    for payload in ({}, {"driving": "Automatic"}, {"driving": None}):
        bus.publish(DRIVING_WANTED, payload)
        bus.drain()

    assert modes(said) == ["manual"]


def test_a_granted_move_in_manual_writes_no_traction_for_an_untaken_train() -> None:
    """The route is not the driving: the points still throw, the near-end check
    still passes and the crossing is still recorded, and nobody writes the
    wheels. The train stands at its signal until a throttle takes it."""
    bus, app = build(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    thrown = heard(bus, "tc49/layout/state/wanted/point/#")
    written = commanded(bus)
    granted(bus, "single")

    assert [payload["addr"] for _topic, payload in thrown] == ["12", "13"]
    assert speeds(written) == []
    assert app.position == {"single": "dn_e"}


def test_a_granted_move_in_manual_needs_no_facing() -> None:
    """The refusal exists because a sign cannot be guessed, and there is no
    sign to compose here: nothing is being written."""
    bus, app = build(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    written = commanded(bus)
    granted(bus, "single")

    assert speeds(written) == []
    assert app.position == {"single": "dn_e"}


def test_a_train_nobody_drove_is_told_nothing_on_arrival() -> None:
    """It was never told to run, so it is not told to stand."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written) == []


def test_a_throttle_taking_the_standing_train_in_manual_drives_its_move() -> None:
    """The grant waits for a person: the throttle that takes the train drives
    the move the dispatcher already granted."""
    bus, _app = build(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    takes(bus, "single")
    turns(bus, "single", 0.4)

    assert speeds(written) == [("3", 0.4)]


def test_to_manual_a_train_this_app_is_driving_finishes_its_move() -> None:
    """Nothing is written on the switch: the train runs on into the block it
    was granted, is stopped there on arrival as it would have been, and its
    next grant writes nothing (ADR-0079, decision 8)."""
    bus, app, clock = wired()
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "single")
    switches(bus, MANUAL)
    assert speeds(written) == [("3", 0.6)]

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    granted(bus, "single")

    assert speeds(written) == [("3", 0.6), ("3", 0.0)]


def test_to_automatic_a_train_with_a_move_and_no_throttle_gets_the_grant() -> None:
    """The train standing at its signal in `manual` carries on: it is given the
    speed its grant implies, and stopped on arrival."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "topped", "up_w")
    faces(bus, topped="up_w.A-to-B")
    written = commanded(bus)
    granted(bus, "topped")
    assert speeds(written) == []

    switches(bus, AUTOMATIC)
    assert speeds(written) == [("3", 0.6), ("4", -0.6)]

    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)

    assert speeds(written)[2:] == [("3", 0.0), ("4", 0.0)]


def test_to_automatic_a_train_a_throttle_holds_is_left_to_the_throttle() -> None:
    bus, _app = build(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    takes(bus, "single")
    written = commanded(bus)
    granted(bus, "single")
    turns(bus, "single", 0.3)
    switches(bus, AUTOMATIC)

    assert speeds(written) == [("3", 0.3)]


def test_to_automatic_a_train_that_has_arrived_is_told_nothing() -> None:
    """Only a move still outstanding is driven on: a train standing where it
    was sent has no grant left to imply a speed."""
    bus, app, clock = wired(driving=MANUAL)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    granted(bus, "single")
    reads(bus, "dn_e.A", "occupied")
    settle(bus, app, clock)
    written = commanded(bus)
    switches(bus, AUTOMATIC)

    assert speeds(written) == []
