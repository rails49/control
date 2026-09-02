"""The live session on the physical binding (#314): `LayoutInterface` and
`DccEx` where the simulator would be.

What is asserted is the assembly and the loop over it, with a plain TCP
listener standing in for `dccex-usb`. The station is reached by **address**
here rather than by the injected connection the translator's own suite uses —
an address is what `--station` gives and opening it is what the session has to
get right — so these tests bind a port on loopback and nothing needs hardware,
which is the rule the whole gate sits under.

The railroad is whichever the checkout has: the library railroads are renamed
and moved under #319, so a name spelled here would go red for a reason that is
not this suite's.
"""

import socket
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Self

from tc49.bench.runner import Assembly, assemble_live, railroad
from tc49.lib.layout import Layout
from tc49.lib.roster import Roster
from tc49.store import AssetStore
from tests.harness import ROOT, railroads

HOST = "127.0.0.1"

TIMEOUT_S = 5.0

PERIOD_S = 0.01
"""The pacer's turn, far shorter than a session's own 0.1s: what these tests
wait on is a socket, and every turn is another look at whether it happened."""

DEVICE_LINK = "tc49/layout/state/device/link/dccex"
POWER_WANTED = "tc49/layout/power_wanted"

TRACK_ON = b"<1>"
TRACK_OFF = b"<0>"


class Station:
    """A command station's end of the port, on loopback.

    One connection, answered with a status line so that the app has heard the
    station *speak* — `device/link` goes `up` on an answer and not on an open
    socket — and everything it is sent kept for the test to read.
    """

    def __init__(self) -> None:
        self._listener = socket.socket()
        self._listener.bind((HOST, 0))
        self._listener.listen(1)
        self.port = int(self._listener.getsockname()[1])
        self._heard = bytearray()
        self._lock = threading.Lock()
        threading.Thread(target=self._serve, name="station", daemon=True).start()

    def _serve(self) -> None:
        try:
            connection, _ = self._listener.accept()
        except OSError:
            return  # closed before anything connected, which is a test ending
        with connection:
            try:
                connection.sendall(b"<p0>")  # answering: the rails are dark
                while True:
                    arrived = connection.recv(4096)
                    if not arrived:
                        return
                    with self._lock:
                        self._heard += arrived
            except OSError:
                return

    def heard(self) -> bytes:
        with self._lock:
            return bytes(self._heard)

    def waits_for(self, message: bytes, limit_s: float = TIMEOUT_S) -> bool:
        """Whether that message has arrived, waiting up to `limit_s` for it:
        the wire between the app writing and this end reading is a thread
        boundary, so arrival is a wait and never a given."""
        deadline = time.monotonic() + limit_s
        while message not in self.heard():
            if time.monotonic() > deadline:
                return False
            time.sleep(0.01)
        return True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._listener.close()


def closed_port() -> int:
    """A port nothing is listening on: a station that is not there."""
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def until(done: Callable[[], bool], limit_s: float = TIMEOUT_S) -> Callable[[], bool]:
    """A `stop` that ends the loop once `done`, or once the test has waited
    long enough — a run that never finishes is a hang and not a failure."""
    deadline = time.monotonic() + limit_s
    return lambda: done() or time.monotonic() > deadline


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


def a_railroad() -> tuple[Layout, Roster]:
    """Some railroad this checkout has: its layout and the stock it owns."""
    return railroad(AssetStore(ROOT), railroads()[0])


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
