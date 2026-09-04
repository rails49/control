"""The translator over one connection, with a socket pair standing in for the
command station.

The connection is injected, so the test holds the station's end of every
attempt the app makes and nothing here needs hardware: the gate is green on a
machine with nothing plugged in, which is the acceptance criterion the rest
of them sit under (#289). What is asserted is the seam — the bytes that go
out, and the two rows that come back on the bus.

The suite has no asyncio plugin, so each test is a coroutine handed to
`asyncio.run`, and what a test waits on is the station's end of the wire: a
message arriving there is the app having acted.
"""

import asyncio
import contextlib
import logging
import socket
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from tc49.dccex.translator import DccEx
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock

TIMEOUT_S = 5.0
QUIET_S = 0.05

# Far longer than any test runs, so a poll never lands in the middle of what
# a test is asserting. The two tests about polling set their own.
NEVER_S = 3600.0

TRACK = "tc49/layout/state/wanted/track"
TRACTION = "tc49/layout/state/wanted/traction"
POINT = "tc49/layout/state/wanted/point"
SIGNAL = "tc49/layout/state/wanted/signal"
FUNCTION = "tc49/layout/state/wanted/function"

DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link/dccex"
DEVICE_POINT = "tc49/layout/state/device/point"


class Station:
    """The command station's end of one connection."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def heard(self, count: int = 1) -> list[bytes]:
        """The next `count` whole messages the app sent, in order."""
        return [
            await asyncio.wait_for(self._reader.readuntil(b">"), TIMEOUT_S)
            for _ in range(count)
        ]

    async def heard_nothing_more(self) -> None:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(self._reader.read(1), QUIET_S)

    def says(self, *messages: bytes) -> None:
        for message in messages:
            self._writer.write(message)

    def hangs_up(self) -> None:
        self._writer.close()


class Port:
    """Where the app connects: one socket pair per attempt, the station's end
    of each kept so the test can drive it."""

    def __init__(self) -> None:
        self.attempts: list[Station] = []
        self._opened = asyncio.Event()

    async def connect(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        app_side, station_side = socket.socketpair()
        reader, writer = await asyncio.open_connection(sock=station_side)
        end = await asyncio.open_connection(sock=app_side)
        # Announced with nothing left to await, so the app runs on from here
        # to the read it waits at before the test wakes: what a test does
        # next is publish, and the link has to be up by then.
        self.attempts.append(Station(reader, writer))
        self._opened.set()
        return end

    async def opened(self, count: int = 1) -> Station:
        """The station's end of the `count`-th attempt, waiting for it."""
        while len(self.attempts) < count:
            self._opened.clear()
            if len(self.attempts) >= count:
                break
            await asyncio.wait_for(self._opened.wait(), TIMEOUT_S)
        return self.attempts[count - 1]


class Tap:
    """Everything published, in delivery order: the trace, as a test reads it."""

    def __init__(self, bus: InProcessBus) -> None:
        self.seen: list[tuple[str, Payload]] = []
        bus.subscribe("tc49/#", self._on_anything)

    def _on_anything(self, topic: str, payload: Payload) -> None:
        self.seen.append((topic, payload))

    def values(self, topic: str) -> list[Payload]:
        return [payload for seen, payload in self.seen if seen == topic]

    def topics(self) -> set[str]:
        return {topic for topic, _ in self.seen}


@contextlib.asynccontextmanager
async def running(
    bus: InProcessBus,
    port: Port,
    poll_s: float = NEVER_S,
    backoff_s: float = 0.005,
    startup: Path | None = None,
) -> AsyncGenerator[DccEx]:
    """The app, constructed on the bus and keeping its link, until the test
    is done with it."""
    app = DccEx(
        bus,
        connect=port.connect,
        startup=startup,
        poll_s=poll_s,
        first_backoff_s=backoff_s,
        max_backoff_s=backoff_s * 4,
    )
    bus.drain()
    keeping = asyncio.create_task(app.run())
    try:
        yield app
    finally:
        keeping.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await keeping


def bus_and_tap() -> tuple[InProcessBus, Tap]:
    bus = InProcessBus(Clock())
    return bus, Tap(bus)


def wanted(bus: InProcessBus, topic: str, address: str, payload: Payload) -> None:
    """One desired value, on the topic its address puts it on."""
    bus.publish(f"{topic}/{address}" if address else topic, payload)


# -- what a connection is handed -----------------------------------------


def test_the_retained_desired_state_is_applied_on_connect() -> None:
    asyncio.run(_retained_desired_state_is_applied_on_connect())


async def _retained_desired_state_is_applied_on_connect() -> None:
    """Three retained values waiting, and connecting sends exactly those
    three: the desired values are the whole picture, so there is no handshake
    and no session state to agree first."""
    bus, _ = bus_and_tap()
    wanted(bus, TRACTION, "460", {"addr": "460", "speed": 0.5})
    wanted(bus, POINT, "5", {"addr": "5", "position": "thrown"})
    wanted(bus, SIGNAL, "40", {"addr": "40", "aspect": "clear"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        assert await station.heard(3) == [b"<t 460 63 1>", b"<a 2 0 1>", b"<A 40 2>"]
        await station.heard_nothing_more()


def test_the_track_is_applied_before_everything_else() -> None:
    asyncio.run(_track_is_applied_before_everything_else())


async def _track_is_applied_before_everything_else() -> None:
    """Power reaches the rails before a turnout is asked to throw, whatever
    order the topics were first heard in."""
    bus, _ = bus_and_tap()
    wanted(bus, POINT, "5", {"addr": "5", "position": "closed"})
    wanted(bus, TRACK, "", {"power": "on"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        assert await station.heard(2) == [b"<1>", b"<a 2 0 0>"]


def test_a_value_that_arrives_while_the_link_is_down_waits_for_it() -> None:
    asyncio.run(_value_that_arrives_while_the_link_is_down_waits_for_it())


async def _value_that_arrives_while_the_link_is_down_waits_for_it() -> None:
    """A command is honoured now or ignored, and the desired value is what
    survives: it is applied on the next connect, the way the retained value
    is at startup."""
    bus, _ = bus_and_tap()
    port = Port()
    app = DccEx(bus, connect=port.connect, poll_s=NEVER_S)
    bus.drain()
    wanted(bus, TRACTION, "3", {"addr": "3", "speed": -1.0})
    bus.drain()
    keeping = asyncio.create_task(app.run())
    try:
        station = await port.opened()
        assert await station.heard(1) == [b"<t 3 126 0>"]
    finally:
        keeping.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await keeping


# -- what this app answers for -------------------------------------------


def test_every_point_address_is_acted_on() -> None:
    asyncio.run(_every_point_address_is_acted_on())


async def _every_point_address_is_acted_on() -> None:
    """An address names no system (ADR-0059): it is the string the drawing
    carries and the hardware answers to, so `5` is a turnout this station
    throws and there is no level in front of it to look at."""
    bus, _ = bus_and_tap()
    wanted(bus, POINT, "5", {"addr": "5", "position": "thrown"})
    wanted(bus, SIGNAL, "40", {"addr": "40", "aspect": "clear"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        assert await station.heard(2) == [b"<a 2 0 1>", b"<A 40 2>"]
        await station.heard_nothing_more()


def test_an_address_this_station_has_no_packet_for_sends_nothing() -> None:
    asyncio.run(_address_this_station_has_no_packet_for_sends_nothing())


async def _address_this_station_has_no_packet_for_sends_nothing() -> None:
    """No ownership table: the app acts on every address it hears and the
    packet is where one it cannot express falls away, so an address nothing
    answers to does no harm, as a packet nobody picks up does."""
    bus, _ = bus_and_tap()
    wanted(bus, POINT, "LT3", {"addr": "LT3", "position": "thrown"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        await station.heard_nothing_more()


def test_a_traction_address_is_bare_and_is_this_apps() -> None:
    asyncio.run(_traction_address_is_bare_and_is_this_apps())


async def _traction_address_is_bare_and_is_this_apps() -> None:
    """A decoder answers to the number it was programmed with whoever sends
    the packet, so every bare address is acted on — and one of two levels is
    a function's, the decoder and the function number, and not a traction
    address at all."""
    bus, _ = bus_and_tap()
    wanted(bus, TRACTION, "3/2", {"addr": "3/2", "speed": 1.0})
    wanted(bus, FUNCTION, "3/2", {"addr": "3", "function": "2", "value": "on"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        assert await station.heard(1) == [b"<F 3 2 1>"]
        await station.heard_nothing_more()


def test_a_frame_that_cannot_be_read_is_dropped() -> None:
    asyncio.run(_frame_that_cannot_be_read_is_dropped())


async def _frame_that_cannot_be_read_is_dropped() -> None:
    """This app answers nothing, so a frame it cannot read is dropped and
    raises nothing — and is not remembered either, so a connect does not
    replay something that sent nothing when it arrived."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, TRACTION, "3", {"addr": "3", "speed": "fast"})
        wanted(bus, TRACTION, "4", {"addr": "4", "speed": True})
        wanted(bus, POINT, "5", {"addr": "5"})
        wanted(bus, TRACK, "", {"power": "maybe"})
        bus.drain()
        await station.heard_nothing_more()


# -- the stop, and clearing it -------------------------------------------


def test_clearing_a_stop_zeroes_every_locomotive_before_the_release() -> None:
    asyncio.run(_clearing_a_stop_zeroes_every_locomotive_before_the_release())


async def _clearing_a_stop_zeroes_every_locomotive_before_the_release() -> None:
    """The named test: under the lock the station keeps every locomotive's
    pre-lock speed and resumes it on release, so a bare release restarts
    every train at the speed it was doing when somebody hit stop. Nothing in
    the software is in the path of those packets, which is what makes the
    byte order the assertion.
    """
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, TRACTION, "3", {"addr": "3", "speed": 0.5})
        wanted(bus, TRACTION, "7", {"addr": "7", "speed": -0.25})
        bus.drain()
        assert await station.heard(2) == [b"<t 3 63 1>", b"<t 7 32 0>"]

        wanted(bus, TRACK, "", {"power": "stopped"})
        bus.drain()
        assert await station.heard(1) == [b"<!P>"]
        station.says(b"<!PAUSED>")
        await asyncio.sleep(QUIET_S)

        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(4) == [
            b"<t 3 0 1>",
            b"<t 7 0 1>",
            b"<!R>",
            b"<1>",
        ]


def test_an_on_with_no_stop_behind_it_releases_nothing() -> None:
    asyncio.run(_an_on_with_no_stop_behind_it_releases_nothing())


async def _an_on_with_no_stop_behind_it_releases_nothing() -> None:
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, TRACTION, "3", {"addr": "3", "speed": 0.5})
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(2) == [b"<t 3 63 1>", b"<1>"]


def test_a_stop_this_app_commanded_is_released_before_the_station_answers() -> None:
    asyncio.run(_stop_this_app_commanded_is_released_before_the_station_answers())


async def _stop_this_app_commanded_is_released_before_the_station_answers() -> None:
    """The lock and its broadcast are a round trip apart, and an `on` inside
    that window must still send the zeros: releasing without them is the
    failure that matters, and an extra set of zeros stops trains that were
    already standing."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, TRACTION, "3", {"addr": "3", "speed": 1.0})
        wanted(bus, TRACK, "", {"power": "stopped"})
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(5) == [
            b"<t 3 126 1>",
            b"<!P>",
            b"<t 3 0 1>",
            b"<!R>",
            b"<1>",
        ]


# -- the startup file ----------------------------------------------------

FILE = """\
# /etc/tc49/dccex-startup.txt — trip currents for the four districts

<= A LIMIT 3000>
<= B LIMIT 3000>
<= C LIMIT 1500>
"""

SENT = [b"<= A LIMIT 3000>", b"<= B LIMIT 3000>", b"<= C LIMIT 1500>"]


def written(tmp_path: Path) -> Path:
    path = tmp_path / "dccex-startup.txt"
    path.write_text(FILE)
    return path


def test_powering_on_sends_the_track_on_and_then_the_file(tmp_path: Path) -> None:
    asyncio.run(_powering_on_sends_the_track_on_and_then_the_file(written(tmp_path)))


async def _powering_on_sends_the_track_on_and_then_the_file(startup: Path) -> None:
    """The order is the whole of it: the districts take their trip currents
    once there is power to trip. The comment and the blank line are a
    person's layout of the file and are not commands, so the station never
    sees them."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port, startup=startup):
        station = await port.opened()
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(4) == [b"<1>"] + SENT
        await station.heard_nothing_more()


def test_a_second_on_with_no_off_between_sends_the_file_once(tmp_path: Path) -> None:
    asyncio.run(_second_on_with_no_off_between_sends_the_file_once(written(tmp_path)))


async def _second_on_with_no_off_between_sends_the_file_once(startup: Path) -> None:
    """It is a transition and not a level: an `on` over rails that are
    already live asks the station for nothing new, and an `off` and back is
    what makes it a fresh power-on again."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port, startup=startup):
        station = await port.opened()
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(4) == [b"<1>"] + SENT

        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(1) == [b"<1>"]
        await station.heard_nothing_more()

        wanted(bus, TRACK, "", {"power": "off"})
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(5) == [b"<0>", b"<1>"] + SENT


def test_clearing_a_stop_powers_on_and_sends_the_file(tmp_path: Path) -> None:
    asyncio.run(_clearing_a_stop_powers_on_and_sends_the_file(written(tmp_path)))


async def _clearing_a_stop_powers_on_and_sends_the_file(startup: Path) -> None:
    """`stopped` is not `on`, so the `on` that clears it is a transition into
    `on` like any other and the file follows the track-on command — behind
    the zeros and the release, which come first whatever else the transition
    carries. The rails stayed live under the lock and the station has the
    values already; sending them twice sets them to what they were."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port, startup=startup):
        station = await port.opened()
        wanted(bus, TRACTION, "3", {"addr": "3", "speed": 0.5})
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(5) == [b"<t 3 63 1>", b"<1>"] + SENT

        wanted(bus, TRACK, "", {"power": "stopped"})
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        cleared = [b"<!P>", b"<t 3 0 1>", b"<!R>", b"<1>"]
        assert await station.heard(7) == cleared + SENT


def test_a_new_link_powers_on_from_the_beginning(tmp_path: Path) -> None:
    asyncio.run(_new_link_powers_on_from_the_beginning(written(tmp_path)))


async def _new_link_powers_on_from_the_beginning(startup: Path) -> None:
    """The station on the far end of the next link may be one that has just
    restarted, and one that has forgotten its trip currents runs at the
    firmware's default until somebody notices. So the memory goes with the
    link and the retained `on` sends the file again."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port, startup=startup):
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        first = await port.opened()
        assert await first.heard(4) == [b"<1>"] + SENT

        first.hangs_up()
        second = await port.opened(2)
        assert await second.heard(4) == [b"<1>"] + SENT


def test_with_no_startup_file_the_byte_stream_is_what_it_was() -> None:
    asyncio.run(_with_no_startup_file_the_byte_stream_is_what_it_was())


async def _with_no_startup_file_the_byte_stream_is_what_it_was() -> None:
    """The flag is optional and its absence is not a behaviour: what goes out
    is the track-on command and nothing after it."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, TRACK, "", {"power": "on"})
        bus.drain()
        assert await station.heard(1) == [b"<1>"]
        await station.heard_nothing_more()


def test_a_file_that_cannot_be_read_is_logged_and_the_railroad_powers_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    asyncio.run(
        _file_that_cannot_be_read_is_logged_and_the_railroad_powers_on(
            tmp_path / "not-there.txt", caplog
        )
    )


async def _file_that_cannot_be_read_is_logged_and_the_railroad_powers_on(
    missing: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A railroad coming up at the firmware's low default trips early, which
    is safe and visible; one that refuses to come up over a configuration
    file is neither (ADR-0050). The person who has to fix it reads the
    log."""
    bus, _ = bus_and_tap()
    port = Port()
    with caplog.at_level(logging.WARNING):
        async with running(bus, port, startup=missing):
            station = await port.opened()
            wanted(bus, TRACK, "", {"power": "on"})
            bus.drain()
            assert await station.heard(1) == [b"<1>"]
            await station.heard_nothing_more()
    assert "not-there.txt" in caplog.text


# -- what the hardware reports -------------------------------------------


def test_the_link_is_down_before_anything_is_connected() -> None:
    """A client joining now is served a value rather than left to read one
    out of an absence, and what is true is that nothing has been reached."""
    bus, tap = bus_and_tap()
    DccEx(bus)
    bus.drain()
    assert [value["link"] for value in tap.values(DEVICE_LINK)] == ["down"]
    assert [value["power"] for value in tap.values(DEVICE_TRACK)] == ["off"]


def test_the_link_row_is_keyed_by_the_id_the_app_is_started_with() -> None:
    """The id is whatever the publisher calls itself and appears in no
    drawing and no list of ours, so two of these on one railroad each keep
    their own row and neither erases the other (ADR-0059). The package's name
    is the default and a value, not a contract."""
    bus, tap = bus_and_tap()
    DccEx(bus, id="shed")
    bus.drain()
    said = tap.values("tc49/layout/state/device/link/shed")
    assert [value["link"] for value in said] == ["down"]
    assert [value["id"] for value in said] == ["shed"]
    assert not tap.values(DEVICE_LINK)


def test_the_supply_says_why_it_is_off_while_the_station_is_unreachable() -> None:
    asyncio.run(_supply_says_why_it_is_off_while_the_station_is_unreachable())


async def _supply_says_why_it_is_off_while_the_station_is_unreachable() -> None:
    """The link row's own words, said again on the supply, so a person
    reading why the railroad is dark reads it off the supply itself rather
    than off a second row (ADR-0059). The reason goes when the station
    answers: what the row says then is the station's own word."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        bus.drain()
        dark = tap.values(DEVICE_TRACK)[-1]
        assert dark["power"] == "off"
        assert dark["reason"] == tap.values(DEVICE_LINK)[-1]["detail"]

        station = await port.opened()
        station.says(b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        lit = tap.values(DEVICE_TRACK)[-1]
        assert lit["power"] == "on"
        assert "reason" not in lit


def test_a_dropped_link_is_published_and_so_is_the_reconnect() -> None:
    asyncio.run(_dropped_link_is_published_and_so_is_the_reconnect())


async def _dropped_link_is_published_and_so_is_the_reconnect() -> None:
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        first = await port.opened()
        first.says(b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["link"] for value in tap.values(DEVICE_LINK)] == ["down", "up"]

        first.hangs_up()
        second = await port.opened(2)
        bus.drain()
        assert [value["link"] for value in tap.values(DEVICE_LINK)] == [
            "down",
            "up",
            "down",
        ]

        second.says(b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["link"] for value in tap.values(DEVICE_LINK)][-1] == "up"


def test_the_link_is_up_only_once_the_station_has_answered() -> None:
    asyncio.run(_link_is_up_only_once_the_station_has_answered())


async def _link_is_up_only_once_the_station_has_answered() -> None:
    """An open socket is not a command station. `station` accepts a client
    with the serial device unplugged, and a link nobody has answered on is
    not one a view may call good."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        await port.opened()
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["link"] for value in tap.values(DEVICE_LINK)] == ["down"]


def test_a_status_reporting_an_overload_reads_the_track_off() -> None:
    asyncio.run(_status_reporting_an_overload_reads_the_track_off())


async def _status_reporting_an_overload_reads_the_track_off() -> None:
    """A district that trips is not broadcast, so the poll is what finds it —
    and the digit is `0` for a track that has tripped, which is the whole of
    what the fold needs."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        station.says(b"<p1 A>", b"<p1 B>", b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)] == ["off", "on"]

        station.says(b"<p0 A>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)] == [
            "off",
            "on",
            "off",
        ]


def test_the_lock_the_station_reports_reads_stopped() -> None:
    asyncio.run(_lock_the_station_reports_reads_stopped())


async def _lock_the_station_reports_reads_stopped() -> None:
    """`stopped` is every locomotive told to stand with the track still live,
    and it reaches the bus from what the station says rather than from having
    commanded it: a railroad that read back its own command would be an echo
    and not an observation."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        station.says(b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)] == ["off", "on"]

        wanted(bus, TRACK, "", {"power": "stopped"})
        bus.drain()
        assert await station.heard(1) == [b"<!P>"]
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)] == ["off", "on"]

        station.says(b"<!PAUSED>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)][-1] == "stopped"


def test_a_dropped_link_takes_the_power_reading_with_it() -> None:
    asyncio.run(_dropped_link_takes_the_power_reading_with_it())


async def _dropped_link_takes_the_power_reading_with_it() -> None:
    """What cannot be read is not what was last read: a district that tripped
    while the link was down would otherwise stand as an observation nobody
    made."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        station.says(b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)][-1] == "on"

        station.hangs_up()
        await port.opened(2)
        bus.drain()
        assert [value["power"] for value in tap.values(DEVICE_TRACK)][-1] == "off"


def test_no_position_is_ever_observed() -> None:
    asyncio.run(_no_position_is_ever_observed())


async def _no_position_is_ever_observed() -> None:
    """This railroad's turnouts have no feedback and the station's answer to
    a throw is one it faked, so the row stays empty however many turnouts are
    thrown: a faked observation is worse than silence."""
    bus, tap = bus_and_tap()
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        wanted(bus, POINT, "5", {"addr": "5", "position": "thrown"})
        bus.drain()
        assert await station.heard(1) == [b"<a 2 0 1>"]
        station.says(b"<H 1 1>", b"<p1>")
        await asyncio.sleep(QUIET_S)
        bus.drain()
    assert not [topic for topic in tap.topics() if topic.startswith(DEVICE_POINT)]
    assert tap.topics() >= {DEVICE_TRACK, DEVICE_LINK}


# -- the poll -------------------------------------------------------------


def test_the_poll_asks_for_the_status_and_the_lock() -> None:
    asyncio.run(_poll_asks_for_the_status_and_the_lock())


async def _poll_asks_for_the_status_and_the_lock() -> None:
    """The status because an overload is not broadcast, and the lock because
    it is queryable — which is what lets a restart read a latched stop back
    rather than remember it."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port, poll_s=0.01):
        station = await port.opened()
        assert await station.heard(2) == [b"<s>", b"<!Q>"]
        assert await station.heard(2) == [b"<s>", b"<!Q>"]


# -- standing the railroad down -------------------------------------------


def test_a_clean_exit_zeroes_every_locomotive_and_switches_the_track_off() -> None:
    asyncio.run(_clean_exit_zeroes_every_locomotive_and_switches_the_track_off())


async def _clean_exit_zeroes_every_locomotive_and_switches_the_track_off() -> None:
    """The process ending is not by itself an instruction to the railroad, so
    the exit is one: zero to every locomotive commanded, in the order they
    were, and only then the power (#314). Cutting the supply first would
    leave the speeds in the station's slots for the next power-on to
    resume."""
    bus, _ = bus_and_tap()
    port = Port()
    async with running(bus, port) as app:
        station = await port.opened()
        wanted(bus, TRACK, "", {"power": "on"})
        wanted(bus, TRACTION, "10", {"addr": "10", "speed": 0.5})
        wanted(bus, TRACTION, "11", {"addr": "11", "speed": -1.0})
        bus.drain()
        assert await station.heard(3) == [b"<1>", b"<t 10 63 1>", b"<t 11 126 0>"]

        await app.shutdown()
        assert await station.heard(3) == [b"<t 10 0 1>", b"<t 11 0 1>", b"<0>"]


def test_standing_down_a_railroad_that_was_never_reached_sends_nothing() -> None:
    asyncio.run(_standing_down_a_railroad_that_was_never_reached_sends_nothing())


async def _standing_down_a_railroad_that_was_never_reached_sends_nothing() -> None:
    """A station the link never opened to is one this app was not driving.
    `_send` drops rather than queues, so the exit is silent rather than a
    backlog waiting for a connection that is not coming."""
    bus, _ = bus_and_tap()
    app = DccEx(bus, connect=Port().connect)
    bus.drain()
    await app.shutdown()  # no link, no writer, and nothing raised
