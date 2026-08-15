"""Driver: the stateless translator from granted moves to layout commands.

Per granted move it immediately publishes `align` (set the connection to
the transit) and `cross` (the move itself, mirrored). It holds no state,
reads no assets, and does not subscribe to the tick (SYSTEM.md, driver
footprint).
"""

from tc49.lib.bus import Bus, Payload


class Driver:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        bus.subscribe("tc49/dispatch/move_granted", self._on_move)

    def _on_move(self, topic: str, payload: Payload) -> None:
        connection, _, transit = payload["transit"].partition(".")
        self._bus.publish(
            "tc49/drive/align", {"connection": connection, "transit": transit}
        )
        self._bus.publish(
            "tc49/drive/cross",
            {
                "train": payload["train"],
                "connection": connection,
                "transit": transit,
                "into": payload["into"],
            },
        )
