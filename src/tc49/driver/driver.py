"""Driver: the stateless translator from granted moves to the command.

Per granted move it immediately publishes `move`, the move itself,
mirrored. Setting the route is the dispatcher's, which publishes `align`
(ADR-0022), so a grant is the driver's green signal. It holds no state and
reads no assets (SYSTEM.md, driver footprint).

Its whole judgement is **how fast**, and it is a pure function of the aspect
the grant shows (ADR-0025): `SPEEDS` below, injected so that a railroad can
say what its aspects are worth without this module being rebuilt. How fast is
the only open question, because the turnouts are already thrown when the
aspect clears; and it is *how fast* and not which way, direction being the
layout interface's to compose out of geometry the driver does not hold.

The one thing it does read is the grant, and it is **read** and never trusted
(#261): a topic under `dispatch` names the component that answers for it and
not the process that published this frame, the bus authenticates nobody, and a
consumer may not raise on a payload (SYSTEM.md, rule 4). In process the
dispatcher publishing it is a call away; under MQTT it is another process, and
a bug there must not take the driver down.
"""

from collections.abc import Mapping

from tc49.lib.bus import Bus, Payload
from tc49.lib.payload import grant, granted_aspect

SPEEDS: Mapping[str, float] = {"clear": 1.0, "caution": 0.4}
"""What each aspect is worth as a speed, a fraction of the locomotive's
maximum (ADR-0025).

`stop` is **absent rather than zero**: a grant showing it is not a permission
to move, so there is no command to send and a mapping entry would invent one.

Two numbers and not a file: the first train to move (#211) does not earn a
format, and braking distance waits until a train has run (GOALS.md, driving).
Injected all the same, because a railroad whose locomotives crawl at `caution`
is a constructor argument away and not a fork of this module.
"""


class Driver:
    def __init__(self, bus: Bus, speeds: Mapping[str, float] = SPEEDS) -> None:
        self._bus = bus
        self._speeds = speeds
        bus.subscribe("tc49/dispatch/move_granted", self._on_move)

    def _on_move(self, topic: str, payload: Payload) -> None:
        """One grant restated as the command that moves the train.

        A frame that cannot be read is **dropped**, silently and to the trace:
        the driver commands and answers nothing, so there is nowhere to address
        a refusal to even where the frame carries an id (ADR-0034), and a
        dropped frame is already on the trace by virtue of having been
        published.

        Splitting the transit is what the driver does with what it read
        besides pricing the aspect — the inventory states the grant's transit
        qualified and `move`'s bare — and the split is the last thing that can
        fail. A
        transit missing either half names no connection or no transit to
        command with, and goes the way of any other frame that cannot be read.
        That the two halves name anything is the layout's question and not the
        driver's, which knows nothing of the layout: the form of the name is
        the whole of what there is to read here.

        An aspect the mapping does not carry is dropped the same way, and the
        two aspects that reach here are the same case: `stop` reads perfectly
        well and authorises no move, and a name from outside the enum leaves
        nothing to run at. There is no default to fall back on — a speed this
        component invented would be authority the dispatcher never gave — and
        a drop is what a grant this driver cannot act on is worth, since it
        commands and answers nothing (SYSTEM.md, rule 4).
        """
        granted = grant(payload)
        if granted is None:
            return
        aspect = granted_aspect(payload)
        speed = self._speeds.get(aspect) if aspect is not None else None
        if speed is None:
            return
        connection, _, transit = granted.transit.partition(".")
        if not connection or not transit:
            return
        self._bus.publish(
            "tc49/layout/move",
            {
                "train": granted.train,
                "connection": connection,
                "transit": transit,
                "into": granted.into,
                "speed": speed,
            },
        )
