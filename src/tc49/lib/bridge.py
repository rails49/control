"""The WebSocket bridge: the milestone binding between bus and browser.

A relay and nothing more (ui/PANEL.md, #71): every `tc49/#` event goes out
to every connected client as one JSON frame, ``{"topic": …, "payload": …}``,
and a frame on the one inbound topic — ``request_submitted``, the panel's
whole write surface — is published as the event it names. Anything else
inbound is refused with an error frame; the dispatcher stays the sole
feasibility authority precisely because nothing else can reach the bus.

It lives here beside the bus binding it rides on and shares its fate: when
the bus becomes a real broker, the browser speaks MQTT-over-WebSocket to the
broker directly and this file is deleted (ADR-0013 wiring note, #67).

Threading: the bus stays single-threaded. Outbound frames are sent by
whatever thread drains the bus — one sender per connection, which is what
the sync connection allows. Inbound, each client's handler thread calls
``publish``, which is one queue append; the event is delivered when the
session's loop next drains, exactly as a scheduler's would be. Restricting
inbound to an event topic keeps that cross-thread surface to the append —
a state topic would also write the last-value map.
"""

import json
import threading

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

from tc49.lib.bus import Bus, Payload

INBOUND = "tc49/schedule/request_submitted"


class Bridge:
    """Serving from construction; `port` says where, `close()` stops it."""

    def __init__(self, bus: Bus, port: int = 0) -> None:
        self._bus = bus
        self._clients: set[ServerConnection] = set()
        self._clients_lock = threading.Lock()
        bus.subscribe("tc49/#", self._relay)
        self._server: Server = serve(self._serve_client, "127.0.0.1", port)
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
        with self._clients_lock:
            self._clients.add(connection)
        try:
            for message in connection:
                self._receive(connection, message)
        finally:
            with self._clients_lock:
                self._clients.discard(connection)

    def _receive(self, connection: ServerConnection, message: str | bytes) -> None:
        try:
            frame = json.loads(message)
            topic, payload = frame["topic"], frame["payload"]
        except (ValueError, TypeError, KeyError):
            connection.send(json.dumps({"error": "expected {topic, payload} JSON"}))
            return
        if topic != INBOUND:
            connection.send(
                json.dumps({"error": f"'{topic}' is not inbound; only '{INBOUND}' is"})
            )
            return
        self._bus.publish(INBOUND, payload)
