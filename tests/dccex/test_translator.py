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
import socket
from collections.abc import AsyncGenerator

import pytest

from tc49.dccex.translator import DccEx
from tc49.lib.bus import Bus, Payload
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

    def __init__(self, bus: Bus) -> None:
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
    bus: Bus, port: Port, poll_s: float = NEVER_S, backoff_s: float = 0.005
) -> AsyncGenerator[DccEx]:
    """The app, constructed on the bus and keeping its link, until the test
    is done with it."""
    app = DccEx(
        bus,
        connect=port.connect,
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


def bus_and_tap() -> tuple[Bus, Tap]:
    bus = Bus(Clock())
    return bus, Tap(bus)


def wanted(bus: Bus, topic: str, address: str, payload: Payload) -> None:
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
    wanted(bus, POINT, "dccex/5", {"addr": "dccex/5", "position": "thrown"})
    wanted(bus, SIGNAL, "dccex/40", {"addr": "dccex/40", "aspect": "clear"})
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
    wanted(bus, POINT, "dccex/5", {"addr": "dccex/5", "position": "closed"})
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


def test_a_point_naming_another_system_sends_nothing() -> None:
    asyncio.run(_point_naming_another_system_sends_nothing())


async def _point_naming_another_system_sends_nothing() -> None:
    """No ownership table: this app recognises its own addresses and an
    address nothing answers to does no harm, as a packet nobody picks up
    does."""
    bus, _ = bus_and_tap()
    wanted(bus, POINT, "jmri/LT3", {"addr": "jmri/LT3", "position": "thrown"})
    port = Port()
    async with running(bus, port):
        station = await port.opened()
        await station.heard_nothing_more()


def test_a_traction_address_is_bare_and_is_this_apps() -> None:
    asyncio.run(_traction_address_is_bare_and_is_this_apps())


async def _traction_address_is_bare_and_is_this_apps() -> None:
    """A decoder answers to the number it was programmed with whoever sends
    the packet, and traction cannot be split across systems, so every bare
    address is acted on — and one wearing a system is not a traction
    address at all."""
    bus, _ = bus_and_tap()
    wanted(bus, TRACTION, "dccex/3", {"addr": "dccex/3", "speed": 1.0})
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
        wanted(bus, POINT, "dccex/5", {"addr": "dccex/5"})
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


# -- what the hardware reports -------------------------------------------


def test_the_link_is_down_before_anything_is_connected() -> None:
    """A client joining now is served a value rather than left to read one
    out of an absence, and what is true is that nothing has been reached."""
    bus, tap = bus_and_tap()
    DccEx(bus)
    bus.drain()
    assert [value["link"] for value in tap.values(DEVICE_LINK)] == ["down"]
    assert [value["power"] for value in tap.values(DEVICE_TRACK)] == ["off"]


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
        wanted(bus, POINT, "dccex/5", {"addr": "dccex/5", "position": "thrown"})
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
