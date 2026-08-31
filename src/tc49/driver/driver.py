"""Driver: the stateless translator from granted moves to the command.

Per granted move it immediately publishes `move`, the move itself,
mirrored. Setting the route is the dispatcher's, which publishes `align`
(ADR-0022), so a grant is the driver's green signal. It holds no state and
reads no assets (SYSTEM.md, driver footprint).
"""

from tc49.lib.bus import Bus, Payload


class Driver:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        bus.subscribe("tc49/dispatch/move_granted", self._on_move)

    def _on_move(self, topic: str, payload: Payload) -> None:
        connection, _, transit = payload["transit"].partition(".")
        self._bus.publish(
            "tc49/layout/move",
            {
                "train": payload["train"],
                "connection": connection,
                "transit": transit,
                "into": payload["into"],
            },
        )
