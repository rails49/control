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

Given a file, the binding makes those retained values **durable** (#123): it
loads them at startup and rewrites the whole file on every retained change,
so a process that comes back up finds them waiting on their topics exactly
as a broker that outlived it would have held them. Durability belongs here
rather than to an app because that is where MQTT already puts it, so the
broker that replaces this binding in milestone 2 keeps the behaviour. Without
a file the bus opens none, which is what leaves ``bench`` and ``sweep``
untouched by construction rather than by a branch.
"""

from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from tc49.lib import durable
from tc49.lib.clock import Clock
from tc49.lib.inventory import AT, is_state_topic

Payload = dict[str, Any]
Handler = Callable[[str, Payload], None]

_Subscription = tuple[str, Handler]


class Bus(Protocol):
    """What an app is handed, and all of it: the surface both bindings
    implement, and the only name an app component writes.

    Structural rather than a base class, so a binding is one by having the
    four members and not by inheriting: the MQTT binding shares no
    implementation with the in-process one — a broker holds the retained
    values and a network thread fills the queue — and there is nothing for a
    common ancestor to carry (ADR-0059).
    """

    @property
    def last_values(self) -> dict[str, Payload]: ...

    def subscribe(self, topic_filter: str, handler: Handler) -> None: ...

    def publish(self, topic: str, payload: Payload) -> None: ...

    def drain(self) -> None: ...


class InProcessBus:
    def __init__(self, clock: Clock, state: Path | None = None) -> None:
        """`clock`: the run clock, which the binding reads as it publishes.
        Required rather than defaulted, because a bus given none would stamp
        every state value alike and the ordering the stamp is for would
        quietly stop working wherever one was constructed (#240).

        `state`: where the retained values live between sessions, or None
        to keep them in memory alone. A path naming no file yet is the first
        session of all, and starts empty."""
        self._clock = clock
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Payload, _Subscription | None]] = deque()
        self._state = state
        # Filtered on the way out as `publish` filters on the way in: a file
        # naming an event topic would replay it to every subscriber, and
        # event topics are never replayed (SYSTEM.md, the bus). The promise
        # is the bus's to keep, whatever wrote the file.
        kept = durable.read(state) if state is not None else {}
        self._last_values: dict[str, Payload] = {
            # Re-stamped with this session's clock, which is reading zero
            # here. The stamp is seconds since the session started, so one
            # carried verbatim out of the last run sits on another timeline
            # and — being the larger number, for as long as that run was
            # long — would beat every genuine report this one makes. The
            # restored picture is instead the oldest thing known, and the
            # first real report supersedes it: what the railroad is saying
            # now outranks what it was left believing (ADR-0030, #240). The
            # file still carries the stamp it was written with; it is the
            # read that re-stamps.
            topic: self._stamped(value)
            for topic, value in kept.items()
            if is_state_topic(topic)
        }

    @property
    def last_values(self) -> dict[str, Payload]:
        """Every state topic's last value, in the order each was first
        published. What a late subscriber is owed, for a subscriber that
        cannot use ``subscribe`` — the bridge relaying to a client that
        connects mid-run (ADR-0032), and an app adopting its own value at
        construction, which has to settle before it publishes anything and so
        cannot wait for a drain (#123)."""
        return dict(self._last_values)

    def subscribe(self, topic_filter: str, handler: Handler) -> None:
        _validate_filter(topic_filter)
        subscription = (topic_filter, handler)
        self._subscriptions.append(subscription)
        for topic, payload in self._last_values.items():
            if _matches(topic_filter, topic):
                self._queue.append((topic, payload, subscription))

    def publish(self, topic: str, payload: Payload) -> None:
        if is_state_topic(topic):
            payload = self._stamped(payload)
            self._last_values[topic] = payload
            self._persist()
        self._queue.append((topic, payload, None))

    def _stamped(self, payload: Payload) -> Payload:
        """The value with this instant's stamp on it, leading its fields as
        the inventory has it. Whatever ``at`` the payload arrived with is
        gone: the stamp says when this bus published the value, and a caller
        cannot state that on its behalf.

        A payload that is not an object has no fields to put a stamp among,
        so it is left exactly as it came — anything at all can arrive on a
        topic and a retained file can be hand-edited (rule 4), and the value
        reads as unstamped, which is a case `payload.Ordering` already has.
        """
        given = cast(object, payload)
        if not isinstance(given, dict):
            return payload
        fields = cast(Payload, given)
        return {AT: self._clock.now, **{k: v for k, v in fields.items() if k != AT}}

    def _persist(self) -> None:
        """The whole picture on every retained change, which a railroad can
        afford: it is slow, and a state topic only republishes when it moves.
        `durable` is where the cut mid-write is answered."""
        if self._state is not None:
            durable.write(self._state, self._last_values)

    def drain(self) -> None:
        while self._queue:
            topic, payload, target = self._queue.popleft()
            targets = [target] if target is not None else list(self._subscriptions)
            for topic_filter, handler in targets:
                if _matches(topic_filter, topic):
                    handler(topic, payload)


def _validate_filter(topic_filter: str) -> None:
    # MQTT grammar: '#' only as the whole last level, '+' only as a whole level.
    levels = topic_filter.split("/")
    for i, level in enumerate(levels):
        if "#" in level and not (level == "#" and i == len(levels) - 1):
            raise ValueError(f"invalid filter {topic_filter!r}: misplaced '#'")
        if "+" in level and level != "+":
            raise ValueError(f"invalid filter {topic_filter!r}: misplaced '+'")


def _matches(topic_filter: str, topic: str) -> bool:
    filter_levels = topic_filter.split("/")
    topic_levels = topic.split("/")
    for i, level in enumerate(filter_levels):
        if level == "#":
            return True
        if i >= len(topic_levels) or (level != "+" and level != topic_levels[i]):
            return False
    return len(topic_levels) == len(filter_levels)
