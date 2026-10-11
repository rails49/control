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
import time
from collections.abc import Callable, Iterator
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import pytest

from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.loading import NO_RAILROAD
from tc49.lib.mqtt import MqttBus
from tc49.simulator import Simulator
from tc49.simulator.__main__ import serve
from tc49.store import AssetStore
from tc49.store.server import make_server
from tests.brokers import Broker, drained, settle, until
from tests.harness import ASSETS
from tests.ports import free_port

RAILROAD_NAME = "crossover-yard"
OTHER = "single-track-meet"
"""A second railroad for the store to hold, loaded while the app runs: what
the record follows (ADR-0072, decision 5)."""
GONE = "nowhere"
"""A name the store lists no railroad under."""
RAILROAD = "tc49/layout/state/railroad"
POWER = "tc49/layout/state/power"
MOVE = "tc49/layout/move"
OCCUPIED = "tc49/layout/block_occupied"
VACATED = "tc49/layout/block_vacated"
PLACED = "tc49/dispatch/train_placed"
ALIVE = "tc49/layout/alive_confirmed"
POWER_WANTED = "tc49/layout/power_wanted"

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
    drawn(tmp_path, RAILROAD_NAME)
    return tmp_path


def drawn(root: Path, railroad: str) -> None:
    """`railroad` on the installation at `root`: its drawing, the one
    document this app reads."""
    shutil.copy(
        ASSETS / "layouts" / f"{railroad}.drawing.yaml",
        root / "layouts" / f"{railroad}.drawing.yaml",
    )


def recorded(root: Path, railroad: str) -> None:
    """The store's record of the railroad loaded last, as the binding that
    ran before this one left it (#728)."""
    AssetStore(root).put_loaded(railroad)


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

    def __init__(
        self,
        broker: Broker,
        store: Store,
        railroad: str = RAILROAD_NAME,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.bus = MqttBus(port=broker.port)
        self._documents = Documents(
            store.url, log=quiet, first_backoff_s=0.01, max_backoff_s=0.05
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=serve,
            args=(self.bus, self._documents, railroad, self._stop, 0.01),
            kwargs={"transit_s": TRANSIT_S, "clear_s": CLEAR_S, "log": log or quiet},
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:  # started, and so joinable (#560)
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
    it), and a track that is off, as the layout interface comes up: a
    simulated box needs ON after it starts, as a real one does (ADR-0070).
    """
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, POWER) != []), "it published nothing"
    assert rows(heard, RAILROAD)[-1]["name"] == RAILROAD_NAME
    assert rows(heard, POWER)[-1]["power"] == "off"
    assert app.running, "the app stopped on its own"
    witness.close()


def test_it_never_says_the_layout_is_up(broker: Broker, store: Store, app: App) -> None:
    """`alive_confirmed` is what something off the box cuts track power on
    when it stops, and the simulator drives no hardware: a running one says
    nothing on it however long it runs (#716)."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"

    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        witness.drain()
        time.sleep(0.01)

    assert rows(heard, ALIVE) == [], "the simulator said the layout was up"
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
    it at once: a press of ON, a hand's placement and a granted move are
    drained, the two sensor events are scheduled on the delays, and the
    seconds pass on a wall clock until each fires — the head into the
    destination first and the tail off the origin after it, the only order
    the physical railroad can produce (ADR-0047).

    All three frames are published by another client, which is what the broker
    makes of them: none says who sent it and nothing here asks (rule 4).
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
    # ON first, as a person presses it on a box that has just come up: with
    # the power off a `move` is dropped, as the layout drops it (ADR-0070).
    hand.publish(POWER_WANTED, {"power": "on"})
    assert drained(
        witness, lambda: rows(heard, POWER)[-1]["power"] == "on"
    ), "the press went unanswered"
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


RAILROAD_WANTED = "tc49/layout/railroad_wanted"


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[Simulator]:
    """Every simulator the app builds, in order: the one it came up on, then
    one per rebuild. What a rebuild carries over is held in no row — it is
    the steel's own memory, on no topic (ADR-0030) — so it is read off the
    object."""
    simulators: list[Simulator] = []

    class Recorded(Simulator):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            simulators.append(self)

    monkeypatch.setattr("tc49.simulator.__main__.Simulator", Recorded)
    return simulators


def test_a_rebuild_under_the_same_name_keeps_the_trains_whose_blocks_remain(
    broker: Broker, store: Store, root: Path, app: App, built: list[Simulator]
) -> None:
    """With track power off a saved edit changes the drawing and not the
    track, so the steel stands where it stood (ADR-0071). The edit here
    renames `yard_e`: the train standing in it has no block left in the
    drawing to stand in, and the one in `yard_w` is kept."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(PLACED, {"train": "freight_1", "block": "yard_w"})
    hand.publish(PLACED, {"train": "express_2", "block": "yard_e"})
    assert drained(
        witness, lambda: len(built[0].position) == 2
    ), "the placements never landed"

    drawing = root / "layouts" / f"{RAILROAD_NAME}.drawing.yaml"
    drawing.write_text(drawing.read_text().replace("yard_e", "siding_e"))
    hand.publish(RAILROAD_WANTED, {"railroad": RAILROAD_NAME})

    assert drained(witness, lambda: len(built) == 2), "it was never rebuilt"
    assert built[1].position == {"freight_1": "yard_w"}
    hand.close()
    witness.close()


def test_it_starts_on_the_railroad_the_store_records(
    broker: Broker, store: Store, root: Path
) -> None:
    """A box comes back on the railroad it was left on (ADR-0072, decision
    5): started with no railroad named, as every command line starts it, the
    app reads the store's record and comes up on that, as `layout` does."""
    recorded(root, RAILROAD_NAME)
    store.start()
    app = App(broker, store, railroad=NO_RAILROAD)
    witness, heard = watching(broker)
    try:
        app.start()
        assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"
        assert rows(heard, RAILROAD)[-1]["name"] == RAILROAD_NAME
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()


def test_it_records_each_railroad_it_is_built_on(
    broker: Broker, store: Store, root: Path, app: App
) -> None:
    """Written each time this app is built on a railroad, on the way up and
    on each answered gesture, so the next start finds the one loaded last
    (ADR-0072, decision 5)."""
    drawn(root, OTHER)
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, POWER) != []), "it never came up"
    assert AssetStore(root).loaded() == RAILROAD_NAME, "the railroad it came up on"

    # A person's gesture, with the rails dead as the app comes up (ADR-0070).
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(RAILROAD_WANTED, {"railroad": OTHER})

    assert drained(
        witness, lambda: rows(heard, RAILROAD)[-1]["name"] == OTHER
    ), "the gesture was dropped"
    assert AssetStore(root).loaded() == OTHER, "the railroad loaded afterwards"
    hand.close()
    witness.close()


def test_a_recorded_railroad_the_store_no_longer_has_leaves_it_standing(
    broker: Broker, store: Store, root: Path
) -> None:
    """The record is a starting point and not a binding, as the flag is: one
    the store cannot give leaves the app standing and naming no railroad on
    the row (#727). The record is not cleared — the next load overwrites it."""
    recorded(root, GONE)
    store.start()
    said: list[str] = []
    app = App(broker, store, railroad=NO_RAILROAD, log=said.append)
    witness, heard = watching(broker)
    try:
        app.start()
        assert until(lambda: any("standing" in line for line in said)), "never stood"
        assert drained(witness, lambda: rows(heard, RAILROAD) != []), "no row"
        assert rows(heard, RAILROAD)[-1]["name"] == NO_RAILROAD
        assert rows(heard, POWER) == [], "it was built on a railroad it has not got"
        assert AssetStore(root).loaded() == GONE, "the record was cleared"
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()
