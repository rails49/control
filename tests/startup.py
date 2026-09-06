"""The retained window, held once for every app that comes up through it.

`lib/startup.py` gives the broker a moment to hand over the rows an app owns
and waits it on `stop`, so a signal arriving inside the window ends the
process rather than being sat on for the rest of it. That is one rule, and
the dispatcher and the scheduler are two apps held to it — which is a reason
for one fixture and one run of assertions, not a copy in each suite that will
drift (#455).

Here rather than in `tests/harness.py`, for the reason `tests/brokers.py` is:
what this holds is an app coming up alone against a real broker (ADR-0059,
decision 5), not the in-process assembly. Registered as a plugin beside it, so
pytest resolves `waiting` by name in whichever suite asks for it.

A suite says only which app is under test, through `windowed`; what the app
then has to do is the same for both.
"""

import time
from collections.abc import Iterator
from typing import Protocol

import pytest

from tc49.lib.mqtt import MqttBus
from tc49.lib.startup import RETAINED_S
from tests.brokers import settle, until

WINDOW_S = 30.0
"""A retained window long enough for a test to be sure the app is inside one.
The deployed number is `RETAINED_S` (`lib/startup.py`); what is under test is
that a stop is acted on wherever inside a window it lands, which no length
may change."""


class Waiting(Protocol):
    """An app under test, as this rule needs to see one: its client, what it
    has printed on the way up, and the three calls that run it."""

    bus: MqttBus
    said: list[str]

    def start(self) -> None: ...

    @property
    def running(self) -> bool: ...

    def stop(self) -> None: ...


@pytest.fixture
def waiting(windowed: Waiting) -> Iterator[Waiting]:
    """The suite's app on a window nothing will end early: the broker holds
    no row of the one it waits for, so it waits the whole of `WINDOW_S`."""
    try:
        yield windowed
    finally:
        windowed.stop()


def a_stop_in_the_window_is_acted_on_there(waiting: Waiting, witness: MqttBus) -> None:
    """`retained_s` is a moment given to the broker, "waited on `stop`" so
    that "a signal arriving inside the window ends the process rather than
    being sat on for the rest of it" (`lib/startup.py`). An app that polled
    instead and took no `stop` at all honoured a SIGTERM landing in the
    window a window late — a second in the deployment, and however long
    `WINDOW_S` is here (#430).

    `witness` is another client of the same broker, already subscribed: the
    app is inside the window only where nothing it publishes has arrived.
    """
    waiting.start()
    assert until(lambda: waiting.said != []), "it never read its documents"
    # Past the store and past the broker, and nothing but the window left to
    # be in: the row it is waiting for is one nothing on this broker writes.
    settle(witness)
    assert waiting.bus.connected, "it never reached the broker"
    assert not any(
        line.startswith("up on") for line in waiting.said
    ), f"it came up, so the stop below would not land in the window: {waiting.said}"

    began = time.monotonic()
    waiting.stop()
    took = time.monotonic() - began

    assert not waiting.running, f"a stop in the window did not end it: {waiting.said}"
    assert took < RETAINED_S, f"the stop was sat on for {took}s of a {WINDOW_S}s window"
    witness.close()
