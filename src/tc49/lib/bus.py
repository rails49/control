"""In-process event bus: the milestone-1 binding of the bus contract.

Single-threaded, queued-FIFO, run-to-completion (SYSTEM.md "The bus",
ADR-0008): ``publish()`` appends to one queue and returns; ``drain()``
delivers each queued event to subscribers in subscription order, so
delivery order is a pure function of publish and subscribe order.

State topics — marked structurally by a ``state`` path segment before the
leaf — are last-value-wins: the last value is delivered to a late
subscriber. Event topics are never replayed.
"""

from collections import deque
from collections.abc import Callable
from typing import Any

from tc49.lib.inventory import is_state_topic

Payload = dict[str, Any]
Handler = Callable[[str, Payload], None]

_Subscription = tuple[str, Handler]


class Bus:
    def __init__(self) -> None:
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Payload, _Subscription | None]] = deque()
        self._last_values: dict[str, Payload] = {}

    @property
    def last_values(self) -> dict[str, Payload]:
        """Every state topic's last value, in the order each was first
        published. What a late subscriber is owed, for a subscriber that
        cannot use ``subscribe`` — the bridge relaying to a client that
        connects mid-run (ADR-0032)."""
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
            self._last_values[topic] = payload
        self._queue.append((topic, payload, None))

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
