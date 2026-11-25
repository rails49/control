"""Tests at the store client: an app in its own process reading its railroad.

Against a real store on a real socket, because what is under test is the two
faces meeting — the route the store serves and what `lib` makes of the reply
— and a fake of either would only agree with itself.
"""

import shutil
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from rails49_testing.ports import free_port

from tc49.lib.documents import Documents, reread_roster
from tc49.lib.fast_clock import KeptClock
from tc49.lib.settings import (
    ARRIVAL_ALLOWANCE_S,
    SENSOR_SILENCE_S,
    KeptInstallation,
    KeptSettings,
)
from tc49.lib.timetable import Entry, Timetable, TrainStart
from tc49.store import AssetStore
from tc49.store.server import make_server
from tests.harness import ASSETS, catalogued

RAILROAD = "crossover-yard"


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


def test_the_loaded_railroad_is_what_was_put(url: str) -> None:
    """The binding's record of what it loaded, read back as it starts
    (ADR-0072 decision 5); nothing recorded is no railroad."""
    documents = client(url)
    assert documents.loaded() == ""
    documents.put_loaded(RAILROAD)
    assert documents.loaded() == RAILROAD


def test_a_loaded_record_the_store_refuses_is_raised(url: str) -> None:
    with pytest.raises(ValueError, match="railroad"):
        client(url).put_loaded("")


def test_the_clock_a_railroad_keeps_is_what_was_put(url: str) -> None:
    """None where it keeps none, which starts it at the box's wall time
    (ADR-0090, decision 4)."""
    documents = client(url)
    assert documents.clock(RAILROAD) is None
    kept = KeptClock(start=(12 * 60 + 30) * 60, speed_up=8.0)
    documents.put_clock(RAILROAD, kept)
    assert documents.clock(RAILROAD) == kept


def test_a_kept_clock_the_store_cannot_read_is_raised(url: str, root: Path) -> None:
    (root / "layouts" / f"{RAILROAD}.clock.yaml").write_text("start: 12:30\n")
    with pytest.raises(ValueError, match="clock"):
        client(url).clock(RAILROAD)


def test_it_returns_once_the_store_comes_up_after_it_was_asked(root: Path) -> None:
    """An app coming up before the store is an ordinary state: the request
    waits, says so on stderr, and is answered when the store opens its socket
    (ADR-0059 decision 5, ADR-0050). No `depends_on` anywhere in compose,
    which is what this makes safe."""
    port = free_port()
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


def test_a_roster_read_once_raises_where_no_store_answers() -> None:
    """The read a running app makes for a train it has not got: one attempt,
    because a bus loop waiting on the store would stop the railroad
    (ADR-0092, decision 1)."""
    said: list[str] = []

    with pytest.raises(ConnectionError):
        client(f"http://127.0.0.1:{free_port()}", said).roster(RAILROAD, once=True)

    assert said == []


def test_a_roster_read_once_is_the_roster(url: str, root: Path) -> None:
    assert client(url).roster(RAILROAD, once=True) == AssetStore(root).roster(RAILROAD)


def test_the_roster_read_again_is_the_stores(url: str, root: Path) -> None:
    said: list[str] = []

    read = reread_roster(client(url), RAILROAD, said.append)()

    assert read == AssetStore(root).roster(RAILROAD)
    assert said == []


def test_a_store_that_does_not_answer_reads_no_roster_and_says_so() -> None:
    """One attempt and no wait: the bus loop asks this on its own thread."""
    said: list[str] = []
    documents = client(f"http://127.0.0.1:{free_port()}")

    assert reread_roster(documents, RAILROAD, said.append)() is None
    assert len(said) == 1 and "not read again" in said[0]


def test_the_settings_a_railroad_keeps_are_what_was_put(url: str) -> None:
    """None where it keeps none, which loads it at the defaults (#1126)."""
    documents = client(url)
    assert documents.settings(RAILROAD) is None
    documents.put_settings(RAILROAD, KeptSettings(2.5))
    assert documents.settings(RAILROAD) == KeptSettings(2.5)


def test_the_speeds_a_railroad_keeps_are_what_was_put(url: str) -> None:
    documents = client(url)
    kept = KeptSettings(1.0, {"clear": 0.8, "caution": 0.2})
    documents.put_settings(RAILROAD, kept)
    assert documents.settings(RAILROAD) == kept


def test_the_installations_settings_are_what_was_put(url: str) -> None:
    """None where it keeps none, which runs at the defaults (#1132)."""
    documents = client(url)
    assert documents.installation() is None
    documents.put_installation(KeptInstallation(10.0))
    assert documents.installation() == KeptInstallation(10.0)


def test_the_installations_sensor_silence_is_kept_beside_the_throttle_silence(
    url: str, root: Path
) -> None:
    """Each document says both, so setting one leaves the other (#1149)."""
    documents = client(url)
    documents.put_installation(KeptInstallation(10.0, 20.0))
    assert documents.installation() == KeptInstallation(10.0, 20.0)
    assert yaml.safe_load((root / "installation.yaml").read_text()) == {
        "throttle_silence": 10.0,
        "sensor_silence": 20.0,
        "arrival_allowance": ARRIVAL_ALLOWANCE_S,
    }


def test_an_installation_without_a_sensor_silence_reads_at_the_default(
    url: str, root: Path
) -> None:
    """A document giving only its throttle silence keeps what it gives and
    comes up at the default for the rest (#1149)."""
    (root / "installation.yaml").write_text("throttle_silence: 12\n")
    assert client(url).installation() == KeptInstallation(12.0, SENSOR_SILENCE_S)


def test_a_sensor_silence_the_store_cannot_read_is_raised(url: str, root: Path) -> None:
    (root / "installation.yaml").write_text("sensor_silence: 1\n")
    with pytest.raises(ValueError, match="sensor_silence"):
        client(url).installation()


def test_the_installations_arrival_allowance_is_kept_beside_the_silences(
    url: str, root: Path
) -> None:
    """A document with all three reads all three (#1188)."""
    (root / "installation.yaml").write_text(
        "throttle_silence: 10\nsensor_silence: 20\narrival_allowance: 120\n"
    )
    assert client(url).installation() == KeptInstallation(10.0, 20.0, 120.0)


def test_an_installation_without_an_arrival_allowance_reads_at_sixty(
    url: str, root: Path
) -> None:
    """A document giving its two silences alone keeps what it gives and comes
    up at the default allowance (#1188)."""
    (root / "installation.yaml").write_text(
        "throttle_silence: 10\nsensor_silence: 20\n"
    )
    assert client(url).installation() == KeptInstallation(10.0, 20.0, 60.0)


def test_an_arrival_allowance_the_store_cannot_read_is_raised(
    url: str, root: Path
) -> None:
    (root / "installation.yaml").write_text("arrival_allowance: 4\n")
    with pytest.raises(ValueError, match="arrival_allowance"):
        client(url).installation()


def test_a_settings_document_with_short_blocks_reads_it(url: str, root: Path) -> None:
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text(
        "point_gap: 1\nshort_blocks: true\n"
    )
    assert client(url).settings(RAILROAD) == KeptSettings(1.0, short_blocks=True)


def test_a_settings_document_without_short_blocks_reads_false(
    url: str, root: Path
) -> None:
    """A document kept before there was the setting: the length check on
    (#1286)."""
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text("point_gap: 1\n")
    kept = client(url).settings(RAILROAD)
    assert kept is not None
    assert kept.short_blocks is False


def test_short_blocks_the_store_cannot_read_is_raised(url: str, root: Path) -> None:
    """`1` is a number, not `true` (#1286)."""
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text(
        "point_gap: 1\nshort_blocks: 1\n"
    )
    with pytest.raises(ValueError, match="short_blocks"):
        client(url).settings(RAILROAD)


def test_the_short_blocks_a_railroad_keeps_is_what_was_put(url: str) -> None:
    documents = client(url)
    kept = KeptSettings(1.0, short_blocks=True)
    documents.put_settings(RAILROAD, kept)
    assert documents.settings(RAILROAD) == kept


def test_a_settings_document_with_without_sensors_reads_it(
    url: str, root: Path
) -> None:
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text(
        "point_gap: 1\nwithout_sensors: true\n"
    )
    assert client(url).settings(RAILROAD) == KeptSettings(1.0, without_sensors=True)


def test_a_settings_document_without_without_sensors_reads_false(
    url: str, root: Path
) -> None:
    """The railroad runs by its sensors (#1316)."""
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text("point_gap: 1\n")
    kept = client(url).settings(RAILROAD)
    assert kept is not None
    assert kept.without_sensors is False


def test_without_sensors_the_store_cannot_read_is_raised(url: str, root: Path) -> None:
    """`1` is a number, not `true` (#1316)."""
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text(
        "point_gap: 1\nwithout_sensors: 1\n"
    )
    with pytest.raises(ValueError, match="without_sensors"):
        client(url).settings(RAILROAD)


def test_the_without_sensors_a_railroad_keeps_is_what_was_put(url: str) -> None:
    documents = client(url)
    kept = KeptSettings(1.0, short_blocks=True, without_sensors=True)
    documents.put_settings(RAILROAD, kept)
    assert documents.settings(RAILROAD) == kept


def test_installation_settings_the_store_cannot_read_are_raised(
    url: str, root: Path
) -> None:
    (root / "installation.yaml").write_text("throttle_silence: 1\n")
    with pytest.raises(ValueError, match="throttle_silence"):
        client(url).installation()


def test_kept_settings_the_store_cannot_read_are_raised(url: str, root: Path) -> None:
    (root / "layouts" / f"{RAILROAD}.settings.yaml").write_text("point_gap: 9\n")
    with pytest.raises(ValueError, match="point_gap"):
        client(url).settings(RAILROAD)


EVENING = Timetable(
    "evening",
    RAILROAD,
    6 * 3600,
    {"freight_1": TrainStart("yard_w", "A-to-B")},
    (
        Entry((6 * 60 + 2) * 60, "freight_1", ("dn_e", "up_e"), 2, "meets the express"),
        Entry((12 * 60 + 30) * 60, "freight_1"),
    ),
)
"""A timetable of the railroad (#1345): a run with a dwell and a note, and a
turn-round at a time YAML 1.1 reads as a number unquoted."""


def test_the_timetable_a_railroad_keeps_is_what_was_put(url: str, root: Path) -> None:
    """None where the store has none, and filed by the railroad and the name
    the timetable gives."""
    documents = client(url)
    assert documents.timetable(RAILROAD, "evening") is None
    documents.put_timetable(EVENING)
    assert documents.timetable(RAILROAD, "evening") == EVENING
    assert (root / "timetables" / RAILROAD / "evening.timetable.yaml").exists()


def test_a_timetable_put_again_replaces_the_one_before(url: str) -> None:
    documents = client(url)
    documents.put_timetable(EVENING)
    shorter = EVENING.removed(1)
    documents.put_timetable(shorter)
    assert documents.timetable(RAILROAD, "evening") == shorter


def test_a_deleted_timetable_is_one_the_store_has_not_got(url: str) -> None:
    documents = client(url)
    documents.put_timetable(EVENING)
    documents.delete_timetable(RAILROAD, "evening")
    assert documents.timetable(RAILROAD, "evening") is None


def test_deleting_a_timetable_the_store_has_not_got_is_no_error(url: str) -> None:
    """A delete whose answer was lost is asked again, and by then the
    timetable is gone."""
    client(url).delete_timetable(RAILROAD, "evening")


def test_a_timetable_the_store_cannot_read_is_raised(url: str, root: Path) -> None:
    filed = root / "timetables" / RAILROAD
    filed.mkdir(parents=True)
    (filed / "evening.timetable.yaml").write_text(
        f"timetable: evening\nlayout: {RAILROAD}\nstart: 12:30\n"
        "trains: {}\nentries: []\n"
    )
    with pytest.raises(ValueError, match="HH:MM"):
        client(url).timetable(RAILROAD, "evening")


def test_a_timetable_is_deleted_once_the_store_comes_up(root: Path) -> None:
    """A write and a delete wait for a store that does not answer, as a read
    does."""
    AssetStore(root).put_timetable(EVENING.document(), RAILROAD, "evening")
    port = free_port()
    said: list[str] = []
    asking = threading.Thread(
        target=lambda: client(f"http://127.0.0.1:{port}", said).delete_timetable(
            RAILROAD, "evening"
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
    assert AssetStore(root).timetables(RAILROAD) == []
