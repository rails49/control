"""Tests at the store client: an app in its own process reading its railroad.

Against a real store on a real socket, because what is under test is the two
faces meeting — the route the store serves and what `lib` makes of the reply
— and a fake of either would only agree with itself.
"""

import shutil
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tc49.lib.documents import Documents
from tc49.store import AssetStore
from tc49.store.server import make_server
from tests.harness import ASSETS, catalogued

RAILROAD = "crossover-yard"


def _free_port() -> int:
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        return int(held.getsockname()[1])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with one railroad on it: its drawing, its roster and
    the catalogue the roster's cars name."""
    catalogued(tmp_path)
    (tmp_path / "layouts").mkdir()
    for suffix in ("drawing", "roster"):
        shutil.copy(
            ASSETS / "layouts" / f"{RAILROAD}.{suffix}.yaml",
            tmp_path / "layouts" / f"{RAILROAD}.{suffix}.yaml",
        )
    return tmp_path


@pytest.fixture
def url(root: Path) -> Iterator[str]:
    """That store, served, for as long as the test wants it."""
    server = make_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def client(url: str, said: list[str] | None = None) -> Documents:
    """One with a store that is expected to be there: a wait is milliseconds,
    not seconds, and what it said is kept where a test can read it."""
    return Documents(
        url,
        log=(said if said is not None else []).append,
        first_backoff_s=0.01,
        max_backoff_s=0.05,
    )


def test_the_layout_is_the_one_the_store_derives(url: str, root: Path) -> None:
    """The whole of what the route is for: an app that cannot import the
    store gets the layout the store would have handed it (ADR-0059
    decision 5)."""
    assert client(url).layout(RAILROAD) == AssetStore(root).get(RAILROAD)


def test_the_roster_is_merged_against_the_installations_catalogue(
    url: str, root: Path
) -> None:
    """Two documents and one answer: a car is only complete against the model
    it names, and the merge is `lib/stock.py`'s wherever the documents came
    from (ADR-0045)."""
    assert client(url).roster(RAILROAD) == AssetStore(root).roster(RAILROAD)


def test_the_catalogue_is_the_models_the_installation_knows(
    url: str, root: Path
) -> None:
    assert client(url).catalogue() == AssetStore(root).catalogue()


def test_a_railroad_with_no_drawing_is_not_found(url: str) -> None:
    """An answer, so it ends the waiting rather than being retried: what would
    change it is a person drawing something."""
    said: list[str] = []
    with pytest.raises(FileNotFoundError, match="atlantis"):
        client(url, said).layout("atlantis")
    assert said == []


def test_a_drawing_that_does_not_derive_is_raised_with_the_stores_words(
    url: str, root: Path
) -> None:
    """The other answer an app has to say out loud and stop on: the railroad
    is drawn and does not describe a layout yet (ADR-0050)."""
    store = AssetStore(root)
    doc = store.drawing(RAILROAD)
    doc["wires"] = doc["wires"][:-1]
    store.put(doc)
    with pytest.raises(ValueError) as refused:
        client(url).layout(RAILROAD)
    assert "crossover-yard" in str(refused.value)


def test_it_returns_once_the_store_comes_up_after_it_was_asked(root: Path) -> None:
    """An app coming up before the store is an ordinary state: the request
    waits, says so on stderr, and is answered when the store opens its socket
    (ADR-0059 decision 5, ADR-0050). No `depends_on` anywhere in compose,
    which is what this makes safe."""
    port = _free_port()
    said: list[str] = []
    answer: list[Any] = []
    asking = threading.Thread(
        target=lambda: answer.append(
            client(f"http://127.0.0.1:{port}", said).layout(RAILROAD)
        ),
        daemon=True,
    )
    asking.start()
    waiting = time.monotonic() + 5
    while not said and time.monotonic() < waiting:  # asked, nothing to answer
        time.sleep(0.01)
    assert said, "the client did not wait for a store that was not there"

    server = make_server(root, port=port)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        asking.join(timeout=10)
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=5)

    assert not asking.is_alive()
    assert answer == [AssetStore(root).get(RAILROAD)]
    assert "retrying" in said[0]
