"""Another railroad is loaded while the apps run, and each reaches the same
state a second time (ADR-0060).

The apps are not restarted. A person publishes `tc49/layout/railroad_wanted`,
the binding of the layout interface that is running answers it — that being
the one app bound to a railroad, and the writer of the row — and
`tc49/layout/state/railroad` moves. Every other app follows the **state** row
and never the gesture, so the five of them are driven here by moving the row
directly and the two bindings by the gesture, each the way a running system
reaches it.

Whichever way it arrives: the app built on the railroad that is leaving stops
answering, the retained rows it owns are **cleared**, and it is built again on
the new one. Asserting that new rows appeared is not enough — a stale row for
a block or an address the new railroad does not have is exactly the failure
the reload introduces, is invisible to a cold-start check, and is what a page
opened afterwards reads. So the whole retained picture is read back and the
railroad that left may not be named anywhere in it.

Processes again rather than threads, for the reason `test_cold_start.py`
gives: what a container does when the row moves is what is under test, and
the sentence each app prints when it is up on the new railroad is how a test
knows the reload has finished.

The one thing here that is not a process is the publisher of `device/sensor`:
there is none to start, and what it stands in for is the rule ADR-0063 states
— the names it publishes its sensors under are the drawing's, so it follows
the row like every other app that reads the store, while a translator that
reads nothing does not.
"""

import json
import shutil
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from tc49.lib.bus import Payload
from tc49.lib.inventory import OFF, ON
from tc49.lib.loading import Loaded
from tc49.lib.mqtt import MqttBus
from tests.apps import APPS, App, Process, Store
from tests.brokers import Broker, drained, settle, until
from tests.harness import ASSETS, catalogued

WAS = "crossover-yard"
NOW = "single-track-meet"
"""Two railroads that share no block name, which is what makes a row left
over from the first legible in the second. Both are the committed fixtures:
what is under test is the reload and not the drawing."""

RAILROAD = "tc49/layout/state/railroad"
WANTED = "tc49/layout/railroad_wanted"
POWER = "tc49/layout/state/power"

MISSING = "no-such-railroad"
"""A name the store does not list. Nothing derives from it and nothing ever
will: what it is for is the refusal (ADR-0050)."""

WAS_BLOCKS = ("yard_w", "yard_e", "up_w", "up_e", "dn_w", "dn_e")
"""Every block of the railroad that leaves. None of them is a block of the
one that arrives, so a retained picture naming one of these is a picture with
a stale row in it."""

WAS_TRAIN = "freight_1"
NOW_TRAIN = "runner"

WATCHED = "loop_up"
"""A block of the railroad that arrives, whose sensor at one end the hardware
knows by a name of its own."""

KNOWN_AS = "LS322"
"""What that hardware calls that sensor: a string of the system's making,
which is why the drawing carries it and the topic does not (ADR-0063)."""

ENDS = ("A", "B")
"""A block's two ends. Written out here rather than read off the drawing: a
publisher subscribes a sensor per end whatever the document says, the document
naming only the ends the hardware calls something else."""

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
    """The row that says which railroad this broker runs, moved. Retained, as
    every state row is, so an app that is restarted afterwards comes up on
    the railroad the row names.

    This is how the **followers** are driven: the five apps that watch the
    row and never the gesture behind it. The binding of the layout interface
    that is running is the row's writer and answers `railroad_wanted`
    instead, so it is driven by `pick` below (ADR-0060)."""
    bus.publish(RAILROAD, {"name": railroad})


def pick(bus: MqttBus, railroad: str) -> None:
    """The gesture a person makes: the railroad they want, on the topic the
    binding of the layout interface answers. An event and not a row — nothing
    hands it over a second time, and the state row moves only where the app
    that owns it takes this (ADR-0060)."""
    bus.publish(WANTED, {"railroad": railroad})


def picks(bus: MqttBus, railroad: str, running: Process) -> None:
    """The gesture, said again until the app is up on the railroad it names.

    For the case where the supply the gesture is conditional on was written
    by this same hand a moment earlier: the two are different topics, and the
    bus orders nothing between two topics (ADR-0008), so a gesture that
    arrived first is a gesture read against the rails as they were. A person
    with a picker in front of them presses it again, and that is the whole of
    what this does — a press naming the railroad already loaded is ignored,
    so repeating one that landed costs nothing.
    """

    def said() -> bool:
        pick(bus, railroad)
        return f"up on '{railroad}'" in running.said()

    assert until(said, UP_S), f"it never came up on '{railroad}':\n{running.said()}"


def dark(bus: MqttBus) -> None:
    """Wait until the supply reads `off`, which is the precondition on the
    gesture (ADR-0060). The layout interface writes it from its constructor —
    the railroad comes up dark — so what this waits for is the broker holding
    it, and a gesture published afterwards reaches that app behind the echo of
    its own row."""
    bus.subscribe(POWER, lambda topic, payload: None)
    assert until(
        lambda: bus.last_values.get(POWER, {}).get("power") == OFF, UP_S
    ), "the rails never read dead"


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


def knows(root: Path, railroad: str, block: str, end: str, name: str) -> None:
    """The drawing says what the hardware calls the sensor at one block end
    (ADR-0063), written into the installation this test made.

    The committed fixtures say nothing, every end of them being watched under
    the string the topic uses, and a default is not enough to catch a
    publisher that computes the names instead of reading them.
    """
    path = root / "layouts" / f"{railroad}.drawing.yaml"
    doc = cast(dict[str, Any], yaml.safe_load(path.read_text()))
    doc["symbols"][block]["sensors"] = {end: name}
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


class Watching:
    """A publisher of `device/sensor`: the name the hardware knows each block
    end's sensor by, read off the drawing in the store, and the follower every
    app that reads the store has (ADR-0063, ADR-0060).

    On this thread rather than in a process, unlike every app in this file:
    no such app exists to start, ADR-0063 stating the rule one will be built
    to. The two pieces that carry the rule are the deployed ones —
    `lib/loading.py`'s follower, and a read over the same CRUD contract every
    other app reads the store through — so what stands in is the publishing
    and not the following.
    """

    def __init__(self, url: str, railroad: str) -> None:
        self._url = url.rstrip("/")
        self._loaded = Loaded(railroad)
        self.names: dict[str, str] = {}

    def build(self, bus: MqttBus) -> None:
        """Up on the railroad named: the follower subscribed afresh and the
        names read again. A cold start and a reload are the same thing here,
        which is what makes the names right on either."""
        self._loaded.follow(bus)
        self.names = self._read(self._loaded.name)

    def turn(self, bus: MqttBus) -> bool:
        """One turn of the loop such an app runs, and whether it rebuilt on
        this one. The row is read between two turns rather than inside the
        handler, for the reason `lib/loading.py` gives."""
        if not self._loaded.moved:
            return False
        self.build(bus)
        return True

    def _read(self, railroad: str) -> dict[str, str]:
        """Every block end of `railroad` and the name to subscribe its sensor
        under, `<block>.<end>` unless the drawing says otherwise.

        `GET /drawings/<name>`, the document itself: the name is the
        drawing's and reaches no derived layout. Read here as a translator
        must read it, which is over the store's face and importing no app
        (ADR-0013).
        """
        where = f"{self._url}/drawings/{railroad}"
        with urllib.request.urlopen(where, timeout=5) as answer:
            doc = cast(dict[str, Any], json.load(answer))
        names: dict[str, str] = {}
        for block, spec in cast(dict[str, Any], doc["symbols"]).items():
            if spec.get("kind") != "block":
                continue
            written = cast(dict[str, Any], spec.get("sensors") or {})
            for end in ENDS:
                names[f"{block}.{end}"] = str(written.get(end, f"{block}.{end}"))
        return names


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


def test_the_layout_interface_answers_the_gesture_and_rebuilds(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """This app **answers** the picker where the five others follow the row
    it writes: it is the one app bound to a railroad, so a person's
    `railroad_wanted` is what moves `state/railroad` and nothing else is
    (ADR-0060).

    One gesture is enough. It is an event and nothing hands it over a second
    time, so the app is subscribed to it before its own opening rows go out;
    a press landing in that instant would simply be gone.

    The desired rows are one per address, and the address is the old
    railroad's wiring: a speed for a locomotive the new railroad does not
    have is a row nothing republishes and nothing else drops. Zeroing is not
    clearing — a zeroed row is still a row, keyed to an address that is not
    there."""
    running = started("layout", broker, store, tmp_path)
    try:
        writing = hand(broker)
        writing.publish(STALE_TRACTION, {"addr": "17", "speed": 0.5})
        assert until(lambda: STALE_TRACTION in writing.last_values)
        dark(writing)

        pick(writing, NOW)
        up_on(running, NOW)

        held = picture(broker)
        assert STALE_TRACTION not in held, "the desired speed survived the reload"
        assert held[RAILROAD]["name"] == NOW
        assert held["tc49/layout/state/wanted/track"]["power"] == OFF
        assert held["tc49/layout/state/mode"]["modes"] == {}
        no_trace_of_the_old_railroad(held)
        writing.close()
    finally:
        running.stop()


def test_a_gesture_while_the_rails_have_power_changes_nothing(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """Track power off is the precondition, and it is read off the one
    retained row rather than orchestrated: nothing here commands a shutdown,
    and this app never writes `off` of its own accord (ADR-0060, ADR-0051).

    With the power on a train already under a committed route keeps rolling
    and a turnout can still throw, which is what a reload must not happen
    under — so the gesture is dropped and the state row is unmoved. The
    supply is written by a hand here because what folds it on a running
    railroad is the hardware, and there is none (ADR-0043)."""
    running = started("layout", broker, store, tmp_path)
    try:
        writing = hand(broker)
        dark(writing)
        writing.publish("tc49/layout/state/device/track", {"power": ON, "reason": ""})
        assert until(
            lambda: writing.last_values.get(POWER, {}).get("power") == ON, UP_S
        ), "the rails never came alive"

        pick(writing, NOW)
        settle(writing)

        held = picture(broker)
        assert held[RAILROAD]["name"] == WAS, "it loaded a railroad under a live track"
        assert f"up on '{NOW}'" not in running.said(), running.said()
        assert running.running, f"the layout interface stopped:\n{running.said()}"
        writing.close()
    finally:
        running.stop()


def test_a_railroad_the_store_does_not_have_is_refused(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """An app with nothing to run on is worse than one still running the
    railroad it had (ADR-0050), so a name the store cannot answer for is said
    on stderr and the running railroad stands.

    And the picker still works afterwards: a gesture is an event, so there is
    no row standing to be attempted, refused and attempted again — the app
    forgets the refusal and the next press is taken."""
    running = started("layout", broker, store, tmp_path)
    try:
        writing = hand(broker)
        dark(writing)

        pick(writing, MISSING)
        assert until(lambda: f"'{MISSING}':" in running.said(), UP_S), running.said()
        # Up on the same railroad a second time: the rows it owns went with
        # the railroad it was leaving, `state/railroad` among them, so the
        # picture below is read after they have been written again.
        assert until(
            lambda: running.said().count(f"up on '{WAS}'") == 2, UP_S
        ), running.said()

        assert picture(broker)[RAILROAD]["name"] == WAS
        picks(writing, NOW, running)
        assert picture(broker)[RAILROAD]["name"] == NOW
        writing.close()
    finally:
        running.stop()


def test_the_simulator_stands_in_for_the_new_railroads_steel(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """This binding's steel is the drawing it was built from, so another
    railroad is another simulator (ADR-0030). Both its rows are republished
    rather than left, so what this catches is an app that ignores the gesture
    and not one that fails to clear — this app owns no row keyed by anything
    the old railroad had.

    **It answers the gesture with the rails live**, which is the whole of what
    this asserts: nothing writes `off` anywhere below, and the supply reads
    `on` before the pick and after it. The precondition binds the binding that
    drives hardware, because what it buys is a person confirming that the steel
    matches the drawing just loaded; this binding has no steel and so nothing
    to confirm (ADR-0060 as amended, `lib/loading.py`).

    Written the other way — the precondition applied here too — a deployed
    simulator could never answer the picker at all, since it is the only writer
    of its own supply and that supply is a constant. The reload could then only
    be reached by a hand publishing `off`, which is a test driving the system
    through a contract violation to demonstrate an acceptance criterion.
    """
    running = started("simulator", broker, store, tmp_path)
    try:
        writing = hand(broker)
        writing.subscribe(POWER, lambda topic, payload: None)
        assert until(
            lambda: writing.last_values.get(POWER, {}).get("power") == ON, UP_S
        ), "the simulated rails never came alive"

        picks(writing, NOW, running)

        held = picture(broker)
        assert held[RAILROAD]["name"] == NOW
        assert held[POWER]["power"] == ON, "the rebuilt binding forgot its own supply"
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


def test_a_publisher_that_reads_the_store_builds_its_sensor_names_again(
    broker: Broker, root: Path, store: Store
) -> None:
    """The names a sensor publisher subscribes its hardware under are a
    railroad's, so it follows `state/railroad` like every other app that reads
    the store: on a reload it reads the new railroad's drawing and holds no
    name of the old one (ADR-0063, ADR-0060).

    The topic it would publish on does not move — `<block>.<end>` on every
    railroad — so what a reload changes is which ends there are and what the
    hardware calls the sensor at each, and both are read from the store rather
    than computed. The name written into the drawing below is what tells the
    two apart.
    """
    knows(root, NOW, WATCHED, "A", KNOWN_AS)
    writing = hand(broker)
    watching = Watching(store.url, WAS)
    watching.build(writing)
    assert watching.names["yard_w.A"] == "yard_w.A", "it read the wrong railroad"

    load(writing, NOW)
    assert drained(
        writing, lambda: watching.turn(writing), UP_S
    ), "it never followed the row"

    assert watching.names[f"{WATCHED}.A"] == KNOWN_AS, "it did not read the drawing"
    assert watching.names[f"{WATCHED}.B"] == f"{WATCHED}.B"
    left = sorted(name for name in watching.names if name.split(".")[0] in WAS_BLOCKS)
    assert not left, f"it still watches {left} of '{WAS}'"
    writing.close()


def test_a_translator_that_reads_nothing_is_not_a_railroads_and_does_not_reload(
    broker: Broker, store: Store, tmp_path: Path
) -> None:
    """What decides is whether the app reads the store, not that it is
    hardware's: this one takes no `--railroad` and reads no documents, and its
    two rows are the command station's rather than a railroad's — the link it
    has and the supply it reports. A railroad loaded under it changes nothing
    it could publish, so it stands, and its rows stand with it (ADR-0059,
    decision 5).

    A translator that published `device/sensor` would read the drawing for the
    names the hardware knows those sensors by and would follow the row, which
    is the test above (ADR-0063). The rule narrows to the apps that read the
    store rather than gaining an exception."""
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
