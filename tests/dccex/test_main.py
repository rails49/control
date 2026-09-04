"""The translator as its own process: what it takes for it to come up alone.

Against a real broker and a real listener on real sockets, because that is
what is under test — an app started against nothing, in whatever order the
machine brings the two up (ADR-0059, decision 5). The station is reached by
**address** here rather than by the injected connection `test_translator.py`
drives: an address is what `--station` gives and opening it is what this
command line has to get right. Nothing needs hardware, which is the rule the
whole gate sits under.

There is no store here and no fixture for one, and no railroad's name either:
hardware needs no layout, so this app reads no documents and the order the
scheduler's and dispatcher's suites exercise does not exist for it.

The loop runs on a thread here and is ended with the event `serve` takes; in
the deployment it is the main thread, asyncio owns it, and a signal ends it.
What a test waits on is the station's end of the wire — a message arriving
there is the app having drained the broker's queue on the loop thread and
written to the socket.
"""

import socket
import threading
import time
from collections.abc import Iterator

import pytest

from tc49.dccex.__main__ import serve
from tc49.lib.bus import Payload
from tc49.lib.mqtt import MqttBus
from tests.brokers import Broker, drained, free_port, settle

WANTED_TRACK = "tc49/layout/state/wanted/track"
WANTED_TRACTION = "tc49/layout/state/wanted/traction/10"
DEVICE_TRACK = "tc49/layout/state/device/track"
DEVICE_LINK = "tc49/layout/state/device/link"

TRACK_ON = b"<1>"
TRACK_OFF = b"<0>"
HALF_SPEED_10 = b"<t 10 63 1>"
HALTED_10 = b"<t 10 0 1>"

TIMEOUT_S = 5.0

BACKOFF_S = 0.01
"""The retry the suite gives the app, where the deployment starts at half a
second and doubles to eight: a station that appears three lines after the app
went looking for it is what these tests wait on, and waiting out a deployed
backoff to see it would be waiting on nothing else."""

RETAINED_S = 0.1
"""How long the app waits for the broker's retained desired rows before it
opens the link, where the deployment gives them a second. Everything here is
on loopback and already queued by the time the subscription is acknowledged,
so the window is what a test spends and not what it proves."""


class Station:
    """A command station's end of the port, on loopback.

    Bound when `opens()` is called and not before, so a test can have the app
    go looking for a mirror that is not up yet — the port is taken from the
    same place a broker's is, and held only by having been asked for.

    One connection, answered with a status line so that the app has heard the
    station *speak* — `device/link` goes `up` on an answer and not on an open
    socket — and everything it is sent kept for the test to read.
    """

    def __init__(self) -> None:
        self.port = free_port()
        self._heard = bytearray()
        self._lock = threading.Lock()
        self._listener: socket.socket | None = None

    def opens(self) -> None:
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen(1)
        self._listener = listener
        threading.Thread(target=self._serve, args=(listener,), daemon=True).start()

    def _serve(self, listener: socket.socket) -> None:
        try:
            connection, _ = listener.accept()
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

    def close(self) -> None:
        if self._listener is not None:
            self._listener.close()


@pytest.fixture
def station() -> Iterator[Station]:
    serving = Station()
    try:
        yield serving
    finally:
        serving.close()


class App:
    """The translator running as `python -m tc49.dccex` runs it, on a thread
    so the test can watch the bus and the port while it is up.

    Its client is made when it starts and not before, so a test can stop the
    broker first and have the app go looking for one that is not there.
    """

    def __init__(self, broker: Broker, station: Station, id: str = "dccex") -> None:
        self.id = id
        self._broker = broker
        self._station = station
        self._bus: MqttBus | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.up = threading.Event()

    def start(self) -> None:
        self._bus = MqttBus(port=self._broker.port)
        self._thread = threading.Thread(
            target=serve,
            args=(self._bus, ("127.0.0.1", self._station.port), self._stop),
            kwargs={
                "id": self.id,
                "period_s": 0.01,
                "retained_s": RETAINED_S,
                "first_backoff_s": BACKOFF_S,
                "max_backoff_s": BACKOFF_S,
                "log": self._log,
            },
            daemon=True,
        )
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._bus is not None:
            self._bus.close()

    def _log(self, line: str) -> None:
        """The app's log, dropped except for the one line that says it is on
        the broker and looping. What it says is for a person watching a
        container; the suite asserts on the bus and on the wire."""
        if line.startswith("up as"):
            self.up.set()


@pytest.fixture
def app(broker: Broker, station: Station) -> Iterator[App]:
    running = App(broker, station)
    try:
        yield running
    finally:
        running.stop()


def watching(broker: Broker) -> tuple[MqttBus, list[tuple[str, Payload]]]:
    """Another client of the same broker, and everything it hears: the app is
    only visible where anything else on the railroad sees it."""
    bus = MqttBus(port=broker.port)
    assert bus.wait_connected(), "the witness never reached the broker"
    heard: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: heard.append((topic, payload)))
    return bus, heard


def rows(heard: list[tuple[str, Payload]], topic: str) -> list[Payload]:
    """What arrived on one topic, in the order it arrived."""
    return [payload for said, payload in heard if said == topic]


def wanting(broker: Broker) -> MqttBus:
    """A client publishing the desired rows `layout` owns. Another process
    here, which is what the broker makes of the seam #289 states in one:
    nothing says who published, and nothing here asks (rule 4)."""
    bus = MqttBus(port=broker.port)
    assert bus.wait_connected(), "the writer never reached the broker"
    return bus


def test_a_cold_start_publishes_the_apps_own_rows(
    broker: Broker, station: Station, app: App
) -> None:
    """Against an empty broker with no station on the other end: the two rows
    this app opens with, waiting for whoever subscribes next (ADR-0059).

    The link it cannot make, keyed by the id it was started with (decision 7),
    and a supply that is off carrying that same sentence as its reason — a
    person reading why the railroad is dark reads it off the supply rather
    than off a second row. What cannot be read may not be called good.
    """
    witness, heard = watching(broker)
    app.start()

    link = f"{DEVICE_LINK}/{app.id}"
    assert drained(witness, lambda: rows(heard, DEVICE_TRACK) != []), "it said nothing"
    assert rows(heard, link)[-1]["link"] == "down"
    assert rows(heard, link)[-1]["id"] == app.id
    assert rows(heard, DEVICE_TRACK)[-1]["power"] == "off"
    assert rows(heard, DEVICE_TRACK)[-1]["reason"] != ""
    assert app.running, "the app stopped on its own"
    witness.close()


def test_its_link_row_is_keyed_by_the_id_it_was_started_with(
    broker: Broker, station: Station
) -> None:
    """`--id` is the whole of what a second translator on one railroad needs:
    the row is keyed by it, so the second's `up` does not erase the first's
    `down` (ADR-0059, decision 7). A value and not a contract — it appears in
    no drawing and no list of ours."""
    named = App(broker, station, id="north-yard")
    witness, heard = watching(broker)
    try:
        named.start()
        assert drained(
            witness, lambda: rows(heard, f"{DEVICE_LINK}/north-yard") != []
        ), "nothing was published under the id it was given"
        assert rows(heard, f"{DEVICE_LINK}/dccex") == []
    finally:
        named.stop()
        witness.close()


def test_it_applies_the_desired_state_it_finds_on_the_broker(
    broker: Broker, station: Station, app: App
) -> None:
    """The loop is what makes the app an app, and this is the whole path:
    `layout`'s retained desired rows are on the broker before this process
    exists, the client's network thread queues them, the drain hands them to
    the asyncio loop, and the loop writes them to the station.

    The track goes first whatever order they were published in, so nothing is
    commanded onto dead rails.
    """
    hand = wanting(broker)
    hand.publish(WANTED_TRACTION, {"addr": "10", "speed": 0.5})
    hand.publish(WANTED_TRACK, {"power": "on"})
    station.opens()
    app.start()

    assert station.waits_for(HALF_SPEED_10), "the locomotive was never commanded"
    heard = station.heard()
    assert heard.index(TRACK_ON) < heard.index(
        HALF_SPEED_10
    ), "commanded onto dead rails"
    assert app.running, "the app stopped on its own"
    hand.close()


def test_it_comes_up_against_a_station_that_is_not_there_yet(
    broker: Broker, station: Station, app: App
) -> None:
    """The order nothing forbids: no `depends_on` anywhere, so the app is
    started before the mirror it drives and retries rather than exiting, as
    the apps that read documents retry the store (ADR-0059, decision 5).

    A desired value that arrives while the link is down is remembered and
    applied on the connect, which is the same thing that happens to the
    retained one at startup.
    """
    witness, heard = watching(broker)
    app.start()
    assert app.up.wait(10), "it never came up"
    hand = wanting(broker)
    hand.publish(WANTED_TRACK, {"power": "on"})
    assert drained(
        witness, lambda: rows(heard, f"{DEVICE_LINK}/{app.id}") != []
    ), "it never said anything about the link it could not make"
    assert rows(heard, f"{DEVICE_LINK}/{app.id}")[-1]["link"] == "down"

    station.opens()

    assert station.waits_for(TRACK_ON), "the link was never made"
    assert drained(
        witness, lambda: rows(heard, f"{DEVICE_LINK}/{app.id}")[-1]["link"] == "up"
    ), "the link came up and the row did not say so"
    hand.close()
    witness.close()


def test_it_comes_up_against_a_broker_that_is_not_there_yet(
    broker: Broker, station: Station, app: App
) -> None:
    """The other order nothing forbids. The two opening rows are publishes,
    and a publish made to a broker that is not there is dropped rather than
    queued (ADR-0050), so the app waits for the broker before it is built at
    all — and the station is not touched meanwhile."""
    broker.stop()
    station.opens()
    app.start()
    assert not app.up.wait(1), "it said it was up with no broker to be up on"
    assert app.running, "the app gave up on a broker that was not up yet"
    assert station.heard() == b"", "it drove the station with nowhere to report it"

    assert broker.start()

    # Reconnected on the client's own backoff, whose first step is a second.
    assert app.up.wait(30), "it never came up once the broker was there"
    witness, heard = watching(broker)
    assert drained(
        witness, lambda: rows(heard, f"{DEVICE_LINK}/{app.id}") != []
    ), "it never published its own rows"
    witness.close()


def test_it_stands_the_railroad_down_on_its_way_out(
    broker: Broker, station: Station, app: App
) -> None:
    """The process ending is not by itself an instruction to the railroad: the
    station goes on running whatever it was last told, so every locomotive this
    app has commanded is sent zero and only then is the track cut.

    The zeros come first because the station keeps a speed per locomotive and
    resumes it, so cutting the supply over a held speed only postpones the
    motion.
    """
    hand = wanting(broker)
    hand.publish(WANTED_TRACK, {"power": "on"})
    hand.publish(WANTED_TRACTION, {"addr": "10", "speed": 0.5})
    station.opens()
    app.start()
    assert station.waits_for(HALF_SPEED_10), "the locomotive was never commanded"

    app.stop()

    assert station.waits_for(TRACK_OFF), "the rails were left live"
    heard = station.heard()
    assert heard.index(HALTED_10) < heard.index(TRACK_OFF), "cut over a held speed"
    hand.close()


def test_a_desired_value_it_cannot_read_leaves_it_running(
    broker: Broker, station: Station, app: App
) -> None:
    """A frame claiming to be a desired value is one more thing anyone can
    publish, and on the broker whoever publishes it is another process: a
    translator that raised on one would be taken down from outside
    (SYSTEM.md, rule 4, #289).

    Each is dropped whole — not remembered either, so a connect does not
    replay something that sent nothing when it arrived — and the honest value
    after them still reaches the station.

    Published one after another while the app is up, rather than left on the
    broker: a state topic holds the last value, so three retained frames on
    one row would be one frame by the time this process subscribed.
    """
    witness, _ = watching(broker)
    station.opens()
    app.start()
    assert station.waits_for(b"<s>"), "the link was never made"

    hand = wanting(broker)
    for payload in (
        {"addr": "10"},  # a locomotive and no speed
        {"addr": "10", "speed": "fast"},
        {"addr": "10", "speed": True},  # a boolean is not a speed
    ):
        hand.publish(WANTED_TRACTION, payload)
    settle(witness)
    assert b"<t 10" not in station.heard(), "something unreadable was commanded"

    hand.publish(WANTED_TRACTION, {"addr": "10", "speed": 0.5})

    assert station.waits_for(HALF_SPEED_10), "the honest value was dropped too"
    assert app.running, "a frame from another process took the translator down"
    hand.close()
    witness.close()
