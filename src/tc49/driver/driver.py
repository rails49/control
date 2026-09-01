"""Driver: the stateless translator from granted moves to the command.

Per granted move it immediately publishes `move`, the move itself,
mirrored. Setting the route is the dispatcher's, which publishes `align`
(ADR-0022), so a grant is the driver's green signal. It holds no state and
reads no assets (SYSTEM.md, driver footprint).

The one thing it does read is the grant, and it is **read** and never trusted
(#261): a topic under `dispatch` names the component that answers for it and
not the process that published this frame, the bus authenticates nobody, and a
consumer may not raise on a payload (SYSTEM.md, rule 4). In process the
dispatcher publishing it is a call away; under MQTT it is another process, and
a bug there must not take the driver down.
"""

from tc49.lib.bus import Bus, Payload
from tc49.lib.payload import grant


class Driver:
    def __init__(self, bus: Bus) -> None:
        self._bus = bus
        bus.subscribe("tc49/dispatch/move_granted", self._on_move)

    def _on_move(self, topic: str, payload: Payload) -> None:
        """One grant restated as the command that moves the train.

        A frame that cannot be read is **dropped**, silently and to the trace:
        the driver commands and answers nothing, so there is nowhere to address
        a refusal to even where the frame carries an id (ADR-0034), and a
        dropped frame is already on the trace by virtue of having been
        published.

        Splitting the transit is the whole of what the driver does with what it
        read — the inventory states the grant's transit qualified and `move`'s
        bare — and the split is the last thing that can fail the read. A
        transit missing either half names no connection or no transit to
        command with, and goes the way of any other frame that cannot be read.
        That the two halves name anything is the layout's question and not the
        driver's, which knows nothing of the layout: the form of the name is
        the whole of what there is to read here.
        """
        move = grant(payload)
        if move is None:
            return
        connection, _, transit = move.transit.partition(".")
        if not connection or not transit:
            return
        self._bus.publish(
            "tc49/layout/move",
            {
                "train": move.train,
                "connection": connection,
                "transit": transit,
                "into": move.into,
            },
        )
