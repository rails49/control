"""Points go out one point gap apart, and a move waits a gap after its last
point (#1127).

A point takes time to move — a stall motor a second or two, a solenoid on a
shared CDU a recharge — and a train starting from rest onto one still moving
derails. So `layout` writes only the points that change, one gap apart in
route order behind whatever is still going out, and lets the move go one gap
after the last of them. Time is the injected clock's, driven here.

The bench railroad's `to_dn` throws `12` and `13`; the suite's own `align`
adds `14` where it wants three points.
"""

from tc49.layout import LayoutInterface
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.settings import POINT_GAP_S, KeptSettings
from tests.layout.railroad import (
    ALIGN,
    SETTINGS,
    SETTINGS_WANTED,
    WANTED_POINT,
    align,
    commanded,
    energised,
    faces,
    heard,
    lies,
    move,
    railroad,
    settings_row,
    settle,
    speeds,
    stand,
    stock,
    wired,
)

GAP = 1.0
"""The gap the suite runs at, a round number to read the times by."""


def ready(
    gap: float = GAP,
) -> tuple[InProcessBus, LayoutInterface, Clock, list[tuple[str, Payload]]]:
    """A live railroad with `single` standing in `up_w` facing nose-first
    over `to_dn`, and every point write from here on."""
    bus, app, clock = wired(point_gap=gap)
    energised(bus)
    stand(bus, "single", "up_w")
    faces(bus, single="up_w.A-to-B")
    return bus, app, clock, writes(bus)


def three(bus: InProcessBus, transit: str = "to_dn") -> None:
    """An `align` over `transit` carrying three points, all thrown."""
    bus.publish(
        ALIGN,
        {
            "connection": "crossover",
            "transit": transit,
            "points": [
                {"addr": addr, "position": "thrown", "reported": False}
                for addr in ("12", "13", "14")
            ],
        },
    )
    bus.drain()


def hand(bus: InProcessBus, addr: str, position: str) -> None:
    """A point thrown by hand, an `align` naming no transit (ADR-0068)."""
    bus.publish(
        ALIGN,
        {
            "connection": None,
            "transit": None,
            "points": [{"addr": addr, "position": position, "reported": False}],
        },
    )
    bus.drain()


def writes(bus: InProcessBus) -> list[tuple[str, Payload]]:
    """Every point write from here on, the rows a bus hands back on
    subscribing left out."""
    written = heard(bus, WANTED_POINT + "/+")
    bus.drain()
    del written[:]
    return written


def when(written: list[tuple[str, Payload]]) -> list[tuple[str, str, object]]:
    """Each point write as its address, position and the time it went out."""
    return [
        (str(payload["addr"]), str(payload["position"]), payload["at"])
        for _topic, payload in written
    ]


def test_three_points_go_out_a_gap_apart_and_the_move_a_gap_after() -> None:
    bus, app, clock, written = ready()
    three(bus)
    traction = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert when(written) == [("12", "thrown", 0.0)]
    assert speeds(traction) == []

    settle(bus, app, clock, after=GAP / 2)
    assert len(written) == 1
    settle(bus, app, clock, after=GAP / 2)
    settle(bus, app, clock, after=GAP)
    assert when(written) == [
        ("12", "thrown", 0.0),
        ("13", "thrown", 1.0),
        ("14", "thrown", 2.0),
    ]
    assert app.position == {"single": "up_w"}

    settle(bus, app, clock, after=GAP / 2)
    assert speeds(traction) == []
    settle(bus, app, clock, after=GAP / 2)
    assert speeds(traction) == [("3", 0.6)]
    assert app.position == {"single": "dn_e"}


def test_points_already_asked_for_write_nothing_and_the_move_goes_at_once() -> None:
    bus, app, clock, written = ready()
    align(bus, "crossover", "to_dn")
    settle(bus, app, clock, after=GAP)
    settle(bus, app, clock, after=GAP)
    before = len(written)

    align(bus, "crossover", "to_dn")
    traction = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    assert len(written) == before
    assert speeds(traction) == [("3", 0.6)]


def test_points_a_bus_hands_back_are_not_written_again() -> None:
    """What `wanted/point` holds is what the last run asked, and a point it
    holds is not fired again by the first `align` of this one."""
    clock = Clock()
    bus = InProcessBus(clock)
    for addr in ("12", "13"):
        bus.publish(f"{WANTED_POINT}/{addr}", {"addr": addr, "position": "thrown"})
    LayoutInterface(bus, railroad(), stock(), clock, point_gap=GAP)
    bus.drain()
    written = writes(bus)

    align(bus, "crossover", "to_dn")

    assert written == []


def test_a_second_align_waits_behind_the_first() -> None:
    bus, app, clock, written = ready()
    three(bus)
    hand(bus, "12", "closed")
    settle(bus, app, clock, after=GAP)
    settle(bus, app, clock, after=GAP)

    assert when(written)[-1] == ("14", "thrown", 2.0)
    settle(bus, app, clock, after=GAP / 2)
    assert len(written) == 3
    settle(bus, app, clock, after=GAP / 2)
    assert when(written)[-1] == ("12", "closed", 3.0)


def test_a_hand_throw_spaces_the_points_after_it() -> None:
    bus, app, clock, written = ready()
    hand(bus, "13", "thrown")
    align(bus, "crossover", "straight")

    assert when(written) == [("13", "thrown", 0.0)]
    settle(bus, app, clock, after=GAP)
    assert when(written) == [("13", "thrown", 0.0), ("12", "closed", 1.0)]


def test_a_reported_point_waits_for_both_its_gap_and_its_report() -> None:
    bus, app, clock, _written = ready()
    align(bus, "crossover", "to_dn", reported=("12",))
    traction = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)

    lies(bus, "12", "thrown")
    assert speeds(traction) == []
    settle(bus, app, clock, after=GAP)
    assert speeds(traction) == []
    settle(bus, app, clock, after=GAP)
    assert speeds(traction) == [("3", 0.6)]


def test_a_reported_point_past_its_gap_still_waits_for_its_report() -> None:
    bus, app, clock, _written = ready()
    align(bus, "crossover", "to_dn", reported=("12",))
    traction = commanded(bus)
    move(bus, "single", "crossover", "to_dn", "dn_e", 0.6)
    settle(bus, app, clock, after=GAP)
    settle(bus, app, clock, after=GAP)
    assert speeds(traction) == []

    lies(bus, "12", "thrown")
    assert speeds(traction) == [("3", 0.6)]


def test_a_gap_set_is_the_gap_of_the_next_point_written() -> None:
    clock = Clock()
    bus = InProcessBus(clock)
    kept: list[KeptSettings] = []
    app = LayoutInterface(bus, railroad(), stock(), clock, keep=kept.append)
    bus.drain()
    written = writes(bus)

    bus.publish(SETTINGS_WANTED, {"point_gap": 1.0})
    bus.drain()
    assert bus.last_values[SETTINGS] == {"at": 0.0, **settings_row(1.0)}
    assert kept == [KeptSettings(1.0)]

    bus.publish(SETTINGS_WANTED, {"point_gap": 6})
    bus.drain()
    assert app.point_gap == 1.0

    align(bus, "crossover", "to_dn")
    settle(bus, app, clock, after=0.5)
    assert len(written) == 1
    settle(bus, app, clock, after=0.5)
    assert when(written) == [("12", "thrown", 0.0), ("13", "thrown", 1.0)]


def test_with_no_gap_kept_the_railroad_runs_at_half_a_second() -> None:
    """Built with no gap, as `__main__` builds a railroad that keeps none,
    and keeping nothing until a person sets one."""
    clock = Clock()
    bus = InProcessBus(clock)
    kept: list[KeptSettings] = []
    app = LayoutInterface(bus, railroad(), stock(), clock, keep=kept.append)
    bus.drain()
    written = writes(bus)

    assert POINT_GAP_S == 0.5
    assert bus.last_values[SETTINGS] == {"at": 0.0, **settings_row(0.5)}
    align(bus, "crossover", "to_dn")
    settle(bus, app, clock, after=0.25)
    assert len(written) == 1
    settle(bus, app, clock, after=0.25)
    assert when(written) == [("12", "thrown", 0.0), ("13", "thrown", 0.5)]
    assert kept == []


def test_signals_are_not_spaced() -> None:
    bus, _app, _clock, _written = ready()
    signals = heard(bus, "tc49/layout/state/wanted/signal/+")
    bus.publish(
        "tc49/dispatch/state/aspects",
        {"aspects": {"up_w.B": "clear", "up_e.A": "clear", "dn_e.A": "clear"}},
    )
    bus.drain()

    assert [payload["at"] for _topic, payload in signals] == [0.0] * 3
