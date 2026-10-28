"""The driver as its own process: what it takes for it to come up alone.

Against a real broker on a real socket, because that is what is under test —
an app started against nothing, in whatever order the machine brings things up
(ADR-0059, decision 5). There is no store here and no fixture for one: the
driver reads no documents, so the order that the scheduler's and dispatcher's
suites exercise does not exist for this app. The loop itself runs on a thread
here and is ended with the event `serve` takes; in the deployment it is the
main thread and a signal ends it.

Waiting on the app's own log line is how these tests know it is up. Every
other app publishes a row on the way up and the suite waits for that; this one
owns no row, so the sentence a person watching the container reads is the only
announcement there is.
"""

import threading
from collections.abc import Iterator

import pytest

from tc49.driver.__main__ import ALIVE_CONFIRMED, serve
from tc49.lib.bus import Payload
from tc49.lib.loading import NO_RAILROAD
from tc49.lib.mqtt import MqttBus
from tc49.lib.settings import THROTTLE_SILENCE_S, KeptSettings, said
from tests.brokers import (
    Broker,
    at_least_once_in_any_two_seconds,
    beats,
    drained,
    settle,
)

RAILROAD = "crossover-yard"
GRANTED = "tc49/dispatch/move_granted"
MOVE = "tc49/layout/move"
SETTINGS = "tc49/layout/state/settings"

HONEST: Payload = {
    "id": "freight_1-1",
    "train": "freight_1",
    "transit": "west_ladder.to_dn",
    "into": "dn_w",
    "aspect": "clear",
}
"""One grant as the dispatcher publishes it — here from another process, which
is what the broker makes of the seam #261 states in process."""

COMMANDED: Payload = {
    "train": "freight_1",
    "connection": "west_ladder",
    "transit": "to_dn",
    "into": "dn_w",
    "speed": 0.6,
}
"""What `HONEST` becomes: the transit split, the train and the block entered
carried across, and `clear` turned into its speed."""


class App:
    """The driver running as `python -m tc49.driver` runs it, on a thread so
    the test can watch the bus while it is up.

    Its client is made when it starts and not before, so a test can stop the
    broker first and have the app go looking for one that is not there.
    """

    def __init__(self, broker: Broker, railroad: str = RAILROAD) -> None:
        self._broker = broker
        self._railroad = railroad
        self._bus: MqttBus | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.up = threading.Event()

    def start(self) -> None:
        self._bus = MqttBus(port=self._broker.port)
        self._thread = threading.Thread(
            target=serve,
            args=(self._bus, self._railroad, self._stop, 0.01),
            kwargs={"log": self._log},
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
        """The app's log, dropped except for the one line that says it is
        subscribed and looping. What it says is for a person watching a
        container; the suite asserts on the bus."""
        if line.startswith("up on"):
            self.up.set()


@pytest.fixture
def app(broker: Broker) -> Iterator[App]:
    running = App(broker)
    try:
        yield running
    finally:
        running.stop()


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
    return [payload for heard_on, payload in heard if heard_on == topic]


def settings(hand: MqttBus) -> None:
    """`state/settings` as `layout` says it on a loaded railroad, the default
    speeds among it: retained, so a driver that comes up later hears it, and
    without it a grant moves nothing (#1133)."""
    hand.publish(SETTINGS, said(KeptSettings(), THROTTLE_SILENCE_S))


def test_a_cold_start_says_nothing_and_stays_up(broker: Broker, app: App) -> None:
    """Against an empty broker with nothing else running: the driver comes up,
    and the bus stays silent (ADR-0059).

    Silence is this app's cold start, but for saying it is up (#1113). It
    reads no assets (SYSTEM.md, driver footprint), so it
    owns no retained row to publish, and a `move` before a grant would be a
    command the dispatcher never authorised.
    """
    witness, heard = watching(broker)
    app.start()

    assert app.up.wait(10), "it never came up"
    settle(witness)
    said = [topic for topic, _payload in heard if topic != ALIVE_CONFIRMED]
    assert said == [], "the driver published without a grant"
    assert app.running, "the app stopped on its own"
    witness.close()


def test_it_commands_a_grant_it_finds_on_the_broker(broker: Broker, app: App) -> None:
    """The loop is what makes the app an app: a grant published by anything at
    all is drained and restated as the command that moves the train, the
    transit split and the aspect priced (ADR-0025)."""
    witness, heard = watching(broker)
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    settings(hand)
    app.start()
    assert app.up.wait(10), "it never came up"

    # The grant as the dispatcher publishes one. It does not say who published
    # it, and nothing here asks (rule 4).
    hand.publish(GRANTED, HONEST)

    assert drained(witness, lambda: rows(heard, MOVE) != []), "the grant was dropped"
    assert rows(heard, MOVE) == [COMMANDED]
    hand.close()
    witness.close()


def test_it_comes_up_against_a_broker_that_is_not_there_yet(
    broker: Broker, app: App
) -> None:
    """The order nothing forbids: no `depends_on` anywhere, so the app is
    started before the broker it runs on and waits rather than exiting."""
    broker.stop()
    app.start()
    assert not app.up.wait(1), "it said it was up with no broker to be up on"
    assert app.running, "the app gave up on a broker that was not up yet"

    assert broker.start()

    # Reconnected on the client's own backoff, whose first step is a second.
    assert app.up.wait(30), "it never came up once the broker was there"
    witness, heard = watching(broker)
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    settings(hand)
    hand.publish(GRANTED, HONEST)

    assert drained(witness, lambda: rows(heard, MOVE) != []), "the grant was dropped"
    assert rows(heard, MOVE) == [COMMANDED]
    hand.close()
    witness.close()


def test_a_grant_it_cannot_read_leaves_it_running(broker: Broker, app: App) -> None:
    """A frame claiming to be a grant is one more thing anyone can publish,
    and on the broker whoever publishes it is another process: a driver that
    raised on one would be taken down from outside (BUS.md, rule 4, #261).

    Each is dropped, the process stays up, and the honest grant after them
    still lands — a drop being a drop and not a state.
    """
    witness, heard = watching(broker)
    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    settings(hand)
    app.start()
    assert app.up.wait(10), "it never came up"

    aspect = {"aspect": "clear"}
    for payload in (
        aspect,  # an aspect and nothing to move
        {**aspect, "transit": "west_ladder.to_dn", "into": "dn_w"},  # no train
        {**aspect, "train": "freight_1", "transit": "to_dn", "into": "dn_w"},  # bare
        {"train": "freight_1", "transit": "west_ladder.to_dn", "into": "dn_w"},
    ):
        hand.publish(GRANTED, payload)
    settle(witness)
    assert rows(heard, MOVE) == [], "something unreadable was commanded"
    assert app.running, "a frame from another process took the driver down"

    hand.publish(GRANTED, HONEST)

    assert drained(witness, lambda: rows(heard, MOVE) != []), "the grant was dropped"
    assert rows(heard, MOVE) == [COMMANDED]
    hand.close()
    witness.close()


def test_a_grant_before_any_settings_moves_nothing(broker: Broker, app: App) -> None:
    """Up on a broker that holds no `state/settings`, the driver has no
    speeds and drops a grant; once the row is said, the next grant moves at
    its speed (#1133)."""
    witness, heard = watching(broker)
    app.start()
    assert app.up.wait(10), "it never came up"

    hand = MqttBus(port=broker.port)
    assert hand.wait_connected()
    hand.publish(GRANTED, HONEST)
    settle(witness)
    assert rows(heard, MOVE) == [], "a grant was priced with no speeds heard"

    settings(hand)
    hand.publish(GRANTED, HONEST)
    assert drained(witness, lambda: rows(heard, MOVE) != []), "the grant was dropped"
    assert rows(heard, MOVE) == [COMMANDED]
    hand.close()
    witness.close()


def test_on_a_railroad_it_says_once_a_second_that_it_is_up(
    broker: Broker, app: App
) -> None:
    """What a page names the driver on when it goes quiet (#1113): at least
    once in any two seconds, so the page's 3 s has a margin, and once a second
    on the monotonic clock rather than once a turn of a loop turning every
    10 ms."""
    witness, heard = watching(broker)
    app.start()
    assert app.up.wait(10), "it never came up"

    said = beats(broker.port, ALIVE_CONFIRMED, 4.5)

    assert at_least_once_in_any_two_seconds(said, 4.5), f"heard at {said}"
    assert len(said) <= 6, f"{len(said)} in 4.5 s, where once a second is 4 or 5"
    settle(witness)
    assert all(payload == {} for payload in rows(heard, ALIVE_CONFIRMED))
    witness.close()


def test_standing_with_no_railroad_it_says_nothing(broker: Broker) -> None:
    """A driver with no railroad loaded is not judged, and says nothing: the
    band already says no railroad is loaded (#1113)."""
    standing = App(broker, railroad=NO_RAILROAD)
    try:
        standing.start()
        assert standing.up.wait(10), "it never came up"
        said = beats(broker.port, ALIVE_CONFIRMED, 2.5)
        assert said == [], f"a driver with no railroad said it was up at {said}"
        assert standing.running, "the app stopped on its own"
    finally:
        standing.stop()
