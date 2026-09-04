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

Loading another railroad while the apps run is the other half of the same
rule and is `test_reload.py`.
"""

import shutil
import urllib.request
from collections.abc import Iterator
from json import loads
from pathlib import Path

import pytest

from tc49.lib.mqtt import MqttBus
from tests.apps import APPS, App, Process, Store
from tests.brokers import Broker, drained, settle, until
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
store client's own backoff, which doubles from half a second
(`lib/documents.py`) and is the deployed one here: this is the deployment, so
nothing is shortened to suit the suite."""


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


@pytest.fixture
def store(root: Path, tmp_path: Path) -> Iterator[Store]:
    serving = Store(root, tmp_path / "store.log")
    try:
        yield serving
    finally:
        serving.stop()


@pytest.mark.parametrize("app", APPS, ids=[app.name for app in APPS])
def test_an_app_comes_up_alone_and_leaves_its_rows_retained(
    app: App, broker: Broker, store: Store, tmp_path: Path
) -> None:
    """Started against nothing, it waits rather than exits; given what it
    reads, it publishes its own rows and nobody else's, and a client that
    arrives afterwards is handed them."""
    running: Process = app.process(broker, store, RAILROAD, tmp_path)
    running.start()
    try:
        # Nothing is up but the broker, and for the two apps that read no
        # documents not even that is missing: either way the app stays.
        assert not until(
            lambda: not running.running, ALONE_S
        ), f"'{app.name}' exited rather than waiting:\n{running.said()}"
        if app.store:
            store.start()

        # A client that connects after it published, which is the only way to
        # tell a retained row from a message that happened to be in flight.
        late = MqttBus(port=broker.port)
        assert late.wait_connected(), "the witness never reached the broker"
        late.subscribe("tc49/#", lambda topic, payload: None)
        assert drained(
            late,
            lambda: set(app.rows) <= set(late.last_values),
            timeout=UP_S,
        ), f"'{app.name}' never published {sorted(app.rows)}:\n{running.said()}"

        # And nothing else: with no other app running, every row the broker
        # holds is this one's (ADR-0035).
        settle(late)
        assert set(late.last_values) == set(
            app.rows
        ), f"'{app.name}' left a row it does not own"
        assert running.running, f"'{app.name}' stopped on its own:\n{running.said()}"
        late.close()
    finally:
        running.stop()


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
