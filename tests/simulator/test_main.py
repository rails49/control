"""The simulator as its own process: what it takes for it to come up alone.

Against a real broker and a real store on real sockets, because that is what
is under test — an app started against nothing, in whatever order the machine
brings the two up (ADR-0059, decision 5). The loop itself runs on a thread
here and is ended with the event `serve` takes; in the deployment it is the
main thread and a signal ends it.

The railroad is `crossover-yard`, off the store, where the rest of this suite
loads one out of `bench/`: what is under test here is the process, and a
process reads the documents an installation holds. Its drawing is the only
file the store is given — this app reads one document, and a store with no
roster on it is enough to bring it up.

Time is not driven either, where every other test of this app injects the
wait: the loop is the app's own and the seconds really pass, so the two delays
are shortened to milliseconds and a transit is watched rather than stepped.
"""

import shutil
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest

from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.mqtt import MqttBus
from tc49.simulator.__main__ import serve
from tc49.store.server import make_server
from tests.brokers import Broker, drained, free_port, settle
from tests.harness import ASSETS

RAILROAD_NAME = "crossover-yard"
RAILROAD = "tc49/layout/state/railroad"
POWER = "tc49/layout/state/power"
MOVE = "tc49/layout/move"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACED = "tc49/dispatch/train_placed"

TRANSIT_S = 0.05
CLEAR_S = 0.1
"""The two delays, deliberately unequal and both short: what the deployment
spends half a minute on is the same queue, and the suite has no reason to
wait for it."""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as far as this app reads one:
    a drawing, which is the whole of what it is given. No roster — an address
    is what a roster answers with, and this binding sends no command to
    anything."""
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ASSETS / "layouts" / f"{RAILROAD_NAME}.drawing.yaml",
        tmp_path / "layouts" / f"{RAILROAD_NAME}.drawing.yaml",
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
    """The simulator running as `python -m tc49.simulator` runs it, on a
    thread so the test can watch the bus while it is up."""

    def __init__(self, broker: Broker, store: Store) -> None:
        self.bus = MqttBus(port=broker.port)
        self._documents = Documents(
            store.url, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=serve,
            args=(self.bus, self._documents, RAILROAD_NAME, self._stop, 0.01),
            kwargs={"transit_s": TRANSIT_S, "clear_s": CLEAR_S, "log": quiet},
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
    """Against an empty broker with nothing else running: the two rows this
    app opens with, waiting for whoever subscribes next (ADR-0059).

    Which railroad this is, which is the row a view reads whichever binding of
    the layout interface is running (ADR-0059 decision 2, as ADR-0060 amends
    it), and a track that is live — simulated rails always are, a power cut
    being a physical act this binding never simulates (ADR-0030).
    """
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, POWER) != []), "it published nothing"
    assert rows(heard, RAILROAD)[-1]["name"] == RAILROAD_NAME
    assert rows(heard, POWER)[-1]["power"] == "on"
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

    assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"
    witness.close()


def test_it_carries_a_train_across_a_transit_it_finds_on_the_broker(
    broker: Broker, store: Store, app: App
) -> None:
    """The loop is what makes the app an app, and this one is both halves of
    it at once: a hand's placement and a granted move are drained, the two
    sensor events are scheduled on the delays, and the seconds pass on a wall
    clock until each fires — the head into the destination first and the tail
    off the origin after it, the only order the physical railroad can produce
    (ADR-0047).

    Both frames are published by another client, which is what the broker
    makes of them: neither says who sent it and nothing here asks (rule 4).
    """
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"

    # The steel is where a hand left it. The process came up holding no
    # train, so the placement is what puts one on the layout, and the witness
    # hearing it is the broker having handed it to every subscriber — this
    # app among them — before the move that depends on it is sent.
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(PLACED, {"train": "freight_1", "block": "yard_w"})
    assert drained(witness, lambda: rows(heard, PLACED) != []), "the drag was dropped"

    hand.publish(
        MOVE,
        {
            "train": "freight_1",
            "connection": "west_ladder",
            "transit": "to_dn",
            "into": "dn_w",
        },
    )

    assert drained(witness, lambda: rows(heard, VACATED) != []), "nothing moved"
    assert rows(heard, OCCUPIED)[-1]["block"] == "dn_w"
    assert rows(heard, VACATED)[-1]["block"] == "yard_w"
    assert app.running, "the app stopped on its own"
    hand.close()
    witness.close()
