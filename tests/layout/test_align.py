"""Setting the route: an `align` carries the points its transit needs, and
this app throws what it is told (#287, ADR-0031).

It holds no table of points. The pairs were read off the layout by the
dispatcher, which is what lets a railroad be rewired by redrawing it.
"""

from tc49.lib.bus import InProcessBus, Payload
from tests.layout.railroad import (
    ALIGN,
    WANTED_POINT,
    align,
    build,
    energised,
    heard,
    move,
    stand,
)


def points(bus: InProcessBus) -> list[tuple[str, Payload]]:
    return heard(bus, WANTED_POINT + "/#")


def test_each_pair_is_written_to_the_point_it_addresses() -> None:
    """One desired value per address, on the topic that address names: the
    address is trailing levels and names no system, so whatever is wired acts
    on the ones it recognises and an address nothing answers to does no harm
    (ADR-0059)."""
    bus, _app = build()
    written = points(bus)
    align(bus, "crossover", "to_dn")

    assert written == [
        (
            WANTED_POINT + "/12",
            {"at": 0.0, "addr": "12", "position": "thrown"},
        ),
        (
            WANTED_POINT + "/13",
            {"at": 0.0, "addr": "13", "position": "thrown"},
        ),
    ]


def test_two_pairs_naming_one_address_are_one_write() -> None:
    """One accessory output throws a crossover's two ends as a unit, so a way
    may name one address twice; the second is the same statement and not a
    second point (ADR-0031)."""
    bus, _app = build()
    written = points(bus)
    bus.publish(
        "tc49/layout/align",
        {
            "connection": "crossover",
            "transit": "to_dn",
            "points": [
                {"addr": "12", "position": "thrown"},
                {"addr": "12", "position": "thrown"},
            ],
        },
    )
    bus.drain()

    assert written == [
        (
            WANTED_POINT + "/12",
            {"at": 0.0, "addr": "12", "position": "thrown"},
        )
    ]


def test_a_way_that_needs_nothing_thrown_writes_nothing() -> None:
    """`points` is always stated and `[]` where the way crosses none — the
    document is quiet and the wire explicit — so an empty list is a route set
    by having nothing to set."""
    bus, _app = build()
    written = points(bus)
    bus.publish(
        "tc49/layout/align",
        {"connection": "crossover", "transit": "straight", "points": []},
    )
    bus.drain()

    assert written == []


def test_the_points_are_written_again_on_every_align() -> None:
    """Never only on change: a hand may have flipped one since, so the
    dispatcher names the points before every grant and a translator throws
    what it is told (ADR-0043)."""
    bus, _app = build()
    written = points(bus)
    align(bus, "crossover", "straight")
    align(bus, "crossover", "straight")

    assert [topic for topic, _ in written] == [WANTED_POINT + "/12"] * 2


def test_the_way_back_moves_the_shared_point_the_other_way() -> None:
    """Two ways through one connection want one point in two positions, which
    is what a crossover is; each `align` states its own."""
    bus, _app = build()
    written = points(bus)
    align(bus, "crossover", "to_dn")
    align(bus, "crossover", "straight")

    assert [payload["position"] for _topic, payload in written] == [
        "thrown",
        "thrown",
        "closed",
    ]


def by_hand(bus: InProcessBus, payload: Payload) -> None:
    """An `align` as the dispatcher sends a throw by hand (ADR-0068)."""
    bus.publish(ALIGN, payload)
    bus.drain()


def test_a_throw_by_hand_writes_its_point_retained() -> None:
    """An `align` naming no transit is a person's throw the dispatcher passed
    on: the point is written as asked, and the row is retained, so whatever
    drives the point, and a panel opened later, reads it (ADR-0068)."""
    bus, _app = build()
    by_hand(
        bus,
        {
            "connection": None,
            "transit": None,
            "points": [{"addr": "12", "position": "closed"}],
        },
    )
    late = points(bus)
    bus.drain()

    assert late == [
        (
            WANTED_POINT + "/12",
            {"at": 0.0, "addr": "12", "position": "closed"},
        )
    ]


def test_a_throw_by_hand_lets_no_waiting_move_through() -> None:
    """It names no transit, so it authorises none: a `move` held for its
    `align` keeps waiting, and crosses only on the one naming its transit."""
    bus, app = build()
    energised(bus)
    stand(bus, "freight_1", "up_w")
    move(bus, "freight_1", "crossover", "to_dn", "dn_e")
    by_hand(
        bus,
        {
            "connection": None,
            "transit": None,
            "points": [
                {"addr": "12", "position": "thrown"},
                {"addr": "13", "position": "thrown"},
            ],
        },
    )

    assert app.position == {"freight_1": "up_w"}

    align(bus, "crossover", "to_dn")
    assert app.position == {"freight_1": "dn_e"}


def test_an_align_with_only_one_of_the_two_null_writes_nothing() -> None:
    """Half a route is no route and not a throw either: the frame is dropped
    whole, and dropping it raises nothing (BUS.md)."""
    bus, _app = build()
    written = points(bus)
    pair = [{"addr": "12", "position": "thrown"}]
    by_hand(bus, {"connection": None, "transit": "to_dn", "points": pair})
    by_hand(bus, {"connection": "crossover", "transit": None, "points": pair})

    assert written == []
