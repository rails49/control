"""Another railroad is loaded while the apps run, and each reaches the same
state a second time (ADR-0060).

The apps are not restarted. `tc49/layout/state/railroad` moves to another
name and every app follows it: the app built on the railroad that is leaving
stops answering, the retained rows it owns are **cleared**, and it is built
again on the new one. Asserting that new rows appeared is not enough — a
stale row for a block or an address the new railroad does not have is exactly
the failure the reload introduces, is invisible to a cold-start check, and is
what a page opened afterwards reads. So the whole retained picture is read
back and the railroad that left may not be named anywhere in it.

Processes again rather than threads, for the reason `test_cold_start.py`
gives: what a container does when the row moves is what is under test, and
the sentence each app prints when it is up on the new railroad is how a test
knows the reload has finished.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from tc49.lib.bus import Payload
from tc49.lib.mqtt import MqttBus
from tests.apps import APPS, App, Process, Store
from tests.brokers import Broker, settle, until
from tests.harness import ASSETS, catalogued

WAS = "crossover-yard"
NOW = "single-track-meet"
"""Two railroads that share no block name, which is what makes a row left
over from the first legible in the second. Both are the committed fixtures:
what is under test is the reload and not the drawing."""

RAILROAD = "tc49/layout/state/railroad"

WAS_BLOCKS = ("yard_w", "yard_e", "up_w", "up_e", "dn_w", "dn_e")
"""Every block of the railroad that leaves. None of them is a block of the
one that arrives, so a retained picture naming one of these is a picture with
a stale row in it."""

WAS_TRAIN = "freight_1"
NOW_TRAIN = "runner"

UP_S = 30.0
"""How long a reload is given: the app reads two documents off the store,
waits out its own window for the rows the broker holds, and builds. Generous
because a failure here is asserted on the log rather than waited for."""

STALE_TRACTION = "tc49/layout/state/wanted/traction/17"
"""A desired speed for an address neither railroad's roster has, as a
previous railroad's would be — the row nothing republishes and nothing else
drops."""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """An installation with both railroads on it: one loaded, one to load,
    which is the state a person picking from the band is in (ADR-0060)."""
    root = tmp_path / "store"
    root.mkdir()
    catalogued(root)
    (root / "layouts").mkdir()
    for railroad in (WAS, NOW):
        for suffix in ("drawing", "roster"):
            shutil.copy(
                ASSETS / "layouts" / f"{railroad}.{suffix}.yaml",
                root / "layouts" / f"{railroad}.{suffix}.yaml",
            )
    return root


@pytest.fixture
def store(root: Path, tmp_path: Path) -> Iterator[Store]:
    serving = Store(root, tmp_path / "store.log")
    serving.start()
    try:
        yield serving
    finally:
        serving.stop()


def named(app: str) -> App:
    """One of the six by name, so a test reads as the app it is about."""
    return next(one for one in APPS if one.name == app)


def started(app: str, broker: Broker, store: Store, tmp_path: Path) -> Process:
    """The app up on the railroad that is about to leave."""
    running = named(app).process(broker, store, WAS, tmp_path)
    running.start()
    try:
        up_on(running, WAS)
    except AssertionError:
        running.stop()
        raise
    return running


def hand(broker: Broker) -> MqttBus:
    """A client that is nobody: a page, another app, a person with a shell.
    Nothing here says who published, and no app asks (SYSTEM.md, rule 4)."""
    bus = MqttBus(port=broker.port)
    assert bus.wait_connected(), "the hand never reached the broker"
    return bus


def load(bus: MqttBus, railroad: str) -> None:
    """The gesture under test: the row that says which railroad this broker
    runs, moved. Retained, as every state row is, so an app that is
    restarted afterwards comes up on the railroad the row names."""
    bus.publish(RAILROAD, {"name": railroad})


def up_on(running: Process, railroad: str) -> None:
    """Wait until the app says it is up on `railroad`. The log line rather
    than a row, because it is the one signal every app has — the driver owns
    no row at all — and because it says the rebuild is finished rather than
    started."""
    assert until(
        lambda: f"up on '{railroad}'" in running.said(), UP_S
    ), f"it never came up on '{railroad}':\n{running.said()}"


def picture(broker: Broker) -> dict[str, Payload]:
    """Everything the broker holds, as a client that connects now is handed
    it: the whole retained state of the railroad, which is what a page opened
    after the reload reads (ADR-0032)."""
    late = MqttBus(port=broker.port)
    assert late.wait_connected(), "the witness never reached the broker"
    late.subscribe("tc49/#", lambda topic, payload: None)
    settle(late)
    held = late.last_values
    late.close()
    return held


def no_trace_of_the_old_railroad(held: dict[str, Payload]) -> None:
    """No row and no payload names a block of the railroad that left. The
    whole picture and not the rows one app owns: a stale row is stale
    wherever it is, and the point of the check is that nothing has to know
    where to look (ADR-0060)."""
    written = json.dumps({topic: held[topic] for topic in sorted(held)})
    left = sorted(
        block
        for block in WAS_BLOCKS
        if f'"{block}' in written or f"/{block}" in written
    )
    assert not left, f"the picture still names {left} of '{WAS}':\n{written}"


def test_the_scheduler_clears_the_facing_it_held_and_rebuilds(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """The facing is the scheduler's whole retained state, and it is keyed by
    train and by block end. A rebuild alone would **adopt** it — that is what
    a restart under a running railroad is for (#123) — so a reload that only
    rebuilt would carry a departure end of the old railroad into the new
    one."""
    running = started("scheduler", broker, store, tmp_path)
    try:
        writing = hand(broker)
        writing.publish(
            "tc49/schedule/state/facing",
            {"facing": {WAS_TRAIN: "yard_w.A-to-B"}},
        )
        assert until(lambda: "tc49/schedule/state/facing" in writing.last_values)

        load(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        assert held["tc49/schedule/state/facing"]["facing"] == {}
        assert held["tc49/schedule/state/exhausted"]["exhausted"] is True
        no_trace_of_the_old_railroad(held)

        # And it is the new railroad's scheduler: a train only the new one
        # has, placed on a block only the new one has, is answered.
        writing.publish(
            "tc49/dispatch/train_placed", {"train": NOW_TRAIN, "block": "west_1"}
        )
        assert until(
            lambda: picture(broker)["tc49/schedule/state/facing"]["facing"] != {}, UP_S
        ), f"it did not come up on '{NOW}':\n{running.said()}"
        writing.close()
    finally:
        running.stop()


def test_the_dispatcher_clears_the_picture_it_held_and_rebuilds(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """The allocation is the run's whole picture, keyed by train and by
    block, and a rebuild adopts it (#123). After a reload no train is placed:
    a person puts them back through the stock view, the same path as a
    railroad opened for the first time (ADR-0060).

    What this catches is an app that ignores the row. It does not separately
    catch one that rebuilds without clearing, and cannot: adoption is checked
    against the new railroad's layout and roster, so a train standing in a
    block that railroad does not have is dropped on the way in either way.
    The clearing still happens — it is what makes the picture right for the
    apps whose rows are not checked like this, and the scheduler's facing
    below is one of them.
    """
    running = started("dispatcher", broker, store, tmp_path)
    try:
        writing = hand(broker)
        writing.publish(
            "tc49/dispatch/state/allocation",
            {
                "trains": {WAS_TRAIN: "yard_w"},
                "crossing": {},
                "locks": {"yard_w": WAS_TRAIN},
                "requests": [],
            },
        )
        assert until(lambda: "tc49/dispatch/state/allocation" in writing.last_values)

        load(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        allocation = held["tc49/dispatch/state/allocation"]
        assert (allocation["trains"], allocation["locks"]) == ({}, {})
        assert held["tc49/dispatch/state/run"]["run"] == "held"
        # Every signalled end is the new railroad's, which is the rebuild.
        signalled = held["tc49/dispatch/state/aspects"]["aspects"]
        assert signalled, "no aspects: it did not rebuild"
        no_trace_of_the_old_railroad(held)
        writing.close()
    finally:
        running.stop()


def test_the_layout_interface_clears_the_rows_it_asked_for_and_rebuilds(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """The desired rows are one per address, and the address is the old
    railroad's wiring: a speed for a locomotive the new railroad does not
    have is a row nothing republishes and nothing else drops. Zeroing is not
    clearing — a zeroed row is still a row, keyed to an address that is not
    there (ADR-0060)."""
    running = started("layout", broker, store, tmp_path)
    try:
        writing = hand(broker)
        writing.publish(STALE_TRACTION, {"addr": "17", "speed": 0.5})
        assert until(lambda: STALE_TRACTION in writing.last_values)

        load(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        assert STALE_TRACTION not in held, "the desired speed survived the reload"
        assert held[RAILROAD]["name"] == NOW
        assert held["tc49/layout/state/wanted/track"]["power"] == "off"
        assert held["tc49/layout/state/mode"]["modes"] == {}
        no_trace_of_the_old_railroad(held)
        writing.close()
    finally:
        running.stop()


def test_the_simulator_stands_in_for_the_new_railroads_steel(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """This binding's steel is the drawing it was built from, so another
    railroad is another simulator (ADR-0030). Both its rows are republished
    rather than left, so what this catches is an app that ignores the row and
    not one that fails to clear — this app owns no row keyed by anything the
    old railroad had."""
    running = started("simulator", broker, store, tmp_path)
    try:
        writing = hand(broker)
        load(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        assert held[RAILROAD]["name"] == NOW
        assert held["tc49/layout/state/power"]["power"] == "on"
        no_trace_of_the_old_railroad(held)
        writing.close()
    finally:
        running.stop()


def test_the_driver_rebuilds_and_still_owns_no_row(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """The driver holds no state and reads no documents, so it has nothing to
    clear and nothing to read: the reload is the transit it was in the middle
    of being dropped, that transit belonging to a railroad that is gone
    (ADR-0054). It follows the row all the same — an app that did not would
    go on driving the trains of a railroad nobody is running."""
    running = started("driver", broker, store, tmp_path)
    try:
        writing = hand(broker)
        load(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        assert set(held) == {RAILROAD}, "the driver published a row of its own"
        assert running.running, f"the driver stopped:\n{running.said()}"
        writing.close()
    finally:
        running.stop()


def test_the_translator_is_not_a_railroads_and_does_not_reload(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """Hardware needs no layout (ADR-0059, decision 5): this app takes no
    `--railroad`, reads no documents, and its two rows are the command
    station's rather than a railroad's — the link it has and the supply it
    reports. A railroad loaded under it changes nothing it could publish, so
    it stands, and its rows stand with it."""
    running = named("dccex").process(broker, store, WAS, tmp_path)
    running.start()
    assert until(lambda: "up as" in running.said(), UP_S), running.said()
    try:
        writing = hand(broker)
        before = picture(broker)
        load(writing, NOW)
        settle(writing)

        held = picture(broker)
        assert set(held) == set(before) | {RAILROAD}, "it answered a railroad"
        assert held["tc49/layout/state/device/link/dccex"]["link"] == "down"
        assert running.running, f"the translator stopped:\n{running.said()}"
        writing.close()
    finally:
        running.stop()
