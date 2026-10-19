"""Taking a train across: the three rules a `move` meets (#287).

Align before move, the near-end check, and nothing at all while the rails are
dead. Each exists because the bus promises less than it looks like it does —
no ordering between topics, and at-least-once delivery — and each turns a
command that was true once into a no-op rather than into a collision.

The move itself publishes nothing: what turns a wheel is the traction write
(#296), and the sensors that say the train arrived are the detectors'. So
what these assert is where the app believes each train stands, which is the
whole of what the near-end check is made of.
"""

from tests.layout.railroad import (
    DEVICE_TRACK,
    MOVE,
    WANTED_POINT,
    align,
    build,
    energised,
    heard,
    move,
    stand,
)


def test_a_train_crosses_when_the_way_has_been_set() -> None:
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")

    assert app.position == {"freight_1": "dn_e"}


def test_a_move_delivered_before_its_align_waits_for_it() -> None:
    """The two commands have two publishers and the bus promises no ordering
    between topics, so the duty sits here: the points are written first, and
    the train crosses after them (SYSTEM.md, layout interface)."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    written = heard(bus, WANTED_POINT + "/#")

    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    assert app.position == {"freight_1": "up_w"}
    assert written == []

    align(bus, "crossover", "to_dn")
    assert [topic for topic, _ in written] == [
        WANTED_POINT + "/12",
        WANTED_POINT + "/13",
    ]
    assert app.position == {"freight_1": "dn_e"}


def test_a_held_move_is_read_again_against_the_railroad_it_lands_on() -> None:
    """Everything that stopped it can change while it waits, so a held
    command meets all three rules at the moment it is acted on and not at the
    moment it arrived."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    bus.publish(DEVICE_TRACK, {"power": "off"})
    bus.drain()
    align(bus, "crossover", "to_dn")

    assert app.position == {"freight_1": "up_w"}


def test_an_align_lets_through_the_move_it_names_and_no_other() -> None:
    """One transit's route being set says nothing about another's."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    bus.publish(
        MOVE,
        {
            "train": "freight_1",
            "connection": "crossover",
            "transit": "to_dn",
            "into": "dn_e",
            "speed": 1.0,
        },
    )
    bus.drain()
    align(bus, "crossover", "straight")

    assert app.position == {"freight_1": "up_w"}


def test_an_align_authorises_one_crossing_and_the_move_consumes_it() -> None:
    """The rule protects every crossing of a transit and not just its first.

    A transit is crossed many times in a session, and a record of every one
    ever aligned would pass the check forever after the first — leaving the
    move that arrives before its `align` unheld exactly when the points have
    not thrown. So the move takes the authorisation with it, and the next one
    waits for an `align` of its own (#305).
    """
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    assert app.position == {"freight_1": "dn_e"}

    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")

    assert app.position == {"freight_1": "up_w"}


def test_the_consumed_move_is_held_and_the_next_align_releases_it() -> None:
    """Held rather than dropped: the second crossing meets the same rule the
    first did, so its `align` lands and the train goes (#305)."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    align(bus, "crossover", "to_dn")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")

    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    align(bus, "crossover", "to_dn")

    assert app.position == {"freight_1": "dn_e"}


def test_a_move_released_by_its_align_consumes_it_too() -> None:
    """The other path to the same act: a move that waited is acted on inside
    the `align`, and it leaves no authorisation behind it either (#305)."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    align(bus, "crossover", "to_dn")
    assert app.position == {"freight_1": "dn_e"}

    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")

    assert app.position == {"freight_1": "up_w"}
