"""A person throwing a point by hand (ADR-0068, #664).

`tc49/dispatch/point_wanted` names a point's address and the position wanted.
The dispatcher passes it on as an `align` naming no transit unless the point
is **lit** — on the way of a transit that is locked or committed — and drops
it with no reply where it is, or where no point on the railroad wears the
address at all.

Driven at the bus on `reversing-loops`, the one railroad whose points carry
addresses: `mover` stands in C4, and a route out of it goes through j2 and
then j1. The address `align`s ride on are read off the trace.
"""

from typing import Any, cast

from tc49.bench.runner import Assembly
from tc49.lib.bus import Payload
from tests.harness import RUN_WANTED, events, live, press, ticks

POINT_WANTED = "tc49/dispatch/point_wanted"
POWER = "tc49/layout/state/power"
REQUEST_WANTED = "tc49/schedule/request_wanted"


def railroad() -> Assembly:
    """`reversing-loops` with `mover` standing in C4 and nothing asked of it."""
    return live("reversing-loops/positions")


def sent_off(assembly: Assembly, dest: str) -> Assembly:
    """`mover` launched towards `dest`, its route chosen and its first
    increment locked."""
    press(assembly, REQUEST_WANTED, {"train": "mover", "dest": [dest]})
    assert assembly.dispatcher.state.active
    return assembly


def throw(assembly: Assembly, addr: str, position: str = "thrown") -> None:
    press(assembly, POINT_WANTED, {"addr": addr, "position": position})


def by_hand(assembly: Assembly) -> list[dict[str, Any]]:
    """Every `align` that names no transit: the throws a person asked for."""
    return [line for line in events(assembly.trace, "align") if line["transit"] is None]


def thrown(addr: str, position: str = "thrown") -> dict[str, Any]:
    """The `align` a throw by hand goes out as, as the trace writes it."""
    return {
        "time": 0.0,
        "event": "align",
        "connection": None,
        "transit": None,
        "points": [{"addr": addr, "position": position}],
    }


def test_a_point_on_no_lit_transit_goes_out_as_an_align_naming_no_transit() -> None:
    """Nothing is lit on a railroad standing still, so the throw is passed
    on: `connection` and `transit` null, the one point as it was asked."""
    assembly = railroad()

    throw(assembly, "113", "closed")

    assert by_hand(assembly) == [thrown("113", "closed")]


def test_an_address_no_point_wears_is_dropped() -> None:
    """A signal's address, or nobody's: throwing it would change an aspect or
    do nothing, so nothing goes out."""
    assembly = railroad()

    throw(assembly, "999")

    assert events(assembly.trace, "align") == []


def test_a_point_on_a_locked_transit_is_dropped() -> None:
    """`110` is sw14, on the way of j2's transit out of C4, which the launch
    locked for `mover`."""
    assembly = sent_off(railroad(), "A2.A")
    assert "j2.C4_A__CE2_A" in assembly.dispatcher.state.locks

    throw(assembly, "110", "closed")

    assert by_hand(assembly) == []


def test_a_point_on_a_committed_transit_not_yet_locked_is_dropped() -> None:
    """Towards C6 the route ends through j3, which is committed and not
    locked yet: `113`, sw17, is on that way and is lit all the same."""
    assembly = sent_off(railroad(), "C6.A")
    state = assembly.dispatcher.state
    assert "j3.C3b_B__C6_A" not in state.locks
    assert "j3.C3b_B__C6_A" in state.active["mover"].route.transits

    throw(assembly, "113", "thrown")

    assert by_hand(assembly) == []


def test_an_address_two_points_wear_is_dropped_when_one_is_on_a_locked_way() -> None:
    """`101` is worn by sw1 and sw2, which move together. The way into A2 is
    locked and names it, so the address is lit whichever turnout a person
    meant — though sw1 and sw2 also lie on ways nothing is lit over."""
    assembly = sent_off(railroad(), "A2.A")
    assert "j1.A2_A__CE2_B" in assembly.dispatcher.state.locks

    throw(assembly, "101", "thrown")

    assert by_hand(assembly) == []


def test_the_same_throw_goes_out_once_the_route_has_ended() -> None:
    """Dropped, not deferred: the dispatcher keeps nothing of it. Asked again
    once the lock is released and `mover` has arrived, it is passed on."""
    assembly = sent_off(railroad(), "A2.A")
    throw(assembly, "110", "closed")
    assert by_hand(assembly) == []

    ticks(assembly, 10)
    state = assembly.dispatcher.state
    assert not state.active
    assert "j2.C4_A__CE2_A" not in state.locks

    throw(assembly, "110", "closed")

    assert [line["points"] for line in by_hand(assembly)] == [
        [{"addr": "110", "position": "closed"}]
    ]


def test_a_held_run_passes_the_throw_on() -> None:
    """The hold is a brake on commitment, and a throw on an unlit road
    commits nothing."""
    assembly = railroad()
    press(assembly, RUN_WANTED, {"run": "held"})

    throw(assembly, "113")

    assert by_hand(assembly) == [thrown("113")]


def test_dead_track_passes_the_throw_on() -> None:
    """The power is the layout's to answer for: with it off the `wanted/point`
    row is stored and the point moves when power returns (ADR-0054), so the
    dispatcher passes the throw on as it would on live track."""
    assembly = railroad()
    press(assembly, POWER, {"power": "off"})
    assert assembly.dispatcher.state.power == "off"

    throw(assembly, "113")

    assert by_hand(assembly) == [thrown("113")]


def test_a_malformed_payload_is_dropped_and_nothing_raises() -> None:
    """Whatever a page writes: no address, an empty one, a number, a
    position that is neither of the two, or no object at all."""
    assembly = railroad()

    for payload in (
        {"position": "thrown"},
        {"addr": "", "position": "thrown"},
        {"addr": 113, "position": "thrown"},
        {"addr": "113"},
        {"addr": "113", "position": "reverse"},
        {"addr": "113", "position": None},
        ["113", "thrown"],
        "113",
        None,
    ):
        press(assembly, POINT_WANTED, cast(Payload, payload))

    assert events(assembly.trace, "align") == []
