"""Setting the route: an `align` carries the points its transit needs, and
this app throws what it is told (#287, ADR-0031).

It holds no table of points. The pairs were read off the layout by the
dispatcher, which is what lets a railroad be rewired by redrawing it.
"""

from tc49.lib.bus import InProcessBus, Payload
from tests.layout.railroad import WANTED_POINT, align, build, heard


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
