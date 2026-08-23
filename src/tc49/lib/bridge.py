"""The WebSocket bridge: the milestone binding between bus and browser.

A relay and nothing more (ui/PANEL.md, #71): every `tc49/#` event goes out
to every connected client as one JSON frame, ``{"topic": …, "payload": …}``,
and a frame on an inbound topic — a ``tc49/ui`` leaf, those being the panel's
write surface — is published as the event it names. Anything else inbound is
refused with an error frame, ``request_submitted`` included: the browser
writes gestures and never requests, so the scheduler stays the single minter
and the dispatcher the sole feasibility authority precisely because nothing
else can reach the bus (ADR-0036).

**A client names the railroad it wants in the socket path** —
``ws://127.0.0.1:8766/gotthard``, which a browser reaches as ``/live/gotthard``
on the app's own origin (docs/DEPLOY.md) — and hears that railroad or
none. The relay outlives the assembly it relays: ``rebind`` points it at a
freshly built bus and settles every client on the swap, whoever named the
new railroad starting to hear it and whoever was on the old one being closed
so it re-picks rather than rendering one railroad fed by another's events
(#148). A client that names a railroad other than the running one is asked
for by ``wants`` and waits out of earshot until its swap lands; naming one
that does not exist is an error frame and a close, the running railroad
untouched. No inbound topic carries any of this: the set stays exactly the
``tc49/ui`` leaves, which is what ADR-0034's broker ACL will grant.

On connect a client is sent each state topic's last value, before any live
frame and in the same schema — the frames it would have had were it already
there. That is not the relay describing the run (#67): the bus promises a
state topic delivers its latest value to a late subscriber, a broker delivers
it the moment a client subscribes, and a relay that dropped it would be
weaker than the contract it binds (ADR-0032).

It lives here beside the bus binding it rides on and shares its fate: when
the bus becomes a real broker, the browser speaks MQTT-over-WebSocket to the
broker directly and this file is deleted (ADR-0013 wiring note, #67).

Threading: the bus stays single-threaded. Outbound frames are sent by
whatever thread drains the bus — one sender per connection, which is what
the sync connection allows. Inbound, each client's handler thread calls
``publish``, which is one queue append; the event is delivered when the
session's loop next drains, exactly as a scheduler's would be. Restricting
inbound to event topics keeps that cross-thread surface to the append —
a state topic would also write the last-value map. ``wants`` is the second
and last such handoff, and the same size: the handler thread says which
railroad, and the thread that owns the assembly does the building.
"""

import json
import threading
from collections.abc import Callable

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

from tc49.lib.bus import Bus, Payload
from tc49.lib.inventory import INBOUND

Wants = Callable[[str], str | None]
"""Asked for a railroad a client named, on that client's own handler thread:
a refusal in words, or ``None`` to accept, the swap arriving later as a
``rebind``. A bridge given none runs one railroad and can switch to no
other."""


class Bridge:
    """Serving from construction; `port` says where, `close()` stops it."""

    def __init__(
        self,
        bus: Bus,
        port: int = 0,
        wants: Wants | None = None,
        host: str = "127.0.0.1",
    ) -> None:
        self._bus = bus
        self._wants = wants
        # The railroad the bus being relayed is running, and what each client
        # named in its path; `''` is nothing named, which is what a client
        # reaching a bridge with no session behind it says.
        self._running = ""
        self._clients: dict[ServerConnection, str] = {}
        self._waiting: dict[ServerConnection, str] = {}
        self._clients_lock = threading.Lock()
        bus.subscribe("tc49/#", self._relay)
        # Loopback unless told otherwise, which is what the browser reached
        # until a proxy did (ADR-0042).
        self._server: Server = serve(self._serve_client, host, port)
        threading.Thread(
            target=self._server.serve_forever, name="bridge", daemon=True
        ).start()

    @property
    def port(self) -> int:
        return int(self._server.socket.getsockname()[1])

    @property
    def connections(self) -> int:
        """Clients currently registered. A fresh client's registration lands
        moments after its handshake, so anyone who must not race it — a test,
        a session banner — watches this rather than assuming."""
        with self._clients_lock:
            return len(self._clients)

    def close(self) -> None:
        self._server.shutdown()

    def rebind(self, bus: Bus, railroad: str) -> None:
        """Relay a freshly assembled railroad, and settle every client on it.

        One operator, one railroad, and afterwards that is exactly true:
        whoever named this railroad is registered here — before the assembly's
        opening drain, so the startup cascade is their first frames and there
        is nothing to seed — and every other client, on the railroad this one
        replaces or waiting on a third, is closed. Closing is what has them
        re-pick, rather than render the wrong railroad or wait out a swap that
        somebody else's has overtaken.
        """
        self._bus = bus
        bus.subscribe("tc49/#", self._relay)
        with self._clients_lock:
            self._running = railroad
            # Registered and waiting settle by the same rule, which is what
            # makes the rule one sentence: named this railroad, or gone.
            settling = self._clients | self._waiting
            self._clients = {
                one: railroad for one in settling if settling[one] == railroad
            }
            self._waiting = {}
            parting = [one for one in settling if settling[one] != railroad]
        for one in parting:
            one.close()

    def _relay(self, topic: str, payload: Payload) -> None:
        frame = json.dumps({"topic": topic, "payload": payload})
        with self._clients_lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.send(frame)
            except ConnectionClosed:
                pass  # its handler thread is already on the way out

    def _serve_client(self, connection: ServerConnection) -> None:
        # The railroad the client named, off the socket path. A handler runs
        # only once the handshake has produced a request; naming nothing is
        # what a client reaching a bridge with no session behind it does.
        request = connection.request
        named = "" if request is None else request.path.strip("/")
        try:
            if not self._join(connection, named):
                return
            for message in connection:
                self._receive(connection, message)
        except ConnectionClosed:
            # A browser tab that is reloaded or discarded goes without a close
            # handshake. That is a client leaving, not a fault: letting it out
            # of the handler puts a traceback in the session's own log.
            pass
        finally:
            with self._clients_lock:
                self._clients.pop(connection, None)
                self._waiting.pop(connection, None)

    def _join(self, connection: ServerConnection, named: str) -> bool:
        """Register the client for the railroad it named, or refuse it.

        Everything here is under the lock the relay takes. For the running
        railroad that is what orders the last values against live frames: a
        frame published while this runs either lands in the picture sent here
        or is relayed after, so a client is never served one that has already
        been overtaken by the events it sits behind. For any other it is what
        keeps `wants` from being answered by a swap that lands before the
        client is on the list to be woken by it. The relay waits for the
        length of the callback, so `wants` reads a railroad's documents and
        does not build one — a fraction of one boundary, once per join.
        """
        with self._clients_lock:
            if named == self._running:
                for topic, payload in self._bus.last_values.items():
                    connection.send(json.dumps({"topic": topic, "payload": payload}))
                self._clients[connection] = named
                return True
            refusal = (
                self._wants(named)
                if self._wants is not None
                else f"this session is not running '{named}'"
            )
            if refusal is None:
                self._waiting[connection] = named
                return True
        connection.send(json.dumps({"error": refusal}))
        return False

    def _receive(self, connection: ServerConnection, message: str | bytes) -> None:
        try:
            frame = json.loads(message)
            topic, payload = frame["topic"], frame["payload"]
        except (ValueError, TypeError, KeyError):
            connection.send(json.dumps({"error": "expected {topic, payload} JSON"}))
            return
        # A refusal names what is allowed instead, so a client told no learns
        # the whole of its write surface. The type check is not pedantry: a
        # topic that is not a string may not even be hashable.
        if not isinstance(topic, str) or topic not in INBOUND:
            allowed = " and ".join(f"'{one}'" for one in sorted(INBOUND))
            connection.send(
                json.dumps({"error": f"'{topic}' is not inbound; only {allowed} are"})
            )
            return
        self._bus.publish(topic, payload)
