"""The bus: the interface every app is handed, and the in-process binding.

``Bus`` is the interface — subscribe, publish, drain, last values — and
``InProcessBus`` below is one binding of it. The other is `tc49.lib.mqtt`,
over a broker, which is what the deployed apps run on (ADR-0059).
An app names the interface and never a binding: which one it was handed is
the business of whatever assembled it, and `bench`, `sweep` and the property
suite keep the in-process one because byte-identical replay is what they
exist for.

The in-process binding is single-threaded, queued-FIFO, run-to-completion
(SYSTEM.md "The bus",
ADR-0008): ``publish()`` appends to one queue and returns; ``drain()``
delivers each queued event to subscribers in subscription order, so
delivery order is a pure function of publish and subscribe order.

State topics — marked structurally by a ``state`` path segment before the
leaf — are last-value-wins: the last value is delivered to a late
subscriber. Event topics are never replayed.

Publishing on one **stamps** it: the binding reads the run clock and writes
it to the payload's ``at``, so a consumer can tell two values of one topic
apart when the wire hands them over out of order (#240). The binding stamps
rather than the app, which is what keeps a clock out of every app component
(ADR-0009), and it stamps here rather than a level up because this is the
thing that publishes. An ``at`` a caller already put on a state payload is
replaced: one place stamps, and it is the one publishing.

The retained values live in memory and go with the process. Outliving one is
the **broker's** job and nowhere else's: the deployed apps run on the MQTT
binding, where a restarted app finds its own last value waiting on its own
topic and a restarted broker holds nothing at all, which is the railroad
coming up at rest (ADR-0059 decision 3, ADR-0054, #123). This binding is the
harness's, and a benchmark that read a file from the run before it would not
be a benchmark.
"""

from collections import deque
from collections.abc import Callable
from typing import Any, Protocol, cast

from tc49.lib.clock import Clock
from tc49.lib.inventory import AT, is_state_topic

Payload = dict[str, Any]
Handler = Callable[[str, Payload], None]

_Subscription = tuple[str, Handler]


class Bus(Protocol):
    """What an app is handed, and all of it: the surface both bindings
    implement, and the only name an app component writes.

    Structural rather than a base class, so a binding is one by having the
    members and not by inheriting: the MQTT binding shares no implementation
    with the in-process one — a broker holds the retained values and a
    network thread fills the queue — and there is nothing for a common
    ancestor to carry (ADR-0059).

    ``clear`` and ``forget`` are the two a **reload** needs and nothing else
    uses: loading another railroad is a cold start that happens without a
    restart, so the rows the last one left have to go and the app built on it
    has to stop answering (ADR-0060, `tc49.lib.loading`).
    """

    @property
    def last_values(self) -> dict[str, Payload]: ...

    def subscribe(self, topic_filter: str, handler: Handler) -> None: ...

    def publish(self, topic: str, payload: Payload) -> None: ...

    def drain(self) -> None: ...

    def clear(self, topic: str) -> None: ...

    def forget(self) -> None: ...


class InProcessBus:
    def __init__(self, clock: Clock) -> None:
        """`clock`: the run clock, which the binding reads as it publishes.
        Required rather than defaulted, because a bus given none would stamp
        every state value alike and the ordering the stamp is for would
        quietly stop working wherever one was constructed (#240)."""
        self._clock = clock
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Payload, _Subscription | None]] = deque()
        self._last_values: dict[str, Payload] = {}

    @property
    def last_values(self) -> dict[str, Payload]:
        """Every state topic's last value, in the order each was first
        published. What a late subscriber is owed, for a subscriber that
        cannot use ``subscribe`` — an app adopting its own value at
        construction, which has to settle before it publishes anything and so
        cannot wait for a drain (#123, ADR-0032)."""
        return dict(self._last_values)

    def subscribe(self, topic_filter: str, handler: Handler) -> None:
        validate_filter(topic_filter)
        subscription = (topic_filter, handler)
        self._subscriptions.append(subscription)
        for topic, payload in self._last_values.items():
            if matches(topic_filter, topic):
                self._queue.append((topic, payload, subscription))

    def publish(self, topic: str, payload: Payload) -> None:
        if is_state_topic(topic):
            payload = self._stamped(payload)
            self._last_values[topic] = payload
        self._queue.append((topic, payload, None))

    def clear(self, topic: str) -> None:
        """The retained value dropped: the row is **gone**, rather than
        holding a value somebody would read as current.

        Nothing is delivered. A broker clears a row by publishing an empty
        payload and a subscriber is handed no value, so a handler never sees
        an absence — the app that owned the row is about to publish the new
        railroad's, and what reads the topic reads that (ADR-0060). Only a
        state topic has a value to drop; an event topic never had one, and
        asking is a bug in the caller rather than a no-op.
        """
        if not is_state_topic(topic):
            raise ValueError(f"nothing is retained on {topic!r}")
        self._last_values.pop(topic, None)

    def forget(self) -> None:
        """Every subscription dropped, and everything queued with them.

        What makes a reload a cold start: the app built on the railroad that
        is being left keeps its handlers on this bus until something takes
        them off, and one that kept answering beside its replacement would be
        a second dispatcher on one railroad. What is in flight goes for the
        same reason — it was published to the railroad that is gone
        (ADR-0054, ADR-0060).
        """
        self._subscriptions.clear()
        self._queue.clear()

    def _stamped(self, payload: Payload) -> Payload:
        """The value with this instant's stamp on it, read off the run clock.
        The clock is what this binding stamps from and the other binding's
        wall time is what it stamps from, which is the whole of the
        difference: a stamp says when the value was published, and processes
        on a broker share no run clock (ADR-0059)."""
        return stamped(payload, self._clock.now)

    def drain(self) -> None:
        while self._queue:
            topic, payload, target = self._queue.popleft()
            targets = [target] if target is not None else list(self._subscriptions)
            for topic_filter, handler in targets:
                if matches(topic_filter, topic):
                    handler(topic, payload)


def stamped(payload: Payload, at: float) -> Payload:
    """The value with `at` on it, leading its fields as the inventory has it.
    Whatever ``at`` the payload arrived with is gone: the stamp says when the
    binding published the value, and a caller cannot state that on its behalf.

    A payload that is not an object has no fields to put a stamp among, so it
    is left exactly as it came — anything at all can arrive on a topic and a
    retained file can be hand-edited (rule 4), and the value reads as
    unstamped, which is a case `payload.Ordering` already has.

    Here rather than in either binding because both stamp, and only what they
    read the instant off differs.
    """
    given = cast(object, payload)
    if not isinstance(given, dict):
        return payload
    fields = cast(Payload, given)
    return {AT: at, **{k: v for k, v in fields.items() if k != AT}}


def validate_filter(topic_filter: str) -> None:
    # MQTT grammar: '#' only as the whole last level, '+' only as a whole level.
    levels = topic_filter.split("/")
    for i, level in enumerate(levels):
        if "#" in level and not (level == "#" and i == len(levels) - 1):
            raise ValueError(f"invalid filter {topic_filter!r}: misplaced '#'")
        if "+" in level and level != "+":
            raise ValueError(f"invalid filter {topic_filter!r}: misplaced '+'")


def matches(topic_filter: str, topic: str) -> bool:
    filter_levels = topic_filter.split("/")
    topic_levels = topic.split("/")
    for i, level in enumerate(filter_levels):
        if level == "#":
            return True
        if i >= len(topic_levels) or (level != "+" and level != topic_levels[i]):
            return False
    return len(topic_levels) == len(filter_levels)
