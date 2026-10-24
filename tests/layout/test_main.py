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

import pytest
import yaml

from tc49.layout.__main__ import (
    CLOCK,
    CLOCK_WANTED,
    OWNED,
    SILENCE_ENV,
    FastClockRow,
    main,
    retained,
    serve,
    silence,
)
from tc49.layout.interface import (
    ALIVE_CONFIRMED,
    ALLOCATION,
    BLOCK_OCCUPIED,
    DEVICE_SENSOR,
    DRIVING,
    POWER,
    POWER_WANTED,
    RAILROAD,
    TAKEN,
    WANTED_TRACK,
    WANTED_TRACTION,
)
from tc49.lib.bus import InProcessBus, Payload
from tc49.lib.clock import Clock
from tc49.lib.documents import Documents
from tc49.lib.fast_clock import FastClock, KeptClock
from tc49.lib.loading import BUILT, RAILROAD_WANTED
from tc49.lib.mqtt import MqttBus
from tc49.store import AssetStore
from tc49.store.server import make_server
from tests.brokers import Broker, drained, settle, until
from tests.harness import ASSETS, catalogued
from tests.ports import free_port

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


def test_the_allocation_a_dispatcher_left_is_held_before_the_build(
    broker: Broker,
) -> None:
    """The app takes where each train stands from the retained allocation as
    it is constructed (#960), so the wait before the build has to have it."""
    left = MqttBus(port=broker.port)
    assert left.wait_connected()
    left.publish(ALLOCATION, {"trains": {"freight_1": BLOCK}, "crossing": {}})
    assert until(lambda: ALLOCATION in left.last_values)
    left.close()

    bus = MqttBus(port=broker.port)
    assert bus.wait_connected()
    retained(bus, threading.Event(), 0.5)

    assert bus.last_values[ALLOCATION]["trains"] == {"freight_1": BLOCK}
    bus.close()


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


def test_a_layout_built_on_a_railroad_says_the_fast_clock_once_a_second(
    broker: Broker, store: Store, app: App
) -> None:
    """Every page draws the time it is sent and reads no wall clock of its own
    (ADR-0090): a time of day in whole seconds, and the speed-up, which is 1
    on a railroad with no start time of its own. Once a second on the
    monotonic clock, as `alive_confirmed` is, and not once a turn."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, CLOCK) != []), "no clock came"

    began = len(rows(heard, CLOCK))
    listening(witness, 3.5)
    said = rows(heard, CLOCK)[began:]

    assert 3 <= len(said) <= 5, f"{len(said)} in 3.5 s, where once a second is 3 or 4"
    assert all(set(payload) == {"at", "time", "speed_up"} for payload in said)
    assert all(payload["speed_up"] == 1 for payload in said)
    assert all(isinstance(payload["time"], int) for payload in said)
    assert all(0 <= payload["time"] < 24 * 60 * 60 for payload in said)
    witness.close()


def test_a_railroad_is_loaded_at_the_start_time_it_keeps(
    broker: Broker, store: Store, app: App, root: Path
) -> None:
    """Not the box's time of day (ADR-0090, decision 4)."""
    (root / "layouts" / f"{NAME}.clock.yaml").write_text(
        "start: '03:15'\nspeed_up: 4\n"
    )
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, CLOCK) != []), "no clock came"
    said = rows(heard, CLOCK)[0]
    assert said["speed_up"] == 4
    assert 3 * 3600 + 15 * 60 <= said["time"] < 3 * 3600 + 15 * 60 + 4 * 5
    witness.close()


def test_a_railroad_that_keeps_no_clock_has_none_written(
    broker: Broker, store: Store, app: App, root: Path
) -> None:
    """Started at the box's time, which is not kept until somebody sets it."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: len(rows(heard, CLOCK)) >= 2), "no clock came"
    assert not (root / "layouts" / f"{NAME}.clock.yaml").exists()
    witness.close()


def test_the_clock_a_person_sets_is_kept_with_the_railroad(
    broker: Broker, store: Store, app: App, root: Path
) -> None:
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, CLOCK) != []), "no clock came"
    witness.publish(CLOCK_WANTED, {"time": 8 * 3600 + 30 * 60 + 12, "speed_up": 8})
    path = root / "layouts" / f"{NAME}.clock.yaml"
    assert until(
        lambda: path.exists() and "08:30" in path.read_text()
    ), "the clock was never kept"
    assert AssetStore(root).clock(NAME) == {"start": "08:30", "speed_up": 8.0}
    witness.close()


def test_a_layout_built_on_a_railroad_takes_the_clock_a_person_sets(
    broker: Broker, store: Store, app: App
) -> None:
    """A person sets the clock from any page (ADR-0090, decision 2), and every
    page is told at once rather than at the next beat."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    assert drained(witness, lambda: rows(heard, CLOCK) != []), "no clock came"

    witness.publish(CLOCK_WANTED, {"time": 8 * 3600, "speed_up": 8})
    assert drained(
        witness, lambda: any(row["speed_up"] == 8 for row in rows(heard, CLOCK))
    ), "the clock was never set"
    said = next(row for row in rows(heard, CLOCK) if row["speed_up"] == 8)
    assert 8 * 3600 <= said["time"] < 8 * 3600 + 8 * 2
    witness.close()


class Monotonic:
    """A real clock a test moves by hand."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def clocked(
    kept: list[KeptClock] | None = None,
) -> tuple[InProcessBus, Monotonic, Callable[[], None], list[Payload]]:
    """The fast clock's row on a bus, started at 07:00:30 at a speed-up of 1
    on a railroad that keeps 07:00, the beat that says it, and what it says.
    What it keeps goes in `kept`."""
    bus = InProcessBus(Clock())
    monotonic = Monotonic()
    said: list[Payload] = []
    bus.subscribe(CLOCK, lambda _topic, payload: said.append(payload))
    row = FastClockRow(
        bus,
        FastClock(7 * 3600 + 30, 1.0, monotonic.now),
        KeptClock(7 * 3600, 1.0),
        monotonic,
        (kept if kept is not None else []).append,
    )

    def beat() -> None:
        row.say()
        bus.drain()

    beat()
    return bus, monotonic, beat, said


def test_a_new_time_is_said_at_once_and_counted_on_from() -> None:
    bus, monotonic, beat, said = clocked()
    monotonic.now += 10
    bus.publish(CLOCK_WANTED, {"time": 9 * 3600})
    bus.drain()
    monotonic.now += 5
    beat()
    assert [row["time"] for row in said] == [7 * 3600 + 30, 9 * 3600, 9 * 3600 + 5]
    assert said[-1]["speed_up"] == 1


def test_a_new_speed_up_runs_from_where_the_clock_stood() -> None:
    bus, monotonic, beat, said = clocked()
    monotonic.now += 60
    bus.publish(CLOCK_WANTED, {"speed_up": 8})
    bus.drain()
    monotonic.now += 1
    beat()
    assert [row["time"] for row in said[1:]] == [7 * 3600 + 90, 7 * 3600 + 98]
    assert said[-1]["speed_up"] == 8


def test_a_new_time_is_kept_as_the_start_rounded_down_to_the_minute() -> None:
    """Setting the time saves it as the start time (ADR-0090, decision 3),
    with the speed-up the clock runs at."""
    kept: list[KeptClock] = []
    bus, _, _, _ = clocked(kept)
    bus.publish(CLOCK_WANTED, {"time": 9 * 3600 + 59})
    bus.drain()
    assert kept == [KeptClock(9 * 3600, 1.0)]


def test_a_new_speed_up_is_kept_with_the_start_it_had() -> None:
    """Where the clock stands is not kept, only what a person set: the
    railroad still starts at 07:00, now at 8."""
    kept: list[KeptClock] = []
    bus, monotonic, _, _ = clocked(kept)
    monotonic.now += 600
    bus.publish(CLOCK_WANTED, {"speed_up": 8})
    bus.publish(CLOCK_WANTED, {"time": 18 * 3600, "speed_up": 4})
    bus.drain()
    assert kept == [KeptClock(7 * 3600, 8.0), KeptClock(18 * 3600, 4.0)]


def test_a_clock_that_runs_keeps_nothing() -> None:
    """The store is written only when a person sets the clock, so the backup
    has nothing new to save while it runs (ADR-0090)."""
    kept: list[KeptClock] = []
    _, monotonic, beat, _ = clocked(kept)
    for _ in range(3):
        monotonic.now += 1
        beat()
    assert kept == []


def test_a_clock_gesture_that_cannot_be_read_says_nothing() -> None:
    """Dropped as any malformed gesture is (ADR-0034): no row, and the clock
    runs on as it was."""
    kept: list[KeptClock] = []
    bus, _, _, said = clocked(kept)
    for payload in ({}, {"time": 86400}, {"speed_up": 0}, {"time": 1, "speed_up": -1}):
        bus.publish(CLOCK_WANTED, payload)
    bus.drain()
    assert len(said) == 1
    assert kept == []


def test_the_fast_clock_is_cleared_with_the_other_layout_rows() -> None:
    """A railroad loaded starts on a broker holding nothing of the last one
    (ADR-0060), the clock included: the next build starts it again."""
    assert CLOCK in OWNED


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
        assert rows(heard, CLOCK) == [], "it said the time on no railroad"
        assert app.running, "the app stopped on its own"
    finally:
        app.stop()
        witness.close()


def broken(root: Path, railroad: str) -> None:
    """`railroad`'s drawing with its last wire gone, which leaves a dangling
    pin: a drawing that is not a valid drawing, as a track plan being rebuilt
    is (ADR-0085)."""
    drawing = root / "layouts" / f"{railroad}.drawing.yaml"
    document = yaml.safe_load(drawing.read_text())
    document["wires"] = document["wires"][:-1]
    drawing.write_text(yaml.safe_dump(document, sort_keys=False))


def test_a_saved_drawing_that_does_not_derive_names_the_railroad_not_built(
    broker: Broker, store: Store, root: Path, app: App
) -> None:
    """A save names the loaded railroad again (ADR-0071), and the store then
    holds a drawing with a dangling pin under that name. The app stays up on
    what it was built on, and the row names the railroad with `built: false`
    so the page keeps the drawing open for the fix. The fix saved is the
    build arriving: `built: true` with a new stamp (ADR-0085, decision 4)."""
    store.start()
    witness, heard = watching(broker)
    app.start()
    # Power, not the railroad row: the constructor says power after the row,
    # and the gesture is dropped until the app has heard power read off.
    assert drained(witness, lambda: rows(heard, POWER) != []), "no power"
    assert rows(heard, RAILROAD)[-1][BUILT] is True
    drawing = root / "layouts" / f"{NAME}.drawing.yaml"
    valid = drawing.read_text()

    broken(root, NAME)
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(RAILROAD_WANTED, {"railroad": NAME})

    assert drained(witness, lambda: len(rows(heard, RAILROAD)) == 2), "not named"
    assert app.running, "the app stopped"
    unbuilt = rows(heard, RAILROAD)[-1]
    assert (unbuilt["name"], unbuilt[BUILT]) == (NAME, False)
    assert AssetStore(root).loaded() == NAME

    drawing.write_text(valid)
    hand.publish(RAILROAD_WANTED, {"railroad": NAME})

    assert drained(
        witness, lambda: rows(heard, RAILROAD)[-1].get(BUILT) is True
    ), "the fix was never built"
    rebuilt = rows(heard, RAILROAD)[-1]
    assert rebuilt["name"] == NAME
    assert rebuilt["at"] != unbuilt["at"]
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
