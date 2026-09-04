"""The layout interface as its own process: what it takes for it to come up
alone.

Against a real broker and a real store on real sockets, because that is what
is under test — an app started against nothing, in whatever order the machine
brings the two up (ADR-0059, decision 5). The loop itself runs on a thread
here and is ended with the event `serve` takes; in the deployment it is the
main thread and a signal ends it.

The railroad is `crossover-yard`, off the store, where the rest of this suite
draws its own: what is under test here is the process, and a process reads the
documents an installation holds. Time is not driven either — the loop is what
advances the clock, so a level settles by seconds passing, which is the one
thing about this app that no other app's command line has to do.
"""

import shutil
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest

from tc49.layout.__main__ import serve
from tc49.layout.interface import (
    BLOCK_OCCUPIED,
    DEVICE_SENSOR,
    MODE,
    POWER,
    POWER_WANTED,
    RAILROAD,
    WANTED_TRACK,
    WANTED_TRACTION,
)
from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.mqtt import MqttBus
from tc49.store.server import make_server
from tests.brokers import Broker, drained, free_port, settle, until
from tests.harness import ASSETS, catalogued

NAME = "crossover-yard"
END = "up_w.A"
BLOCK = "up_w"
TRACTION = f"{WANTED_TRACTION}/3"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as the store on the layout
    box holds one: a drawing, a roster and the catalogue its cars name."""
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    for suffix in ("drawing", "roster"):
        shutil.copy(
            ASSETS / "layouts" / f"{NAME}.{suffix}.yaml",
            tmp_path / "layouts" / f"{NAME}.{suffix}.yaml",
        )
    return tmp_path


class Store:
    """That store, served on a port of its own — startable after the app has
    already gone looking for it, which is the order nothing here forbids."""

    def __init__(self, root: Path) -> None:
        self.port = free_port()
        self._root = root
        self._thread: threading.Thread | None = None
        self._server: HTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        server = make_server(self._root, self.port)
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


@pytest.fixture
def store(root: Path) -> Iterator[Store]:
    serving = Store(root)
    try:
        yield serving
    finally:
        serving.stop()


class App:
    """The layout interface running as `python -m tc49.layout` runs it, on a
    thread so the test can watch the bus while it is up."""

    def __init__(self, broker: Broker, store: Store) -> None:
        self.bus = MqttBus(port=broker.port)
        self._documents = Documents(
            store.url, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=serve,
            args=(self.bus, self._documents, NAME, self._stop, 0.01),
            kwargs={"log": quiet},
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        self.bus.close()


@pytest.fixture
def app(broker: Broker, store: Store) -> Iterator[App]:
    running = App(broker, store)
    try:
        yield running
    finally:
        running.stop()


def quiet(line: str) -> None:
    """The app's log and the store client's, dropped: what they say is for a
    person watching a container, and the suite asserts on the bus."""


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


def test_a_cold_start_publishes_the_apps_own_rows(
    broker: Broker, store: Store, app: App
) -> None:
    """Against an empty broker with nothing else running: the four rows this
    app opens with, waiting for whoever subscribes next (ADR-0059).

    Which railroad this is, and then a railroad that is dark and has nobody's
    hand on a throttle — the state a person turns on from (ADR-0051), and the
    one every binding of the interface comes up in.
    """
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, MODE) != []), "it published nothing"
    assert rows(heard, RAILROAD)[-1]["name"] == NAME
    assert rows(heard, WANTED_TRACK)[-1]["power"] == "off"
    assert rows(heard, POWER)[-1]["power"] == "off"
    assert rows(heard, MODE)[-1]["modes"] == {}
    assert app.running, "the app stopped on its own"
    witness.close()


def test_it_comes_up_against_a_store_that_is_not_there_yet(
    broker: Broker, store: Store, app: App
) -> None:
    """The order nothing forbids: no `depends_on` anywhere, so the app is
    started before the store it reads and waits rather than exiting."""
    witness, heard = watching(broker)
    app.start()
    settle(witness)
    assert heard == [], "the app published before it had a railroad"
    assert app.running, "the app gave up on a store that was not up yet"

    store.start()

    assert drained(witness, lambda: rows(heard, MODE) != []), "it never came up"
    witness.close()


def test_a_traction_row_a_previous_process_left_is_zeroed(
    broker: Broker, store: Store, app: App
) -> None:
    """A traction row is retained, so a broker that outlived the last process
    hands the speed it was left at back verbatim and a translator subscribed
    to it sends that speed at the first connect: the locomotive rolls the
    moment somebody powers the rails, with no grant and nothing that says why
    (#333, ADR-0054). The row's one writer zeroes it coming up, which on this
    binding means waiting for the broker to hand it over first."""
    store.start()
    left = MqttBus(port=broker.port)
    assert left.wait_connected()
    left.publish(TRACTION, {"addr": "3", "speed": 0.7})
    assert until(lambda: TRACTION in left.last_values)
    left.close()

    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, MODE) != []), "it never came up"
    written = [payload["speed"] for payload in rows(heard, TRACTION)]
    assert written == [0.7, 0.0], "the speed the last process left was not zeroed"
    witness.close()


def test_it_acts_on_a_command_it_finds_on_the_broker(
    broker: Broker, store: Store, app: App
) -> None:
    """The drain half of the loop: a press published by anything at all is
    written through to the device vocabulary, where whatever answers for the
    supply reads it (ADR-0051)."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, MODE) != []), "it never came up"

    # A person's press, as the panel sends one. It does not say who published
    # it, and nothing here asks (rule 4).
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(POWER_WANTED, {"power": "on"})

    assert drained(
        witness, lambda: rows(heard, WANTED_TRACK)[-1]["power"] == "on"
    ), "the press was dropped"
    hand.close()
    witness.close()


def test_a_level_settles_on_seconds_passing(
    broker: Broker, store: Store, app: App
) -> None:
    """The other half of the loop, and the half no other app's has: the clock
    is advanced to wall time and `settle()` called once a turn, so a level
    that stands for the settling time becomes the block's occupancy event.

    Nothing schedules that call — a detector publishes a level *change* and
    nothing else — so a process that never made it would sit on a quiet
    railroad holding an arrival nobody was told about. Here the seconds really
    pass, where the rest of this suite drives the clock.
    """
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, MODE) != []), "it never came up"

    detector = MqttBus(port=broker.port)
    assert detector.wait_connected()
    detector.publish(f"{DEVICE_SENSOR}/{END}", {"addr": END, "occupancy": "occupied"})

    assert drained(
        witness, lambda: rows(heard, BLOCK_OCCUPIED) != []
    ), "the level never settled"
    assert rows(heard, BLOCK_OCCUPIED)[-1]["block"] == BLOCK
    assert app.running, "the app stopped on its own"
    detector.close()
    witness.close()
