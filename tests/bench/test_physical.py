"""The live session on the physical binding (#314): `LayoutInterface` and
`DccEx` where the simulator would be.

What is asserted is the assembly and the loop over it, over the station and
the waiting `physical.py` holds: the station is reached by **address** here
rather than by the injected connection the translator's own suite uses — an
address is what `--station` gives and opening it is what the session has to
get right — so these tests bind a port on loopback and nothing needs hardware,
which is the rule the whole gate sits under.

The railroad is whichever the checkout has: the library railroads are renamed
and moved under #319, so a name spelled here would go red for a reason that is
not this suite's.
"""

import io
import json
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from websockets.sync.client import ClientConnection, connect

from tc49.bench.cli import addressed, picking, station_note
from tc49.bench.cli import station as station_address
from tc49.bench.runner import Assembly, assemble_live
from tc49.bench.session import Session
from tc49.lib.roster import Car, Coupled, Roster, Train
from tests.bench.physical import (
    HOST,
    PERIOD_S,
    TIMEOUT_S,
    Station,
    a_railroad,
    closed_port,
    until,
    waits_until,
)
from tests.harness import ASSETS, railroads

DEVICE_LINK = "tc49/layout/state/device/link/dccex"
POWER_WANTED = "tc49/layout/power_wanted"

TRACK_ON = b"<1>"
TRACK_OFF = b"<0>"


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


# -- the address, and what the banner makes of the railroad ------------------


def test_a_station_is_one_address_a_person_copies() -> None:
    """`<host>:<port>`, one argument, because that is one thing to copy off a
    running `dccex-usb`. The port splits off the right, so a bracketed IPv6
    host keeps its own colons."""
    assert station_address("dccex-usb:2560") == ("dccex-usb", 2560)
    assert station_address("[::1]:2560") == ("[::1]", 2560)


@pytest.mark.parametrize("text", ["dccex-usb", "2560", ":2560", "host:port", ""])
def test_an_address_that_is_not_one_is_refused_with_the_shape(text: str) -> None:
    with pytest.raises(Exception, match="<host>:<port>"):
        station_address(text)


def test_the_banner_counts_the_trains_a_move_can_actually_reach() -> None:
    """A `move` for a train whose cars carry no address writes no traction row
    at all, so the count is what turns "my train did nothing" into a one-line
    diagnosis. It is a count and not a refusal: a railroad only partly
    addressed is an ordinary state, and the rosters committed here are
    benchmark fixtures with no addresses on them (#318)."""
    real = Car(model="a-loco", kind="locomotive", length=200, addr="10")
    synthetic = Car(model="bench-450", kind="freight", length=450)
    roster = Roster(
        "test",
        {
            "driveable": Train(cars=(Coupled(real),)),
            "hauled": Train(cars=(Coupled(real), Coupled(synthetic))),
            "unreachable": Train(cars=(Coupled(synthetic),)),
        },
    )
    assert addressed(roster) == (2, 1)


def test_a_roster_with_no_addresses_at_all_reads_correctly() -> None:
    """Which is what every railroad in this checkout is until an installation
    brings its own stock — so the banner has to read right either way."""
    layout, roster = a_railroad()
    driveable, unaddressed = addressed(roster)
    assert driveable + unaddressed == len(roster.trains)
    assert layout.name


def test_the_banner_stops_promising_a_switch_a_pinned_session_refuses() -> None:
    """A session ordinarily runs whichever railroad a client names (#148). One
    driving a command station stays where it is, and the banner must say the
    thing that is true of the session in front of it."""
    assert picking(False) == "the panel names the railroad and may switch it"
    assert "may not switch" in picking(True)


def test_the_note_names_the_station_the_railroad_and_who_the_detectors_are() -> None:
    """The three things a physical run says about itself that a simulated one
    does not, among them where its readings come from: no camera publishes
    yet, so a person types them a line at a time and the banner says the shape
    of one (#314, #315)."""
    name = railroads()[0]
    _layout, roster = a_railroad()
    note = station_note(("dccex-usb", 2560), name, roster)
    assert "dccex-usb:2560" in note and name in note
    assert "switches to no other" in note
    assert "<block>.<end> <level>" in note and "occupied, clear or unknown" in note
    assert f"of {len(roster.trains)} trains carry an address" in note


# -- a station pins the railroad ---------------------------------------------


def test_a_station_refuses_the_switch_and_says_why() -> None:
    """`DccEx` holds a desired picture keyed by topic, and carrying one across
    a railroad change would re-apply one railroad's speeds and points to
    another's. The refusal is in words, on the naming client's own thread, and
    the railroad already running is untouched."""
    first, second = railroads()[0], railroads()[1]
    live = Session(ASSETS, PERIOD_S, station=(HOST, closed_port()))
    try:
        assert live.wants(first) is None
        refusal = live.wants(second)
        assert refusal is not None
        assert first in refusal and "one physical railroad" in refusal
    finally:
        live.bridge.close()


def test_a_session_with_no_station_switches_as_it_always_did() -> None:
    """The simulated session is untouched: naming another railroad is what the
    panel's picker does, and it is still accepted."""
    live = Session(ASSETS, PERIOD_S)
    try:
        assert live.wants(railroads()[0]) is None
        assert live.wants(railroads()[1]) is None
    finally:
        live.bridge.close()


# -- the whole session -------------------------------------------------------


def link_frame(client: ClientConnection) -> dict[str, Any]:
    """The first frame that says the link is up, read through the picture a
    joining client is served — which opens with the `down` the run was
    constructed saying, the railroad being unreached until it is reached."""
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        frame = json.loads(client.recv(timeout=TIMEOUT_S))
        if frame.get("topic") == DEVICE_LINK and frame["payload"]["link"] == "up":
            payload: dict[str, Any] = frame["payload"]
            return payload
    raise AssertionError("the session never said the link was up")


def test_a_session_on_a_station_comes_up_and_the_panel_joins_it() -> None:
    """The whole of it: a session named a station comes up on the physical
    binding, and a panel joining it is served the row only that binding
    writes."""
    name = railroads()[0]
    with Station() as station:
        live = Session(ASSETS, PERIOD_S, station=(HOST, station.port))
        assert live.wants(name) is None
        log = io.StringIO()
        thread = threading.Thread(target=live.run, args=(log,), daemon=True)
        thread.start()
        try:
            assert waits_until(lambda: f"running {name}" in log.getvalue())
            with connect(f"ws://{HOST}:{live.bridge.port}/{name}") as client:
                assert link_frame(client)["system"] == "dccex"
        finally:
            live.stop()
            thread.join(TIMEOUT_S)
            live.bridge.close()
    assert station.waits_for(TRACK_OFF), "the session stood the railroad down"
