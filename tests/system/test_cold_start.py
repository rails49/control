"""Every app comes up alone, as a process, against an empty broker.

Each app's own suite calls its `serve` on a thread, which tests the app. This
tests the **deployment**: the command line a compose service runs, in a
process of its own started by nothing and depending on nothing, against a
real `mosquitto` on a free port with no store and no other app up (ADR-0059,
decision 5). What decays silently is exactly that — an app that quietly grows
an order it has to be started in still passes its own suite, because its suite
constructs whatever it needs first.

So each app is started with nothing there, left alone for a few seconds, and
only then given a store. What it owns is asserted from a client that connects
**after** it published: a row a late subscriber is handed is a retained row,
and being handed it is what a browser opened an hour into a run depends on
(ADR-0032, ADR-0059 decision 3). Nothing else is running, so everything the
broker holds is this app's, and the assertion is on the whole of it — an app
that leaves a row it does not own behind fails here.

The reload of ADR-0060 — the same app reaching the same state a second time
on another railroad, having cleared the first one's rows — is not checked
here: no app follows a change of `tc49/layout/state/railroad` yet, that
being the work the ADR leaves to the communication issue after this one.
"""

import shutil
import subprocess
import sys
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from json import loads
from pathlib import Path

import pytest

from tc49.lib.mqtt import MqttBus
from tests.brokers import Broker, drained, free_port, listening, settle, until
from tests.harness import ASSETS, catalogued

RAILROAD = "crossover-yard"
"""The railroad the store is given, where the apps that read documents read
theirs. Which one it is decides nothing here — what is under test is the
process — so it is the one the rest of the suite draws on."""

ALONE_S = 3.0
"""How long an app is left with no store and nothing else on the broker
before anything is asserted. A few seconds, because what this catches is an
app that exits over something missing, and an exit like that is immediate."""

UP_S = 30.0
"""How long an app is given to publish, once it has everything. It covers the
store client's own backoff, which doubles from half a second (`lib/documents`)
and is the deployed one here: this is the deployment, so nothing is shortened
to suit the suite."""


@dataclass(frozen=True)
class Cold:
    """One app's cold start: how it is started, and what it leaves retained.

    The flags are the app's own — `dccex` takes a station and no railroad
    (hardware needs no layout, ADR-0059 decision 5), the driver reads no
    documents and so takes no store. A table rather than six tests, because
    what is being asserted is one rule and the differences between the apps
    are the rule's own consequences.
    """

    app: str
    rows: tuple[str, ...]
    railroad: bool = True
    store: bool = False
    station: bool = False


COLD = (
    Cold(
        "scheduler",
        store=True,
        rows=("tc49/schedule/state/facing", "tc49/schedule/state/exhausted"),
    ),
    Cold(
        "dispatcher",
        store=True,
        rows=(
            "tc49/dispatch/state/run",
            "tc49/dispatch/state/allocation",
            "tc49/dispatch/state/aspects",
            "tc49/dispatch/state/disputed",
        ),
    ),
    Cold("driver", rows=()),
    Cold(
        "layout",
        store=True,
        rows=(
            "tc49/layout/state/railroad",
            "tc49/layout/state/power",
            "tc49/layout/state/mode",
            "tc49/layout/state/wanted/track",
        ),
    ),
    Cold(
        "simulator",
        store=True,
        rows=("tc49/layout/state/railroad", "tc49/layout/state/power"),
    ),
    Cold(
        "dccex",
        railroad=False,
        station=True,
        rows=(
            "tc49/layout/state/device/track",
            "tc49/layout/state/device/link/dccex",
        ),
    ),
)
"""The six apps of ADR-0059, and the rows each opens with.

`driver` opens with none: it holds no state and reads no documents, so
silence is its cold start. `layout` writes no desired speed here although it
zeroes one per address it finds: on an empty broker there is nothing to zero,
which is the difference between this and a restart.
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it, as the store on the layout
    box holds one: a drawing, a roster and the catalogue its cars name."""
    root = tmp_path / "store"
    root.mkdir()
    catalogued(root)
    (root / "layouts").mkdir()
    for suffix in ("drawing", "roster"):
        shutil.copy(
            ASSETS / "layouts" / f"{RAILROAD}.{suffix}.yaml",
            root / "layouts" / f"{RAILROAD}.{suffix}.yaml",
        )
    return root


def tc49() -> str:
    """The `tc49` script, as compose's store service runs it: the one beside
    the interpreter running this suite, so a checkout with two environments
    serves the store from the one under test."""
    beside = Path(sys.executable).with_name("tc49")
    return str(beside) if beside.exists() else "tc49"


class Process:
    """One process, started and stopped as a container's is.

    Its output goes to a file rather than a pipe: a pipe nobody reads fills
    and stops the app it was meant to watch, and what these tests want it for
    is a failure's message.
    """

    def __init__(self, command: list[str], log: Path) -> None:
        self._command = command
        self._log = log
        self._running: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self._log.touch()
        with self._log.open("wb") as out:
            self._running = subprocess.Popen(
                self._command, stdout=out, stderr=subprocess.STDOUT
            )

    @property
    def running(self) -> bool:
        return self._running is not None and self._running.poll() is None

    def said(self) -> str:
        """Everything it has printed, for a failure to quote."""
        return self._log.read_text(errors="replace")

    def stop(self) -> None:
        """SIGTERM, which is how a container is stopped, and then a wait: an
        app that does not end on it is a defect of its own."""
        if self._running is None:
            return
        self._running.terminate()
        self._running.wait(timeout=10)
        self._running = None


class Store:
    """The store's face, started the same way and startable late: `tc49
    serve` on a port of its own, over a root this test made."""

    def __init__(self, root: Path, log: Path) -> None:
        self.port = free_port()
        self._process = Process(
            [
                tc49(),
                "serve",
                "--store",
                str(root),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            log,
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._process.start()
        assert until(lambda: listening(self.port), UP_S), self._process.said()

    def stop(self) -> None:
        self._process.stop()


@pytest.fixture
def store(root: Path, tmp_path: Path) -> Iterator[Store]:
    serving = Store(root, tmp_path / "store.log")
    try:
        yield serving
    finally:
        serving.stop()


def command(cold: Cold, broker: Broker, store: Store) -> list[str]:
    """What a compose service for this app runs, as it runs it."""
    args = [sys.executable, "-m", f"tc49.{cold.app}"]
    args += ["--broker", f"127.0.0.1:{broker.port}"]
    if cold.railroad:
        args += ["--railroad", RAILROAD]
    if cold.store:
        args += ["--store", store.url]
    if cold.station:
        # An address nothing answers on: a translator whose command station
        # is not there reports the link it cannot make and stays up
        # (ADR-0050), and no test of ours needs hardware.
        args += ["--station", f"127.0.0.1:{free_port()}"]
    return args


@pytest.mark.parametrize("cold", COLD, ids=[cold.app for cold in COLD])
def test_an_app_comes_up_alone_and_leaves_its_rows_retained(
    cold: Cold, broker: Broker, store: Store, tmp_path: Path
) -> None:
    """Started against nothing, it waits rather than exits; given what it
    reads, it publishes its own rows and nobody else's, and a client that
    arrives afterwards is handed them."""
    app = Process(command(cold, broker, store), tmp_path / f"{cold.app}.log")
    app.start()
    try:
        # Nothing is up but the broker, and for the two apps that read no
        # documents not even that is missing: either way the app stays.
        assert not until(
            lambda: not app.running, ALONE_S
        ), f"'{cold.app}' exited rather than waiting:\n{app.said()}"
        if cold.store:
            store.start()

        # A client that connects after it published, which is the only way to
        # tell a retained row from a message that happened to be in flight.
        late = MqttBus(port=broker.port)
        assert late.wait_connected(), "the witness never reached the broker"
        late.subscribe("tc49/#", lambda topic, payload: None)
        assert drained(
            late,
            lambda: set(cold.rows) <= set(late.last_values),
            timeout=UP_S,
        ), f"'{cold.app}' never published {sorted(cold.rows)}:\n{app.said()}"

        # And nothing else: with no other app running, every row the broker
        # holds is this one's (ADR-0035).
        settle(late)
        assert set(late.last_values) == set(
            cold.rows
        ), f"'{cold.app}' left a row it does not own"
        assert app.running, f"'{cold.app}' stopped on its own:\n{app.said()}"
        late.close()
    finally:
        app.stop()


def test_the_stores_face_comes_up_on_an_empty_root(tmp_path: Path) -> None:
    """The store started the way the apps are, over a root with nothing in
    it: a fresh box, before anybody has drawn a railroad. It answers rather
    than refusing, which is what makes the editor the way a first railroad is
    drawn (#320)."""
    empty = tmp_path / "empty"
    empty.mkdir()
    serving = Store(empty, tmp_path / "store.log")
    serving.start()
    try:
        with urllib.request.urlopen(f"{serving.url}/drawings", timeout=5) as answer:
            listed = loads(answer.read())
        assert listed == {"drawings": []}
    finally:
        serving.stop()
