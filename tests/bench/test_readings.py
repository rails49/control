"""`tc49 readings`: the typed readings as a client of the broker (#379).

The session used to hold the keyboard and the railroad in one process, so a
typed line reached `layout` by being published into a Python object beside it.
With every app in a container of its own (ADR-0059, decision 5) the person at
the keyboard is a client like the camera that will replace them: it connects
to the broker, reads the railroad off the store's HTTP face to know which
block ends there are, and publishes the row a detector would write.

Against a real broker on a real socket, because that is what is under test.
The loop runs on a thread here and is ended with the event `serve` takes or by
the input ending; in the deployment it is the main thread, and the person ends
it by typing Ctrl-D or Ctrl-C.

What these assert is the row on the broker — read by another client, which is
where a detector's readings are visible from. That the row is the one the
inventory declares, and that a typo is refused rather than published, is
`test_detector.py`'s and is not repeated.
"""

import io
import os
import shutil
import sys
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path
from typing import TextIO

import pytest

from tc49.bench.cli import main
from tc49.bench.detector import SENSOR, serve
from tc49.lib.bus import Payload
from tc49.lib.layout import Layout
from tc49.lib.mqtt import MqttBus
from tc49.store.server import make_server
from tests.bench.physical import a_railroad
from tests.brokers import Broker, drained, free_port, settle, until
from tests.harness import ASSETS, railroads

PERIOD_S = 0.01
"""What the suite waits between turns, where the deployment waits a tenth of a
second: a test types a line and then waits on the broker for it, and the turn
is the only thing between the two."""


def a_block(layout: Layout) -> str:
    """Some block of this railroad, which is what a sensor is addressed by:
    whichever comes first by name, since these ask what a typed line reaches
    and not what stands where."""
    return min(layout.blocks)


class Keyboard:
    """The person's end of the input, on a pipe: a line written here is a line
    the reader thread is blocked waiting for, which is what a terminal is and
    what a `StringIO` of the whole session is not."""

    def __init__(self) -> None:
        reading, writing = os.pipe()
        self.lines: TextIO = os.fdopen(reading, "r")
        self._writing: TextIO = os.fdopen(writing, "w")

    def types(self, line: str) -> None:
        self._writing.write(f"{line}\n")
        self._writing.flush()

    def leaves(self) -> None:
        """Ctrl-D: the input ends, and there is no more detector."""
        self._writing.close()

    def close(self) -> None:
        for end in (self._writing, self.lines):
            try:
                end.close()
            except OSError:  # pragma: no cover - already closed by a test
                pass


class Client:
    """`tc49 readings` running as the command runs it, on a thread so the test
    can type at it and watch the broker while it is up.

    Its client is made when it starts and not before, so a test can stop the
    broker first and have the keyboard go looking for one that is not there.
    """

    def __init__(self, broker: Broker, layout: Layout, keyboard: Keyboard) -> None:
        self._broker = broker
        self._layout = layout
        self._keyboard = keyboard
        self._bus: MqttBus | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.said = io.StringIO()
        self.up = threading.Event()

    def start(self) -> None:
        self._bus = MqttBus(port=self._broker.port)
        self._thread = threading.Thread(
            target=serve,
            args=(
                self._bus,
                self._layout,
                self._keyboard.lines,
                self.said,
                self._stop,
                PERIOD_S,
                self._log,
            ),
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
        """The log, dropped except for the one line that says it is on the
        broker and reading. What it says is for a person watching the
        terminal; the suite asserts on the bus."""
        if line.startswith("up on"):
            self.up.set()


@pytest.fixture
def keyboard() -> Iterator[Keyboard]:
    typing = Keyboard()
    try:
        yield typing
    finally:
        typing.close()


@pytest.fixture
def layout() -> Layout:
    """Some railroad this checkout has, which is what the block ends a reading
    may name are validated against."""
    drawn, _roster = a_railroad()
    return drawn


@pytest.fixture
def client(broker: Broker, layout: Layout, keyboard: Keyboard) -> Iterator[Client]:
    typed = Client(broker, layout, keyboard)
    try:
        yield typed
    finally:
        typed.stop()


def watching(broker: Broker) -> tuple[MqttBus, list[tuple[str, Payload]]]:
    """Another client of the same broker, and everything it hears: a reading
    is only worth anything where the rest of the railroad sees it."""
    bus = MqttBus(port=broker.port)
    assert bus.wait_connected(), "the witness never reached the broker"
    heard: list[tuple[str, Payload]] = []
    bus.subscribe("tc49/#", lambda topic, payload: heard.append((topic, payload)))
    return bus, heard


def rows(heard: list[tuple[str, Payload]], topic: str) -> list[Payload]:
    """What arrived on one topic, in the order it arrived."""
    return [payload for said, payload in heard if said == topic]


def test_a_typed_line_reaches_the_broker_as_the_retained_sensor_row(
    broker: Broker, layout: Layout, keyboard: Keyboard, client: Client
) -> None:
    """The whole of what this is for: a person types `<block>.<end> <level>`
    at one process and another reads the row a camera would have written.

    Retained, because it is a state topic and the broker keeps the last value
    of one — so a client that connects *after* the line was typed is told the
    level too, which is what a layout interface restarting under a railroad
    somebody has already walked around depends on (ADR-0059, decision 3).
    """
    witness, heard = watching(broker)
    client.start()
    assert client.up.wait(10), "it never came up"
    end = f"{a_block(layout)}.A"

    keyboard.types(f"{end} occupied")

    assert drained(
        witness, lambda: rows(heard, f"{SENSOR}/{end}") != []
    ), "the typed line never reached the broker"
    published = rows(heard, f"{SENSOR}/{end}")[-1]
    assert published["addr"] == end and published["occupancy"] == "occupied"

    later, kept = watching(broker)
    assert drained(
        later, lambda: rows(kept, f"{SENSOR}/{end}") != []
    ), "the broker was not holding the row for whoever came next"
    assert rows(kept, f"{SENSOR}/{end}")[-1]["occupancy"] == "occupied"
    later.close()
    witness.close()


def test_it_comes_up_against_a_broker_that_is_not_there_yet(
    broker: Broker, layout: Layout, keyboard: Keyboard, client: Client
) -> None:
    """The order nothing forbids: no `depends_on` anywhere, so the keyboard is
    started before the broker and waits rather than exiting.

    Nothing is read meanwhile — a publish made to a broker that is not there is
    dropped rather than queued (ADR-0050), so a line typed into one would be a
    reading nobody ever hears about — and the person is told what is being
    waited for.
    """
    broker.stop()
    client.start()
    assert not client.up.wait(1), "it said it was up with no broker to be up on"
    assert client.running, "it gave up on a broker that was not up yet"

    assert broker.start()

    # Reconnected on the client's own backoff, whose first step is a second.
    assert client.up.wait(30), "it never came up once the broker was there"
    witness, heard = watching(broker)
    end = f"{a_block(layout)}.B"
    keyboard.types(f"{end} clear")
    assert drained(
        witness, lambda: rows(heard, f"{SENSOR}/{end}") != []
    ), "nothing typed after the broker came up reached it"
    witness.close()


def test_a_typo_is_said_where_it_was_typed_and_the_keyboard_stays_up(
    broker: Broker, layout: Layout, keyboard: Keyboard, client: Client
) -> None:
    """A reading for a block nothing has is one the dispatcher could not
    explain, so it is refused at the keyboard where the answer is a line to
    retype (ADR-0048) — and refused rather than raised, this being a person
    typing beside a running railroad."""
    witness, heard = watching(broker)
    client.start()
    assert client.up.wait(10), "it never came up"
    end = f"{a_block(layout)}.A"

    keyboard.types("nonesuch.A occupied")
    keyboard.types(f"{end} occupied")

    assert drained(
        witness, lambda: rows(heard, f"{SENSOR}/{end}") != []
    ), "the line after the typo never reached the broker"
    assert rows(heard, f"{SENSOR}/nonesuch.A") == []
    assert "nonesuch" in client.said.getvalue()
    assert client.running, "a typo took the keyboard down"
    witness.close()


def test_the_input_ending_ends_it_with_the_last_line_published(
    broker: Broker, layout: Layout, keyboard: Keyboard, client: Client
) -> None:
    """Ctrl-D, or a file of readings running out: the whole of this process's
    work is its input, so it ends with it where an app ends on a signal.

    The line typed last is published on the way out. It is on the queue by the
    time the reader thread is finished, and it is as much a reading as any
    other — a person's last word before they walk away from the railroad.
    """
    witness, heard = watching(broker)
    client.start()
    assert client.up.wait(10), "it never came up"
    end = f"{a_block(layout)}.B"

    keyboard.types(f"{end} occupied")
    keyboard.leaves()

    assert until(lambda: not client.running, 10), "it outlived its own input"
    assert drained(
        witness, lambda: rows(heard, f"{SENSOR}/{end}") != []
    ), "the last line typed was dropped on the way out"
    assert rows(heard, f"{SENSOR}/{end}")[-1]["occupancy"] == "occupied"
    witness.close()


def test_a_stop_ends_it_with_nothing_published_after(
    broker: Broker, layout: Layout, keyboard: Keyboard, client: Client
) -> None:
    """The other way it ends, which is the suite's and the deployment's
    signal: the loop stops, and a line typed at a process that is no longer
    reading reaches nobody."""
    witness, heard = watching(broker)
    client.start()
    assert client.up.wait(10), "it never came up"
    end = f"{a_block(layout)}.A"

    client.stop()
    keyboard.types(f"{end} occupied")

    settle(witness)
    assert rows(heard, f"{SENSOR}/{end}") == []


# -- the command a person types ----------------------------------------------


class Store:
    """The railroad's documents served on a port of its own, as the store on
    some other box serves them: this reads one over HTTP, having no store of
    its own to import (ADR-0059, decision 5)."""

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
def store(tmp_path: Path) -> Iterator[Store]:
    """An installation holding one railroad's drawing, and nothing else: one
    document is the whole of what a keyboard reads, since what it needs to
    know is which block ends exist."""
    name = railroads()[0]
    (tmp_path / "layouts").mkdir()
    shutil.copy(
        ASSETS / "layouts" / f"{name}.drawing.yaml",
        tmp_path / "layouts" / f"{name}.drawing.yaml",
    )
    serving = Store(tmp_path)
    serving.start()
    try:
        yield serving
    finally:
        serving.stop()


def test_the_command_reads_the_railroad_off_the_store_and_publishes_to_the_broker(
    broker: Broker, store: Store, layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The three flags of the command, end to end: the broker it publishes to,
    the railroad whose block ends a line is checked against, and the store that
    serves that railroad's drawing.

    Its input is a file of readings that runs out, which is what ends it, so
    the command returns of its own accord.
    """
    witness, heard = watching(broker)
    end = f"{a_block(layout)}.A"
    monkeypatch.setattr(sys, "stdin", io.StringIO(f"{end} occupied\n"))
    out = io.StringIO()

    assert (
        main(
            [
                "readings",
                "--broker",
                f"127.0.0.1:{broker.port}",
                "--railroad",
                railroads()[0],
                "--store",
                store.url,
            ],
            out,
        )
        == 0
    )

    assert drained(
        witness, lambda: rows(heard, f"{SENSOR}/{end}") != []
    ), "the command published nothing to the broker it was given"
    assert rows(heard, f"{SENSOR}/{end}")[-1]["addr"] == end
    witness.close()


def test_a_broker_that_is_not_an_address_is_refused_before_anything_is_read() -> None:
    """The refusal a person mistyping gets, in the words `lib` uses for every
    other app's flag, and before a store is asked for anything: a command that
    cannot publish has nothing to do."""
    out = io.StringIO()
    assert (
        main(
            [
                "readings",
                "--broker",
                "nonesuch",
                "--railroad",
                "x",
                "--store",
                "http://",
            ],
            out,
        )
        == 2
    )
    assert "not a broker address" in out.getvalue()
