"""The MQTT binding of the bus: the same interface, over a broker.

One `Bus` (`tc49.lib.bus`) and two bindings of it. This one is what the
deployed apps run on, each in its own process, and it is what lets hardware
built to speak the bus find our topics where it looks for them — on the
broker, rather than inside somebody's Python queue
(ADR-0059, decision 1). The in-process binding stays
for `bench`, `sweep` and the property suite, whose reason to exist is
byte-identical replay.

What the broker does and this file therefore does not: **retention**. A state
topic — a ``state`` level before the leaf, `inventory.is_state_topic` — is
published retained and an event topic is not, so the broker holds the last
value of every state topic and hands it to whoever subscribes, whenever they
subscribe. That is exactly the promise the in-process binding keeps out of
its own map (ADR-0032), kept by the thing MQTT built for it, and nothing here
persists anything.

**The stamp comes off wall time**, seconds as a float, where the in-process
binding reads the run clock: the processes on a broker share no run clock,
and a stamp that reset to zero in each of them would order nothing. It is
still the binding that stamps and never the app (ADR-0009), and an ``at`` a
caller supplied is still replaced.

**Threading.** The client's network thread does one thing with what arrives:
it appends to a queue. ``drain()``, on the caller's own thread, takes what is
waiting and delivers it to the handlers. So every app keeps its single thread,
a handler still runs to completion before the next one starts, and no app code
learns that a second thread exists. `last_values` is the one member both
threads touch, and it is held under a lock for exactly as long as the copy
takes.

**A broker that is gone is not queued for.** Publishing while disconnected
drops the message, which is what QoS 0 does and what ADR-0050 wants: a
railroad that cannot be reached is reported, never buffered up and applied
minutes later to a layout that has moved on. The connection is retried with
backoff and each loss is said on stderr, so a person watching the container
sees it. Nothing else is done about it: an app has no answer to its broker
being down, and the row that says a participant cannot reach its hardware is
`device/link`, published by whoever knows (ADR-0059 decision 7).
"""

import json
import sys
import threading
import time
from collections import deque

from paho.mqtt import client as paho
from paho.mqtt.enums import CallbackAPIVersion, MQTTErrorCode
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from tc49.lib.bus import Handler, Payload, matches, stamped, validate_filter
from tc49.lib.inventory import is_state_topic

_Subscription = tuple[str, Handler]

QOS = 0
"""What everything is published and subscribed at, and the reason nothing is
queued for a broker that is gone: at QoS 0 the client drops what it cannot
send rather than holding it for a reconnect. The bus promises at-least-once
delivery and no more (SYSTEM.md), and retention — which is what a state topic
actually needs — is independent of QoS."""

SUBSCRIBE_TIMEOUT_S = 5.0
"""How long `subscribe` waits for the broker to acknowledge before carrying
on regardless. A bound and not a promise: a broker that has gone quiet is not
a reason to stop an app from starting, and the filter goes again on the
reconnect."""


class MqttBus:
    """Connecting from construction, as the bridge serves from construction.

    The connection is made in the background, so an app comes up whether its
    broker is there yet or not (ADR-0059 decision 5): `wait_connected` is for
    the one caller who has to know, an app about to publish its opening rows,
    since a publish made before the connection lands is dropped like any other
    made to a broker that is not there.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        client_id: str = "",
        keepalive: int = 60,
    ) -> None:
        self._where = f"{host}:{port}"
        self._lock = threading.Lock()
        self._subscriptions: list[_Subscription] = []
        self._queue: deque[tuple[str, Payload]] = deque()
        self._last_values: dict[str, Payload] = {}
        self._acknowledged: set[int] = set()
        self._acknowledgements = threading.Condition()
        self._client = paho.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=paho.MQTTv311,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_subscribe = self._on_subscribe
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        # Async, so construction does not wait on a broker, and `loop_start`
        # is what retries it — the backoff above is the client's own.
        self._client.connect_async(host, port, keepalive)
        self._client.loop_start()

    @property
    def connected(self) -> bool:
        return self._client.is_connected()

    def wait_connected(self, timeout: float = 5.0) -> bool:
        """Whether the connection landed inside `timeout`. Polled rather than
        signalled because there is nothing to do while waiting: the caller
        either publishes its opening rows or gives up and lets the backoff
        carry on without it."""
        deadline = time.monotonic() + timeout
        while not self.connected and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.connected

    @property
    def last_values(self) -> dict[str, Payload]:
        """Every state topic this process has published or heard, latest
        value each. The broker is where they live; this is the picture built
        from what has come back, which is why an app that must read its own
        row at startup subscribes and drains rather than reading here first —
        a retained value arrives from the broker moments after the connection
        does, where the in-process binding had it from a file synchronously.
        """
        with self._lock:
            return dict(self._last_values)

    def subscribe(self, topic_filter: str, handler: Handler) -> None:
        """Subscribed on the broker too, and again on every reconnect, so the
        retained values arrive whenever the subscription does — before the
        connection, when it lands; after it, on the acknowledgement.

        A second handler on a filter already subscribed re-subscribes it,
        which has the broker send that filter's retained values again and so
        reaches handlers that already had them. The bus promises at-least-once
        delivery for exactly this kind of reason, and a repeated state value
        is the same value.

        Returns once the broker has acknowledged, so a subscription is live
        when the call comes back and an event another app publishes the next
        instant is not lost in the gap: on the in-process binding a
        subscription is effective on the call, and an app that subscribes and
        then goes to work is written for that. Nothing is waited for while
        disconnected — there is no broker to acknowledge, and the filters go
        again as the connection lands.
        """
        validate_filter(topic_filter)
        with self._lock:
            self._subscriptions.append((topic_filter, handler))
        if self.connected:
            self._acknowledged_subscribe(topic_filter)

    def publish(self, topic: str, payload: Payload) -> None:
        """Retained on a state topic and not on an event one, which is the
        whole of what the broker needs to keep the bus's two kinds apart.

        A payload that will not encode as JSON raises here rather than going
        anywhere: it is a bug in the publisher, and the wire has no way to
        carry it (SYSTEM.md, rule 4, is about what a *consumer* reads).
        """
        retain = is_state_topic(topic)
        if retain:
            payload = stamped(payload, time.time())
            with self._lock:
                self._last_values[topic] = payload
        self._client.publish(topic, json.dumps(payload), qos=QOS, retain=retain)

    def drain(self) -> None:
        """Deliver what the network thread has left waiting, on this thread.

        What is waiting when the drain starts, and nothing that arrives during
        it: a drain ends, where a queue the network thread keeps filling would
        not. A handler that publishes reaches its own subscribers through the
        broker and so on a later drain, which is the one place the two
        bindings differ in order — MQTT promises nothing about it either
        (ADR-0008).
        """
        with self._lock:
            waiting = list(self._queue)
            self._queue.clear()
            subscriptions = list(self._subscriptions)
        for topic, payload in waiting:
            for topic_filter, handler in subscriptions:
                if matches(topic_filter, topic):
                    handler(topic, payload)

    def close(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    def _acknowledged_subscribe(self, topic_filter: str) -> None:
        """Subscribe and wait for the acknowledgement, on the caller's thread.

        Never called on the network thread: that thread is what reads the
        acknowledgement, so waiting for one there would wait forever. The
        subscriptions a reconnect re-establishes therefore go without waiting
        (`_on_connect`), which is all a reconnect can do anyway.
        """
        code, mid = self._client.subscribe(topic_filter, qos=QOS)
        if code != MQTTErrorCode.MQTT_ERR_SUCCESS or mid is None:
            self._say(f"subscription to {topic_filter} refused: {code}")
            return
        with self._acknowledgements:
            self._acknowledgements.wait_for(
                lambda: mid in self._acknowledged, timeout=SUBSCRIBE_TIMEOUT_S
            )
            self._acknowledged.discard(mid)

    def _on_subscribe(
        self,
        client: paho.Client,
        userdata: object,
        mid: int,
        reason_codes: list[ReasonCode],
        properties: Properties | None = None,
    ) -> None:
        with self._acknowledgements:
            self._acknowledged.add(mid)
            self._acknowledgements.notify_all()

    def _on_connect(
        self,
        client: paho.Client,
        userdata: object,
        flags: paho.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None = None,
    ) -> None:
        if reason_code.is_failure:
            self._say(f"refused by {self._where}: {reason_code}")
            return
        # Every distinct filter, every time: a reconnect starts a clean
        # session, and the retained values arriving again is the promise being
        # kept rather than a repeat to avoid.
        with self._lock:
            filters = list(dict.fromkeys(one for one, _ in self._subscriptions))
        for topic_filter in filters:
            client.subscribe(topic_filter, qos=QOS)

    def _on_disconnect(
        self,
        client: paho.Client,
        userdata: object,
        flags: paho.DisconnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None = None,
    ) -> None:
        if reason_code.is_failure:
            self._say(f"connection to {self._where} lost: {reason_code}, retrying")

    def _on_message(
        self, client: paho.Client, userdata: object, message: paho.MQTTMessage
    ) -> None:
        """The network thread's whole job: read the payload and queue it."""
        topic = message.topic
        if not message.payload:
            # A retained value cleared: the broker is telling every subscriber
            # the row is gone, and there is no value to deliver.
            with self._lock:
                self._last_values.pop(topic, None)
            return
        try:
            payload: Payload = json.loads(message.payload)
        except ValueError:
            # Dropped rather than raised: the network thread is nobody's app,
            # and something that is not JSON is not a payload a handler could
            # be given. Said on stderr because whoever sent it wants to know.
            self._say(f"unreadable payload on {topic}, dropped")
            return
        with self._lock:
            if is_state_topic(topic):
                self._last_values[topic] = payload
            self._queue.append((topic, payload))

    def _say(self, what: str) -> None:
        print(f"mqtt: {what}", file=sys.stderr, flush=True)
