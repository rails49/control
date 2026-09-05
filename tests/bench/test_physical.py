"""The harness's run on the physical binding (#314): `LayoutInterface` and
`DccEx` where the simulator would be.

What is asserted is the assembly and the loop over it, over the station and
the waiting `physical.py` holds: the station is reached by **address** here
rather than by the injected connection the translator's own suite uses —
opening the address is what the assembly has to get right — so these tests
bind a port on loopback and nothing needs hardware, which is the rule the
whole gate sits under.

The railroad is whichever the checkout has: the library railroads are renamed
and moved under #319, so a name spelled here would go red for a reason that is
not this suite's.
"""

import signal
from collections.abc import Callable

import pytest

from tc49.bench.runner import Assembly, assemble_live
from tc49.lib.mqtt import address
from tests.bench.physical import (
    HOST,
    IPV6_HOST,
    PERIOD_S,
    Station,
    a_railroad,
    closed_port,
    has_ipv6_loopback,
    until,
)

DEVICE_LINK = "tc49/layout/state/device/link/dccex"
POWER_WANTED = "tc49/layout/power_wanted"
WANTED_TRACTION = "tc49/layout/state/wanted/traction"

TRACK_ON = b"<1>"
TRACK_OFF = b"<0>"

HALF_SPEED_10 = b"<t 10 63 1>"
HALTED_10 = b"<t 10 0 1>"


def link_of(assembly: Assembly) -> tuple[str, str]:
    """What the run last said about its link to the station: the word, and the
    reason a person reads beside it."""
    value = assembly.bus.last_values.get(DEVICE_LINK)
    if not isinstance(value, dict):
        return ("", "")
    return (str(value.get("link", "")), str(value.get("detail", "")))


def link_while_running(
    assembly: Assembly, done: Callable[[tuple[str, str]], bool]
) -> tuple[str, str]:
    """Run until the link says what `done` is waiting for, and answer what it
    last said.

    Read on the turn and never afterwards: ending a run lets its link go, and
    the row then honestly says so — a session that has stopped is not one
    whose station is reachable.
    """
    last = ("", "")

    def turn() -> bool:
        nonlocal last
        last = link_of(assembly)
        return done(last)

    assembly.run(PERIOD_S, stop=until(turn))
    return last


# -- which binding a run is built on -----------------------------------------


def test_a_station_puts_the_physical_binding_where_the_simulator_would_be() -> None:
    """A run has **one** binding of the layout interface and neither knows the
    other exists (ADR-0030). Named a station, the assembly holds the core app
    and its translator and no simulator at all."""
    layout, roster = a_railroad()
    driven = assemble_live(layout, roster, station=(HOST, closed_port()))
    assert driven.simulator is None
    assert driven.interface is not None and driven.dccex is not None


def test_a_run_with_no_station_is_exactly_what_it_was() -> None:
    """The simulator branch is untouched: with no station named, the run is
    the one `tc49 live` has always built, and nothing physical is
    constructed."""
    layout, roster = a_railroad()
    simulated = assemble_live(layout, roster)
    assert simulated.simulator is not None
    assert simulated.interface is None and simulated.dccex is None


def test_the_railroad_comes_up_dark_and_unreached_before_anything_runs() -> None:
    """Constructed and not yet run, the two rows already say so: a client
    joining now is served that rather than an absence (ADR-0032)."""
    layout, roster = a_railroad()
    driven = assemble_live(layout, roster, station=(HOST, closed_port()))
    driven.bus.drain()
    word, detail = link_of(driven)
    assert word == "down" and "not connected" in detail


# -- the loop the physical branch runs ---------------------------------------


def test_the_run_reaches_the_station_and_says_the_link_is_up() -> None:
    """`tc49 live <railroad> --station <host>:<port>` comes up: the loop opens
    the connection, the station answers, and `device/link/dccex` says so."""
    layout, roster = a_railroad()
    with Station() as station:
        driven = assemble_live(layout, roster, station=(HOST, station.port))
        word, detail = link_while_running(driven, lambda said: said[0] == "up")
        assert word == "up" and f"{HOST}:{station.port}" in detail


def test_the_run_advances_the_clock_to_wall_time() -> None:
    """The pacer's first job. Steel keeps its own time, so nothing else in a
    physical run moves the clock — and the settling the debounce does is
    measured against it, which is what makes it the loop's business."""
    layout, roster = a_railroad()
    with Station() as station:
        driven = assemble_live(layout, roster, station=(HOST, station.port))
        assert driven.clock.now == 0.0
        turns = 0

        def counted() -> bool:
            nonlocal turns
            turns += 1
            return turns > 3

        driven.run(PERIOD_S, stop=until(counted))
        assert driven.clock.now >= PERIOD_S


def test_a_station_that_is_not_there_leaves_the_session_running() -> None:
    """Broken hardware is reported, never worked around (ADR-0050): the run
    comes up either way and the row says what is wrong with it."""
    layout, roster = a_railroad()
    driven = assemble_live(layout, roster, station=(HOST, closed_port()))
    word, detail = link_while_running(
        driven, lambda said: said[1].startswith("connecting to")
    )
    assert word == "down"
    assert detail.startswith(f"connecting to {HOST}:")


# -- standing the railroad down ----------------------------------------------


def test_the_run_ending_switches_the_track_off() -> None:
    """The process ending is not by itself an instruction to the railroad, so
    the exit is one (#314). The rails are powered during the run — an `off`
    goes out on connect too, the railroad coming up dark — so what this reads
    is the `off` that came *after* the `on`."""
    layout, roster = a_railroad()
    with Station() as station:
        driven = assemble_live(layout, roster, station=(HOST, station.port))
        driven.bus.publish(POWER_WANTED, {"power": "on"})
        driven.run(PERIOD_S, stop=until(lambda: station.waits_for(TRACK_ON, 0.0)))
        assert station.waits_for(TRACK_OFF)
        heard = station.heard()
        assert heard.rindex(TRACK_OFF) > heard.rindex(TRACK_ON)


def test_an_interrupt_stands_the_railroad_down_before_the_run_leaves() -> None:
    """Ctrl-C is the ordinary way a session ends, and it takes a path of its
    own: `asyncio.Runner` cancels the task it is waiting on rather than
    raising in place, the `finally` gets to `await` after the cancellation has
    already been delivered, and the zeros are drained out before the link is
    let go. Any one of those could stop being true silently, so the interrupt
    is sent here for real — `raise_signal` is a SIGINT to this process, and
    the handler installed over the run is the one a terminal's Ctrl-C
    reaches.

    Installed rather than assumed, because a suite does not always inherit
    it: a shell hands a background child SIGINT already ignored, and a raised
    signal then does nothing at all. `asyncio.Runner` puts its cancelling
    handler in only over `default_int_handler`, so the run is entered in the
    state an interactive session is in and the ambient one is put back
    afterwards.

    The interrupt arrives once the station has heard a locomotive commanded,
    so what is asserted after it is a zero over a speed that was really
    running, and the `off` after that zero. A run that never leaves ends at
    the waiting limit instead and fails there: `KeyboardInterrupt` is what
    `tc49 live` catches, and its absence is the stand-down not happening.
    """
    layout, roster = a_railroad()
    with Station() as station:
        driven = assemble_live(layout, roster, station=(HOST, station.port))
        driven.bus.publish(POWER_WANTED, {"power": "on"})
        # The row the layout app writes on a move, published here directly:
        # this suite is about the loop and the exit, not about how a speed
        # comes to be commanded.
        driven.bus.publish(f"{WANTED_TRACTION}/10", {"addr": "10", "speed": 0.5})
        sent = False

        def interrupts() -> bool:
            nonlocal sent
            if not sent and station.waits_for(HALF_SPEED_10, 0.0):
                sent = True
                signal.raise_signal(signal.SIGINT)
            return False  # the interrupt ends the run, never the stop

        ambient = signal.signal(signal.SIGINT, signal.default_int_handler)
        try:
            with pytest.raises(KeyboardInterrupt):
                driven.run(PERIOD_S, stop=until(interrupts))
        finally:
            signal.signal(signal.SIGINT, ambient)

        assert station.waits_for(HALTED_10), "the interrupt sent no zeros"
        assert station.waits_for(TRACK_OFF), "the interrupt left the track on"
        heard = station.heard()
        assert heard.rindex(HALTED_10) > heard.index(HALF_SPEED_10)
        assert heard.rindex(TRACK_OFF) > heard.rindex(HALTED_10)


# -- the address a station is opened on --------------------------------------


@pytest.mark.skipif(
    not has_ipv6_loopback(), reason="this machine has no IPv6 loopback to listen on"
)
def test_a_bracketed_address_opens_the_station_listening_on_it() -> None:
    """What the brackets are for: an address written the one unambiguous way
    an IPv6 host takes a port reaches a station on that host, rather than
    parsing and then failing to resolve (#335). Where a machine has no IPv6
    loopback to bind there is nothing to reach, and what the address parses
    to is `tests/lib/test_mqtt.py`'s either way."""
    layout, roster = a_railroad()
    with Station(IPV6_HOST) as station:
        host, port = address(f"[{IPV6_HOST}]:{station.port}")
        driven = assemble_live(layout, roster, station=(host, port))
        word, _ = link_while_running(driven, lambda said: said[0] == "up")
        assert word == "up"
        assert station.waits_for(TRACK_OFF)


def test_a_speed_the_last_run_left_does_not_roll_a_locomotive() -> None:
    """A traction row is retained, so the speed the last run left is still on
    the broker when `layout` comes back up (ADR-0059, decision 3) — and it
    would otherwise be replayed to the station, rolling the locomotive the
    instant the operator presses power-on, with no grant and the run still
    held (#333).

    `layout` comes up having written zero over the row, so what the station
    hears is a stop and never the speed."""
    layout, roster = a_railroad()
    with Station() as station:
        driven = assemble_live(
            layout,
            roster,
            retained={f"{WANTED_TRACTION}/10": {"addr": "10", "speed": 0.5}},
            station=(HOST, station.port),
        )
        driven.bus.publish(POWER_WANTED, {"power": "on"})
        driven.run(PERIOD_S, stop=until(lambda: station.waits_for(TRACK_ON, 0.0)))

        assert station.waits_for(HALTED_10)
        assert HALF_SPEED_10 not in station.heard()
