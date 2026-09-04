"""The scheduler as its own process: what it takes for it to come up alone.

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

from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.mqtt import MqttBus
from tc49.scheduler.__main__ import serve
from tc49.scheduler.scheduler import FACING
from tc49.store.server import make_server
from tests.brokers import Broker, drained, free_port, settle, until
from tests.harness import ASSETS, catalogued

RAILROAD = "crossover-yard"
OTHER = "single-track-meet"
EXHAUSTED = "tc49/schedule/state/exhausted"
PLACED = "tc49/dispatch/train_placed"
WANTED = "tc49/schedule/request_wanted"
SUBMITTED = "tc49/dispatch/request_submitted"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as the store on the layout
    box holds one: a drawing, a roster and the catalogue its cars name."""
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    # Two railroads, because one is loaded while the apps run (ADR-0060) and
    # the other is what a person picking from the band picks.
    for railroad in (RAILROAD, OTHER):
        for suffix in ("drawing", "roster"):
            shutil.copy(
                ASSETS / "layouts" / f"{railroad}.{suffix}.yaml",
                tmp_path / "layouts" / f"{railroad}.{suffix}.yaml",
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
    """The scheduler running as `python -m tc49.scheduler` runs it, on a
    thread so the test can watch the bus while it is up."""

    def __init__(self, broker: Broker, store: Store) -> None:
        self.bus = MqttBus(port=broker.port)
        self._documents = Documents(
            store.url, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05
        )
        self._stop = threading.Event()
        self.said: list[str] = []
        """What the app has printed. The suite asserts on the bus, except
        where what happened is not on it: a railroad refused is a sentence
        for the person watching the container and no row of anyone's."""
        self._thread = threading.Thread(
            target=serve,
            args=(self.bus, self._documents, RAILROAD, self._stop, 0.01),
            kwargs={"log": self.said.append},
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
    """Against an empty broker with nothing else running: the two rows the
    scheduler owns, waiting for whoever subscribes next (ADR-0059)."""
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(
        witness, lambda: rows(heard, EXHAUSTED) != []
    ), "it published nothing"
    assert rows(heard, FACING)[-1]["facing"] == {}
    assert rows(heard, EXHAUSTED)[-1]["exhausted"] is True
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

    assert drained(witness, lambda: rows(heard, EXHAUSTED) != []), "it never came up"
    witness.close()


def test_the_facing_a_previous_process_left_is_adopted(
    broker: Broker, store: Store, app: App
) -> None:
    """A scheduler restarted under a running railroad finds its own row on
    the broker and carries the trains' facing forward, exactly as the durable
    file did in one process (#123). Without it every train's direction arrow
    is dropped and the next drag has no departure end."""
    store.start()
    left = MqttBus(port=broker.port)
    assert left.wait_connected()
    left.publish(FACING, {"facing": {"freight_1": "yard_w.A-to-B"}})
    assert until(lambda: FACING in left.last_values)
    left.close()

    witness, heard = watching(broker)
    app.start()

    # The facing row goes out before `exhausted`, so the last one heard by
    # the time that arrives is this process's and not the one it adopted.
    assert drained(witness, lambda: rows(heard, EXHAUSTED) != [])
    assert rows(heard, FACING)[-1]["facing"] == {"freight_1": "yard_w.A-to-B"}
    witness.close()


def test_it_answers_a_gesture_it_finds_on_the_broker(
    broker: Broker, store: Store, app: App
) -> None:
    """The loop is what makes the app an app: a drag published by anything at
    all is drained and composed into the request the dispatcher acts on."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, EXHAUSTED) != []), "it never came up"

    # A placement as the dispatcher announces one, and a drag as a page sends
    # one. Neither says who published it, and nothing here asks (rule 4).
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(PLACED, {"train": "freight_1", "block": "yard_w"})
    assert drained(
        witness, lambda: rows(heard, FACING)[-1]["facing"] != {}
    ), "the placement was never heard"
    hand.publish(WANTED, {"train": "freight_1", "dest": ["yard_e.A"]})

    assert drained(witness, lambda: rows(heard, SUBMITTED) != []), "nothing composed"
    submitted = rows(heard, SUBMITTED)[-1]
    assert submitted["train"] == "freight_1" and submitted["depart"] == "yard_w.B"
    hand.close()
    witness.close()
    hand.close()
    witness.close()


RAILROAD_ROW = "tc49/layout/state/railroad"


def test_it_rebuilds_on_the_railroad_the_row_names(
    broker: Broker, store: Store, app: App
) -> None:
    """A railroad is loaded while the apps run (ADR-0060): the row moves, the
    facing this app held for the last railroad is cleared, and it comes up on
    the new one. The clearing is the point — the facing is adopted at
    construction (#123), so a rebuild alone would carry a departure end of a
    railroad that is gone."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, EXHAUSTED) != []), "it never came up"

    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(FACING, {"facing": {"freight_1": "yard_w.A-to-B"}})
    assert drained(witness, lambda: rows(heard, FACING)[-1]["facing"] != {})
    hand.publish(RAILROAD_ROW, {"name": OTHER})

    assert drained(
        witness, lambda: rows(heard, FACING)[-1]["facing"] == {}, timeout=15.0
    ), "the facing of the railroad that left was not cleared"
    assert app.running, "the app stopped on the way over"
    hand.close()
    witness.close()


def test_a_railroad_the_store_does_not_have_is_said_and_not_taken(
    broker: Broker, store: Store, app: App
) -> None:
    """An app with nothing to run on is worse than one still running the
    railroad it had, so a name the store answers 404 for is reported and
    refused (ADR-0050). It rebuilds on the railroad it has and goes on
    answering gestures about it."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, EXHAUSTED) != []), "it never came up"

    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(RAILROAD_ROW, {"name": "atlantis"})

    assert until(
        lambda: any("atlantis" in line for line in app.said), 15.0
    ), f"it said nothing about a railroad it could not load: {app.said}"
    assert until(
        lambda: app.said[-1].startswith(f"up on '{RAILROAD}'"), 15.0
    ), f"it did not come back up on the railroad it has: {app.said}"

    # And it is answering for that railroad: a train of the one it still has,
    # placed, is heard and composed — which no app that had given up its
    # layout could do, and no app still rebuilding would get to.
    hand.publish(PLACED, {"train": "freight_1", "block": "yard_w"})
    assert drained(
        witness, lambda: rows(heard, FACING)[-1]["facing"] != {}, timeout=15.0
    ), "it stopped answering for the railroad it was running"
    assert app.running, "it gave up on a railroad it was not asked to leave"

    # The refusal is answered once and not for ever: the row still stands and
    # the app is not spending its life rebuilding on it.
    said = len(app.said)
    settle(witness, 2.0)
    assert app.said[said:] == [], f"it went on trying: {app.said[said:]}"
    hand.close()
    witness.close()
