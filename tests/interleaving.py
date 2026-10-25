"""An in-process bus that delivers in any order MQTT allows.

`InProcessBus` delivers from one queue, first in first out, each message to
every subscriber before the next. Over a broker each app is a process of its
own (ADR-0059), and BUS.md ("Order from one publisher") promises order only
for what one writer sends on one topic: none between two writers, none
between two topics, and one message's copies to different subscribers arrive
independently. This binding keeps exactly that much order and lets `choose`
pick everything else, so the property suite can search the orders a broker
may hand the apps (#1043).

A **channel** is (publisher, topic, subscriber), and each is a FIFO queue.
The subscriber is the object a handler is bound to, or the handler itself
where it is bound to none. The publisher is the subscriber whose handler is
running when `publish` is called, or `OUTSIDE` when none is — the
simulator's fired events and a test's gestures. A retained value handed on
`subscribe` comes from `RETAINED`.
"""

from collections import deque
from collections.abc import Callable
from itertools import count

from tc49.lib.bus import Handler, InProcessBus, Payload, matches, validate_filter
from tc49.lib.clock import Clock
from tc49.lib.inventory import is_state_topic

OUTSIDE = "outside"
"""The publisher of what no handler published: a fired event, a gesture."""

RETAINED = "retained"
"""The publisher of a retained value handed to a late subscriber."""

Choose = Callable[[int], int]
"""Given the number of non-empty channels, the index of the one to deliver
from, the channels ordered by when their head message was queued."""

After = Callable[[object, str, Payload], None]
"""Called with the subscriber, topic and payload after each delivery."""

_Channel = tuple[object, str, int]  # publisher key, topic, subscriber key
_Queued = tuple[int, str, Payload, Handler]  # sequence, topic, payload, handler


def subscriber_of(handler: Handler) -> object:
    """The object a handler is bound to, or the handler itself."""
    return getattr(handler, "__self__", handler)


class InterleavingBus(InProcessBus):
    def __init__(
        self, clock: Clock, choose: Choose, after: After | None = None
    ) -> None:
        """`choose` picks the channel each delivery comes from; `lambda n: 0`
        delivers each message to each subscriber in the order they were
        queued. `after`, if given, sees every delivery once its handler has
        returned, which is where a test reads the state a handler left."""
        super().__init__(clock)
        self._choose = choose
        self._after = after
        self._channels: dict[_Channel, deque[_Queued]] = {}
        self._sequence = count()
        self._running: object = OUTSIDE

    def subscribe(self, topic_filter: str, handler: Handler) -> None:
        validate_filter(topic_filter)
        self._subscriptions.append((topic_filter, handler))
        for topic, payload in self._last_values.items():
            if matches(topic_filter, topic):
                self._enqueue(RETAINED, topic, payload, handler)

    def publish(self, topic: str, payload: Payload) -> None:
        if is_state_topic(topic):
            payload = self._stamped(payload)
            self._last_values[topic] = payload
        for topic_filter, handler in self._subscriptions:
            if matches(topic_filter, topic):
                self._enqueue(self._running, topic, payload, handler)

    def forget(self) -> None:
        super().forget()
        self._channels.clear()

    def drain(self) -> None:
        while self._channels:
            heads = sorted(self._channels, key=lambda key: self._channels[key][0][0])
            index = self._choose(len(heads))
            channel = heads[index]
            queue = self._channels[channel]
            _, topic, payload, handler = queue.popleft()
            if not queue:
                del self._channels[channel]
            subscriber = subscriber_of(handler)
            outer, self._running = self._running, subscriber
            try:
                handler(topic, payload)
            finally:
                self._running = outer
            if self._after is not None:
                self._after(subscriber, topic, payload)

    def _enqueue(
        self, publisher: object, topic: str, payload: Payload, handler: Handler
    ) -> None:
        # Keyed by identity: a subscriber need not be hashable, and two equal
        # ones are still two processes.
        key = publisher if isinstance(publisher, str) else id(publisher)
        channel = (key, topic, id(subscriber_of(handler)))
        queued = (next(self._sequence), topic, payload, handler)
        self._channels.setdefault(channel, deque()).append(queued)
