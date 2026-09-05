"""The dispatcher as its own process: what it takes for it to come up alone.

Against a real broker and a real store on real sockets, because that is what
is under test — an app started against nothing, in whatever order the machine
brings the two up (ADR-0059, decision 5). The loop itself runs on a thread
here and is ended with the event `serve` takes; in the deployment it is the
main thread and a signal ends it.
"""

import shutil
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest

from tc49.dispatcher.__main__ import serve
from tc49.dispatcher.dispatch import ALLOCATION, ASPECTS
from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.mqtt import MqttBus
from tc49.store.server import make_server
from tests.brokers import Broker, drained, free_port, settle, until
from tests.harness import ASSETS, catalogued

RAILROAD = "crossover-yard"
RUN = "tc49/dispatch/state/run"
DISPUTED = "tc49/dispatch/state/disputed"
GRANTED = "tc49/dispatch/lock_granted"
PLACEMENT_WANTED = "tc49/dispatch/placement_wanted"
PLACED = "tc49/dispatch/train_placed"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as the store on the layout
    box holds one: a drawing, a roster and the catalogue its cars name."""
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    for suffix in ("drawing", "roster"):
        shutil.copy(
            ASSETS / "layouts" / f"{RAILROAD}.{suffix}.yaml",
            tmp_path / "layouts" / f"{RAILROAD}.{suffix}.yaml",
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
    """The dispatcher running as `python -m tc49.dispatcher` runs it, on a
    thread so the test can watch the bus while it is up."""

    def __init__(self, broker: Broker, store: Store) -> None:
        self.bus = MqttBus(port=broker.port)
        self._documents = Documents(
            store.url, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=serve,
            args=(self.bus, self._documents, RAILROAD, self._stop, 0.01),
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
    """Against an empty broker with nothing else running: the four rows the
    dispatcher opens with, waiting for whoever subscribes next (ADR-0059).

    Held, with an empty layout and every signal at stop: the only thing there
    is to do on a railroad nothing stands on is place trains, and a run an
    operator drives comes up that way (ADR-0037 as #171 amends it).
    """
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, DISPUTED) != []), "it published nothing"
    assert rows(heard, RUN)[-1]["run"] == "held"
    assert rows(heard, RUN)[-1]["moving"] is False
    assert set(rows(heard, ASPECTS)[-1]["aspects"].values()) == {"stop"}
    picture = rows(heard, ALLOCATION)[-1]
    assert (picture["trains"], picture["locks"], picture["requests"]) == ({}, {}, [])
    assert rows(heard, DISPUTED)[-1]["trains"] == []
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

    assert drained(witness, lambda: rows(heard, DISPUTED) != []), "it never came up"
    witness.close()


def test_the_picture_a_previous_process_left_is_adopted(
    broker: Broker, store: Store, app: App
) -> None:
    """A dispatcher restarted under a running railroad finds its own picture
    on the broker and comes up with its trains where they stood, which is
    the whole of what #123 asks for now that the broker holds them. Without
    it the railroad comes
    up empty and every standing train is a placement somebody has to make
    again."""
    store.start()
    left = MqttBus(port=broker.port)
    assert left.wait_connected()
    left.publish(
        ALLOCATION,
        {
            "trains": {"freight_1": "yard_w"},
            "crossing": {},
            "locks": {"yard_w": "freight_1"},
            "requests": [],
        },
    )
    assert until(lambda: ALLOCATION in left.last_values)
    left.close()

    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, DISPUTED) != []), "it never came up"
    # The standing lock is rebuilt one block per train and announced, and the
    # picture this process publishes carries the train the last one left.
    assert rows(heard, GRANTED)[-1] == {"train": "freight_1", "resources": ["yard_w"]}
    assert rows(heard, ALLOCATION)[-1]["trains"] == {"freight_1": "yard_w"}
    assert rows(heard, ALLOCATION)[-1]["locks"] == {"yard_w": "freight_1"}
    witness.close()


def test_it_answers_a_gesture_it_finds_on_the_broker(
    broker: Broker, store: Store, app: App
) -> None:
    """The loop is what makes the app an app: a placement published by
    anything at all is drained, accepted against the roster and the layout,
    and announced as the fact the rest of the railroad reads (ADR-0039)."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, DISPUTED) != []), "it never came up"

    # A drag as a page sends one. It does not say who published it, and
    # nothing here asks (rule 4).
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(PLACEMENT_WANTED, {"train": "freight_1", "block": "yard_e"})

    assert drained(witness, lambda: rows(heard, PLACED) != []), "the drag was dropped"
    assert rows(heard, PLACED)[-1] == {"train": "freight_1", "block": "yard_e"}
    assert rows(heard, ALLOCATION)[-1]["trains"] == {"freight_1": "yard_e"}
    hand.close()
    witness.close()
