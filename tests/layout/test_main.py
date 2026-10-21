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
import time
from collections.abc import Callable, Iterator
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from tc49.layout.__main__ import SILENCE_ENV, main, serve, silence
from tc49.layout.interface import (
    ALIVE_CONFIRMED,
    BLOCK_OCCUPIED,
    DEVICE_SENSOR,
    DRIVING,
    PLACED,
    POWER,
    POWER_WANTED,
    RAILROAD,
    TAKEN,
    WANTED_TRACK,
    WANTED_TRACTION,
    LayoutInterface,
)
from tc49.lib.bus import Payload
from tc49.lib.documents import Documents
from tc49.lib.loading import NO_RAILROAD, RAILROAD_WANTED
from tc49.lib.mqtt import MqttBus
from tc49.store import AssetStore
from tc49.store.server import make_server
from tests.brokers import Broker, drained, settle, until
from tests.harness import ASSETS, catalogued
from tests.ports import free_port

NAME = "crossover-yard"
OTHER = "single-track-meet"
"""A second railroad for the store to hold, loaded while the app runs: what
the record follows (ADR-0072, decision 5)."""
GONE = "nowhere"
"""A name the store lists no railroad under."""
END = "up_w.A"
BLOCK = "up_w"
TRACTION = f"{WANTED_TRACTION}/3"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as the store on the layout
    box holds one: a drawing, a roster and the catalogue its cars name."""
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    drawn(tmp_path, NAME)
    return tmp_path


def drawn(root: Path, railroad: str) -> None:
    """`railroad` on the installation at `root`: its drawing and its roster,
    the two documents this app reads."""
    for suffix in ("drawing", "roster"):
        shutil.copy(
            ASSETS / "layouts" / f"{railroad}.{suffix}.yaml",
            root / "layouts" / f"{railroad}.{suffix}.yaml",
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
    """The layout interface running as `python -m tc49.layout` runs it, on a
    thread so the test can watch the bus while it is up."""

    def __init__(
        self,
        broker: Broker,
        store: Store,
        railroad: str = NAME,
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
            kwargs={"log": log or quiet},
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
    """Against an empty broker with nothing else running: the four rows this
    app opens with, waiting for whoever subscribes next (ADR-0059).

    Which railroad this is, and then a railroad that is dark and has nobody's
    hand on a throttle — the state a person turns on from (ADR-0051), and the
    one every binding of the interface comes up in.
    """
    store.start()
    witness, heard = watching(broker)
    app.start()

    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it published nothing"
    assert rows(heard, RAILROAD)[-1]["name"] == NAME
    assert rows(heard, WANTED_TRACK)[-1]["power"] == "off"
    assert rows(heard, POWER)[-1]["power"] == "off"
    assert rows(heard, DRIVING)[-1]["driving"] == "manual"
    assert rows(heard, TAKEN)[-1]["taken"] == {}
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

    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"
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

    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"
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
    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"

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
    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"

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


def listening(witness: MqttBus, seconds: float) -> None:
    """Drain for a stretch of wall time: what is under test is a rate, so the
    seconds have to pass rather than a condition come true."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        witness.drain()
        time.sleep(0.01)


def test_a_layout_built_on_a_railroad_says_once_a_second_that_it_is_up(
    broker: Broker, store: Store, app: App
) -> None:
    """What something off the box watches to cut track power when the box goes
    silent (#716): at least once in any two seconds, so a watcher's timeout
    has a margin, and once a second on the monotonic clock rather than once a
    turn — the loop here turns every 10 ms, and a hundred frames a second
    would be the period leaking onto the wire."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"

    began = len(rows(heard, ALIVE_CONFIRMED))
    listening(witness, 3.5)
    said = rows(heard, ALIVE_CONFIRMED)[began:]

    assert 3 <= len(said) <= 5, f"{len(said)} in 3.5 s, where once a second is 3 or 4"
    assert all(payload == {} for payload in said)
    witness.close()


def test_a_layout_standing_with_no_railroad_says_nothing(
    broker: Broker, store: Store
) -> None:
    """Standing is up with nothing built, and nothing a cut of track power
    would interrupt: loading a railroad needs the power off anyway."""
    store.start()
    said: list[str] = []
    app = App(broker, store, railroad="nowhere", log=said.append)
    witness, heard = watching(broker)
    try:
        app.start()
        assert until(lambda: any("standing" in line for line in said)), "never stood"
        listening(witness, 2.5)
        assert rows(heard, ALIVE_CONFIRMED) == [], "it said it was up on no railroad"
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()


def test_it_starts_on_the_railroad_the_store_records(
    broker: Broker, store: Store, root: Path
) -> None:
    """A box comes back on the railroad its rails were built to (ADR-0072,
    decision 5): started with no railroad named, as every command line
    starts it, the app reads the store's record and comes up on that."""
    recorded(root, NAME)
    store.start()
    app = App(broker, store, railroad=NO_RAILROAD)
    witness, heard = watching(broker)
    try:
        app.start()
        assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"
        assert rows(heard, RAILROAD)[-1]["name"] == NAME
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()


def test_it_records_each_railroad_it_is_built_on(
    broker: Broker, store: Store, root: Path, app: App
) -> None:
    """The other half of the record: written each time this app is built on
    a railroad, on the way up and on each answered gesture, so the next start
    finds the one loaded last (ADR-0072, decision 5)."""
    drawn(root, OTHER)
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, TAKEN) != []), "it never came up"
    assert AssetStore(root).loaded() == NAME, "the railroad it came up on"

    # A person's gesture, with the rails dead as the app comes up (ADR-0060).
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
        assert rows(heard, TAKEN) == [], "it was built on a railroad it has not got"
        assert AssetStore(root).loaded() == GONE, "the record was cleared"
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()


@pytest.fixture
def built(monkeypatch: pytest.MonkeyPatch) -> list[LayoutInterface]:
    """Every layout interface the app builds, in order: the one it came up
    on, then one per rebuild. What a rebuild carries over is held in no row —
    the steel's position is on no topic (ADR-0030) — so it is read off the
    object."""
    interfaces: list[LayoutInterface] = []

    class Recorded(LayoutInterface):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            interfaces.append(self)

    monkeypatch.setattr("tc49.layout.__main__.LayoutInterface", Recorded)
    return interfaces


def test_a_rebuild_under_the_same_name_keeps_the_trains_whose_blocks_remain(
    broker: Broker, store: Store, root: Path, app: App, built: list[LayoutInterface]
) -> None:
    """With track power off a saved edit changes the drawing and not the
    track, so a train stands where it stood (ADR-0071). The edit here renames
    `yard_e`: the train standing in it has no block left in the drawing to
    stand in, and the one in `yard_w` is kept."""
    store.start()
    witness, _ = watching(broker)
    app.start()
    # Not the taken row: the interface writes it as it is constructed, before
    # `built` holds it.
    assert drained(witness, lambda: built != []), "it never came up"
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(PLACED, {"train": "freight_1", "block": "yard_w"})
    hand.publish(PLACED, {"train": "express_2", "block": "yard_e"})
    assert drained(
        witness, lambda: len(built[0].position) == 2
    ), "the placements never landed"

    # The rails are dead as the app comes up, so the gesture is answered.
    drawing = root / "layouts" / f"{NAME}.drawing.yaml"
    drawing.write_text(drawing.read_text().replace("yard_e", "siding_e"))
    hand.publish(RAILROAD_WANTED, {"railroad": NAME})

    assert drained(witness, lambda: len(built) == 2), "it was never rebuilt"
    assert built[1].position == {"freight_1": "yard_w"}
    hand.close()
    witness.close()


def test_a_saved_drawing_that_does_not_derive_leaves_the_railroad_loaded(
    broker: Broker, store: Store, root: Path, app: App
) -> None:
    """A save names the loaded railroad again (ADR-0071), and the store then
    holds a drawing with a dangling pin under that name. The app stays up on
    what it was built on and the row still names the railroad, so the page
    keeps the drawing open for the fix."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    # Power, not the railroad row: the constructor says power after the row,
    # and the gesture is dropped until the app has heard power read off.
    assert drained(witness, lambda: rows(heard, POWER) != []), "no power"

    drawing = root / "layouts" / f"{NAME}.drawing.yaml"
    document = yaml.safe_load(drawing.read_text())
    document["wires"] = document["wires"][:-1]
    drawing.write_text(yaml.safe_dump(document, sort_keys=False))
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(RAILROAD_WANTED, {"railroad": NAME})

    assert drained(witness, lambda: len(rows(heard, RAILROAD)) == 2), "not rebuilt"
    assert app.running, "the app stopped"
    assert rows(heard, RAILROAD)[-1]["name"] == NAME
    hand.close()
    witness.close()


@pytest.mark.parametrize("environ", [{}, {SILENCE_ENV: ""}, {SILENCE_ENV: "  "}])
def test_no_silence_set_is_five_seconds(environ: dict[str, str]) -> None:
    """Compose passes an unset variable through as `""`, which means the same
    as not passing it."""
    assert silence(environ) == 5.0


def test_a_silence_set_is_that_many_seconds() -> None:
    assert silence({SILENCE_ENV: "8"}) == 8.0


@pytest.mark.parametrize("said", ["soon", "1", "-3", "nan"])
def test_a_bad_silence_stops_the_app_at_start_naming_the_variable(
    said: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A silence the deployment got wrong is said once, at start, and the app
    exits rather than looking for a broker: a second or less would release a
    train between two of its throttle's `throttle_alive`, and a container in a
    restart loop whose log names the variable is a line of the env file to
    fix."""
    monkeypatch.setenv(SILENCE_ENV, said)
    monkeypatch.setattr(
        "sys.argv",
        ["tc49.layout", "--broker", "localhost:1", "--store", "http://localhost:1"],
    )
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code != 0
    assert SILENCE_ENV in capsys.readouterr().err
